"""Focused setup and shared-budget PostgreSQL model-usage proofs."""

from copy import deepcopy
import json

from app.modules.model_usage.models import ModelUsageEffect
from tests.checkers_model_calls.model_usage_pg_support import (
    DatabaseFacts,
    model_database as _model_database,
)
from tests.checkers_model_calls.test_model_call_transactions_postgresql import (
    AsyncSession,
    BoundaryPorts,
    DBAPIError,
    ModelCallBudgetUnavailable,
    ModelCallConflict,
    ModelCallUsage,
    ModelGenerationSettings,
    ModelProfileProvisioningFacts,
    ModelProfileReader,
    ModelCallUnavailable,
    ModelUsageBudgetAccount,
    asyncio,
    canonical_json_hash,
    evidence,
    execution,
    insert_checker_run,
    new_record_id,
    provision,
    pytest,
    service,
    setup_service,
    setup_slot_key,
    sha,
    slot,
    text,
    uuid4,
)

model_database = _model_database


async def test_profile_reader_requires_exact_project_and_selector(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    profile = await provision(model_database, ports, limit=10_000)
    async with AsyncSession(model_database.engine) as session:
        async with session.begin():
            reader = ModelProfileReader(session)
            assert (
                await reader.read_exact(
                    profile.selector,
                    project_id=model_database.project_id,
                )
                == profile
            )
            with pytest.raises(ModelCallUnavailable, match="model_profile_unavailable"):
                await reader.read_exact(profile.selector, project_id=new_record_id())
            with pytest.raises(ModelCallUnavailable, match="model_profile_unavailable"):
                await reader.read_exact(
                    profile.selector.model_copy(
                        update={"profile_digest": sha("substituted-profile")}
                    ),
                    project_id=model_database.project_id,
                )


async def test_provisioning_replay_retains_original_receipts_with_fresh_authority(
    model_database: DatabaseFacts,
) -> None:
    await provision(model_database, BoundaryPorts(), limit=10_000, replay=True)


async def test_profile_publication_rejects_substituted_authority_digest(
    model_database: DatabaseFacts,
) -> None:
    with pytest.raises(DBAPIError):
        await provision(
            model_database,
            BoundaryPorts(corrupt_admin_receipt=True),
            limit=10_000,
        )


async def test_profile_publication_is_not_owned_by_a_checker_registry_entry(
    model_database: DatabaseFacts,
) -> None:
    async with model_database.engine.begin() as connection:
        await connection.execute(
            text("update external_checker_registry_entries set phase='pre_submit' where id=:id"),
            {"id": model_database.registry_entry_id},
        )
    profile = await provision(model_database, BoundaryPorts(), limit=10_000)
    assert profile.spec.project_id == model_database.project_id


async def test_setup_profile_selection_pins_latest_matching_identity(
    model_database: DatabaseFacts,
) -> None:
    """New attempts see a matching update; old snapshots and other models do not drift."""
    ports = BoundaryPorts()
    first = await provision(model_database, ports, limit=10_000)

    async def publish(spec):
        facts = ModelProfileProvisioningFacts(
            operation_id=uuid4(),
            actor_profile_id=new_record_id(),
            spec=spec,
            profile_digest=canonical_json_hash(spec.model_dump(mode="json")),
        )
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await service(session, ports).provision_profile(facts)

    second = await publish(
        first.spec.model_copy(
            update={
                "profile_version": 2,
                "settings": ModelGenerationSettings(reasoning_effort="high", text_verbosity="low"),
            }
        )
    )
    await publish(
        first.spec.model_copy(
            update={
                "profile_version": 3,
                "model_snapshot": "gpt-unrelated-2026-10-01",
            }
        )
    )

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            reader = ModelProfileReader(session)
            selected = await reader.read_latest_matching(
                project_id=model_database.project_id,
                provider=first.spec.provider,
                api=first.spec.api,
                model_snapshot=first.spec.model_snapshot,
            )
            pinned = await reader.read_exact(
                {
                    "profile_id": first.profile_id,
                    "profile_version": first.spec.profile_version,
                    "profile_digest": first.profile_digest,
                },
                project_id=model_database.project_id,
            )

    assert selected.profile_id == second.profile_id
    assert selected.spec.profile_version == 2
    assert pinned.profile_id == first.profile_id
    assert pinned.spec.profile_version == 1


async def test_database_guards_recompute_profile_and_budget_digests(
    model_database: DatabaseFacts,
) -> None:
    await provision(model_database, BoundaryPorts(), limit=10_000)
    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError, match="profile digest is invalid"):
            async with session.begin():
                await session.execute(
                    text(
                        "insert into model_usage_profiles select :id,project_id,2,:digest,provider,api,model_snapshot,generation_settings,maximum_request_bytes,maximum_output_bytes,maximum_response_bytes,maximum_input_tokens,maximum_output_tokens,maximum_calls,maximum_total_request_bytes,maximum_total_response_bytes,maximum_total_input_tokens,maximum_total_output_tokens,allowed_tools,maximum_tool_calls,maximum_tool_output_bytes,deadline_ms,pricing_policy_id,pricing_policy_version,pricing_policy_digest,uncached_input_rate,cached_input_rate,output_rate,:operation,actor_profile_id,:authority,clock_timestamp() from model_usage_profiles where profile_version=1"
                    ),
                    {
                        "id": new_record_id(),
                        "digest": sha("noncanonical-profile"),
                        "operation": uuid4(),
                        "authority": new_record_id(),
                    },
                )

    async with AsyncSession(model_database.engine) as session:
        with pytest.raises(DBAPIError, match="configuration digest is invalid"):
            async with session.begin():
                await session.execute(
                    text(
                        "insert into model_usage_budget_configurations select :id,project_id,2,:digest,authorized_total_nanodollars,externally_reconciled_prior_spend_nanodollars,lifetime_limit_nanodollars,:operation,actor_profile_id,:authority,clock_timestamp() from model_usage_budget_configurations where configuration_version=1"
                    ),
                    {
                        "id": new_record_id(),
                        "digest": sha("noncanonical-budget"),
                        "operation": uuid4(),
                        "authority": new_record_id(),
                    },
                )


async def test_concurrent_dispatch_reserves_one_lifetime_budget(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation)
    prepared = []
    for requirement in ("model_a", "model_b"):
        run = execution(model_database)
        paid_slot = slot(model_database, profile, requirement)
        request_sha = sha(requirement)
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                item = await service(session, ports).prepare_attempt(
                    run,
                    paid_slot,
                    registry_entry_id=model_database.registry_entry_id,
                    request_sha256=request_sha,
                )
        prepared.append((run, item, evidence(requirement, request_sha)))

    async def dispatch(item):
        run, attempt, request_evidence = item
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await service(session, ports).reserve_dispatch(
                    run, attempt, request_evidence
                )

    results = await asyncio.gather(*(dispatch(item) for item in prepared), return_exceptions=True)
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, ModelCallBudgetUnavailable) for result in results) == 1
    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == reservation
        assert account.lifetime_settled_nanodollars == 0


async def test_setup_and_checker_dispatches_share_one_account_and_both_win(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch * 2,
        profile_changes={
            "maximum_calls": 2,
            "maximum_total_request_bytes": 20_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 200,
            "maximum_total_output_tokens": 100,
        },
    )
    checker_run = execution(model_database)
    checker_slot = slot(model_database, profile, "shared_budget_checker")
    checker_sha = sha("shared-budget-checker")
    checker_evidence = evidence("shared-budget-checker", checker_sha)
    setup_key = await setup_slot_key(model_database, profile)
    setup_sha = sha("shared-budget-setup")
    setup_evidence = evidence("shared-budget-setup", setup_sha)

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            checker_prepared = await service(session, ports).prepare_attempt(
                checker_run,
                checker_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=checker_sha,
            )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            setup_prepared = await setup_service(session, ports).prepare(setup_key, setup_sha)

    async def reserve_checker():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await service(session, ports).reserve_dispatch(
                    checker_run, checker_prepared, checker_evidence
                )

    async def reserve_setup():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await setup_service(session, ports).reserve_dispatch(
                    setup_prepared, setup_evidence
                )

    checker_reserved, setup_reserved = await asyncio.gather(reserve_checker(), reserve_setup())
    assert checker_reserved.reserved_nanodollars == per_dispatch
    assert setup_reserved.reserved_nanodollars == per_dispatch
    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == per_dispatch * 2
        assert account.lifetime_settled_nanodollars == 0


async def test_cheap_completed_call_reserves_remaining_aggregate_before_next_dispatch(
    model_database: DatabaseFacts,
) -> None:
    """A cheap first result cannot defer an aggregate-token failure until after I/O."""
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch * 2,
        profile_changes={
            "maximum_calls": 2,
            "maximum_total_request_bytes": 20_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 100,
            "maximum_total_output_tokens": 100,
        },
    )
    run = execution(model_database)
    first_slot = slot(model_database, profile, "aggregate_pre_dispatch")
    second_slot = first_slot.model_copy(update={"slot_index": 1})
    first_sha = sha("aggregate-pre-dispatch-first")
    second_sha = sha("aggregate-pre-dispatch-second")

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            first_prepared = await owner.prepare_attempt(
                run,
                first_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=first_sha,
            )
            first_dispatched = await owner.reserve_dispatch(
                run,
                first_prepared,
                evidence("aggregate-pre-dispatch-first", first_sha),
            )
            await owner.complete(
                first_dispatched.effect,
                provider_response_id="resp_cheap_cached",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=evidence(
                    "aggregate-pre-dispatch-response",
                    sha("aggregate-pre-dispatch-response"),
                ),
                usage=ModelCallUsage(
                    input_tokens=10,
                    cached_input_tokens=10,
                    output_tokens=0,
                    reasoning_tokens=0,
                ),
            )
            second_prepared = await owner.prepare_attempt(
                run,
                second_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=second_sha,
            )
            with pytest.raises(ModelCallBudgetUnavailable, match="run_envelope"):
                await owner.reserve_dispatch(
                    run,
                    second_prepared,
                    evidence("aggregate-pre-dispatch-second", second_sha),
                )

    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        second = await session.get(ModelUsageEffect, str(second_prepared.attempt_id))
        assert account.lifetime_reserved_nanodollars == 0
        assert account.lifetime_settled_nanodollars == 10 * 2
        assert second is not None and second.state == "prepared"


async def test_setup_draft_review_correction_settle_three_shared_calls(
    model_database: DatabaseFacts,
) -> None:
    """One exact setup attempt can run a finite three-call owner-controlled loop."""
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch * 3,
        profile_changes={
            "maximum_calls": 3,
            "maximum_total_request_bytes": 30_000,
            "maximum_total_response_bytes": 90_000,
            "maximum_total_input_tokens": 300,
            "maximum_total_output_tokens": 150,
        },
    )
    base = await setup_slot_key(model_database, profile)
    settled = 0
    for index, phase in enumerate(("draft", "review", "correction")):
        key = base.model_copy(update={"phase": phase, "call_index": index})
        request_sha = sha(f"setup-loop-{phase}-request")
        response_sha = sha(f"setup-loop-{phase}-response")
        usage = ModelCallUsage(
            input_tokens=10 + index,
            cached_input_tokens=index,
            output_tokens=5 + index,
            reasoning_tokens=index,
        )
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                owner = setup_service(session, ports)
                prepared = await owner.prepare(key, request_sha)
                dispatched = await owner.reserve_dispatch(
                    prepared, evidence(f"setup-loop-{phase}-request", request_sha)
                )
                completed = await owner.complete(
                    dispatched.effect,
                    provider_response_id=f"resp_setup_{phase}",
                    provider_model_snapshot=profile.spec.model_snapshot,
                    response_evidence=evidence(f"setup-loop-{phase}-response", response_sha),
                    usage=usage,
                )
                assert completed.effect.slot_key == key
                assert completed.state == "completed"
                assert completed.replayed is False
                settled += completed.settled_nanodollars

    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        states = (
            (
                await session.execute(
                    text(
                        "select effect.state from model_usage_effects effect join setup_model_usage_slots slot on slot.id=effect.setup_slot_id where slot.compilation_attempt_id=:attempt order by slot.call_index"
                    ),
                    {"attempt": base.compilation_attempt_id},
                )
            )
            .scalars()
            .all()
        )
        assert states == ["completed", "completed", "completed"]
        assert account.lifetime_reserved_nanodollars == 0
        assert account.lifetime_settled_nanodollars == settled


async def test_setup_known_failure_settles_once_and_replays_after_restart(
    model_database: DatabaseFacts,
) -> None:
    """An unusable paid response conserves exact spend and never dispatches twice."""
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation)
    key = await setup_slot_key(model_database, profile)
    request_sha = sha("setup-known-failure-request")
    response = evidence("setup-known-failure-response", sha("setup-known-failure-response"))
    usage = ModelCallUsage(
        input_tokens=40,
        cached_input_tokens=10,
        output_tokens=12,
        reasoning_tokens=3,
    )

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = setup_service(session, ports)
            prepared = await owner.prepare(key, request_sha)
            dispatched = await owner.reserve_dispatch(
                prepared,
                evidence("setup-known-failure-request", request_sha),
            )
            failed = await owner.complete(
                dispatched.effect,
                provider_response_id="resp_setup_known_failure",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response,
                usage=usage,
                usable=False,
            )
            assert failed.state == "known_failed"
            assert failed.replayed is False

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            replay = await setup_service(session, ports).complete(
                dispatched.effect,
                provider_response_id="resp_setup_known_failure",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response,
                usage=usage,
                usable=False,
            )
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            row = await session.get(ModelUsageEffect, str(dispatched.effect.effect_id))
            assert replay.state == "known_failed"
            assert replay.replayed is True
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == 30 * 11 + 10 * 2 + 12 * 29
            assert row.settlement_authorization_evidence_id is not None
            assert row.settled_at is not None

    assert ports.events.count("setup_dispatch") == 1


async def test_setup_rejects_same_project_profile_substitution_before_effect(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    profile_a = await provision(model_database, ports, limit=1_000_000)
    spec_b = profile_a.spec.model_copy(
        update={
            "profile_version": 2,
            "settings": ModelGenerationSettings(
                reasoning_effort="high",
                text_verbosity="low",
            ),
        }
    )
    facts_b = ModelProfileProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=spec_b,
        profile_digest=canonical_json_hash(spec_b.model_dump(mode="json")),
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            profile_b = await service(session, ports).provision_profile(facts_b)

    locked_key = await setup_slot_key(model_database, profile_a)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            await setup_service(session, ports).prepare(
                locked_key,
                sha("locked-profile-a-request"),
            )
    substituted = locked_key.model_copy(
        update={
            "profile_id": profile_b.profile_id,
            "profile_version": profile_b.spec.profile_version,
            "profile_digest": profile_b.profile_digest,
        }
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        with pytest.raises(DBAPIError, match="invalid setup model usage envelope ownership"):
            async with session.begin():
                await setup_service(session, ports).prepare(
                    substituted,
                    sha("same-project-profile-substitution"),
                )
    async with AsyncSession(model_database.engine) as session:
        counts = (
            await session.execute(
                text(
                    "select count(distinct envelope.id),count(effect.id),min(envelope.profile_id::text) from setup_model_usage_envelopes envelope join setup_model_usage_slots slot on slot.envelope_id=envelope.id join model_usage_effects effect on effect.setup_slot_id=slot.id where envelope.compilation_attempt_id=:attempt"
                ),
                {"attempt": locked_key.compilation_attempt_id},
            )
        ).one()
        assert counts == (1, 1, str(profile_a.profile_id))


async def test_uncertain_setup_effect_replay_never_reauthorizes_dispatch(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation)
    key = await setup_slot_key(model_database, profile)
    request_sha = sha("setup-uncertain-request")
    request_evidence = evidence("setup-uncertain-request", request_sha)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = setup_service(session, ports)
            prepared = await owner.prepare(key, request_sha)
            dispatched = await owner.reserve_dispatch(prepared, request_evidence)
            observed = await owner.mark_uncertain(
                dispatched.effect,
                sha("setup-uncertain-observation"),
            )
            assert observed.state == "uncertain"

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = setup_service(session, ports)
            observed = await owner.recover_existing(key, request_sha)
            assert observed is not None
            assert observed.state == "uncertain"
            assert observed.replayed is True
            replayed = await owner.prepare(key, request_sha)
            with pytest.raises(ModelCallConflict, match="not_dispatchable"):
                await owner.reserve_dispatch(replayed, request_evidence)
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == reservation
            assert account.lifetime_settled_nanodollars == 0


async def test_setup_and_checker_dispatches_share_one_account_cap(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(
        model_database,
        ports,
        limit=per_dispatch,
        profile_changes={
            "maximum_calls": 2,
            "maximum_total_request_bytes": 20_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 200,
            "maximum_total_output_tokens": 100,
        },
    )
    checker_run = execution(model_database)
    checker_slot = slot(model_database, profile, "shared_cap_checker")
    checker_sha = sha("shared-cap-checker")
    checker_evidence = evidence("shared-cap-checker", checker_sha)
    setup_key = await setup_slot_key(model_database, profile)
    setup_sha = sha("shared-cap-setup")
    setup_evidence = evidence("shared-cap-setup", setup_sha)

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            checker_prepared = await service(session, ports).prepare_attempt(
                checker_run,
                checker_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=checker_sha,
            )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            setup_prepared = await setup_service(session, ports).prepare(setup_key, setup_sha)

    async def reserve_checker():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await service(session, ports).reserve_dispatch(
                    checker_run, checker_prepared, checker_evidence
                )

    async def reserve_setup():
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                return await setup_service(session, ports).reserve_dispatch(
                    setup_prepared, setup_evidence
                )

    results = await asyncio.gather(reserve_checker(), reserve_setup(), return_exceptions=True)
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    assert sum(isinstance(result, ModelCallBudgetUnavailable) for result in results) == 1
    async with AsyncSession(model_database.engine) as session:
        account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
        assert account.lifetime_reserved_nanodollars == per_dispatch
        assert account.lifetime_settled_nanodollars == 0


async def test_setup_reservation_rollback_releases_shared_account(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    per_dispatch = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=per_dispatch)
    setup_key = await setup_slot_key(model_database, profile)
    setup_sha = sha("rollback-shared-setup")
    setup_evidence = evidence("rollback-shared-setup", setup_sha)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            setup_prepared = await setup_service(session, ports).prepare(setup_key, setup_sha)
        with pytest.raises(RuntimeError, match="force setup rollback"):
            async with session.begin():
                await setup_service(session, ports).reserve_dispatch(setup_prepared, setup_evidence)
                raise RuntimeError("force setup rollback")

    checker_run = execution(model_database)
    checker_slot = slot(model_database, profile, "after_setup_rollback")
    checker_sha = sha("after-setup-rollback")
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            checker_prepared = await service(session, ports).prepare_attempt(
                checker_run,
                checker_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=checker_sha,
            )
            reserved = await service(session, ports).reserve_dispatch(
                checker_run,
                checker_prepared,
                evidence("after-setup-rollback", checker_sha),
            )
            assert reserved.reserved_nanodollars == per_dispatch
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == per_dispatch
            assert account.lifetime_settled_nanodollars == 0


async def test_fresh_execution_authority_precedes_currentness_and_owner_locks(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    run = execution(model_database)
    paid_slot = slot(model_database, profile, "model_order")
    request_sha = sha("ordered-request")
    ports.events.clear()
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            prepared = await owner.prepare_attempt(
                run,
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=request_sha,
            )
            assert ports.events == ["prepare", "current"]
            ports.events.clear()
            dispatched = await owner.reserve_dispatch(
                run,
                prepared,
                evidence("ordered-request", request_sha),
            )
            assert ports.events == ["dispatch", "current"]
            await owner.mark_uncertain(
                dispatched.effect,
                sha("ordered-uncertain"),
                provider_response_id="resp_ordered",
            )

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            await insert_checker_run(session, run)
            owner = service(session, ports)
            ports.events.clear()
            await owner.attach_recovery(run, dispatched.effect)
            assert ports.events == ["recover", "current"]
            ports.events.clear()
            with pytest.raises(ModelCallConflict, match="not_retryable"):
                await owner.prepare_recovery_child(
                    paid_slot,
                    registry_entry_id=model_database.registry_entry_id,
                    parent_attempt_id=prepared.attempt_id,
                    terminal_digest=sha("ordered-uncertain"),
                    request_sha256=prepared.request_sha256,
                )
            assert ports.events == ["child", "recovery_current"]


async def test_recovery_insert_rejects_every_substituted_owner_and_authority_fact(
    model_database: DatabaseFacts,
) -> None:
    """The SQL boundary proves a fresh successor and rejects unrelated recovery facts."""
    ports = BoundaryPorts()
    profile = await provision(model_database, ports, limit=10_000)
    origin = execution(model_database)
    paid_slot = slot(model_database, profile, "recovery_guard_origin")
    request_sha = sha("recovery-guard-origin")
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            prepared = await owner.prepare_attempt(
                origin,
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=request_sha,
            )
            dispatched = await owner.reserve_dispatch(
                origin,
                prepared,
                evidence("recovery-guard-origin", request_sha),
            )
            await owner.mark_uncertain(
                dispatched.effect,
                sha("recovery-guard-origin-uncertain"),
                provider_response_id="resp_recovery_guard_origin",
            )

    other_origin = execution(model_database)
    other_slot = slot(model_database, profile, "recovery_guard_other")
    other_sha = sha("recovery-guard-other")
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            other_prepared = await owner.prepare_attempt(
                other_origin,
                other_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=other_sha,
            )
            other_dispatched = await owner.reserve_dispatch(
                other_origin,
                other_prepared,
                evidence("recovery-guard-other", other_sha),
            )
            await owner.mark_uncertain(
                other_dispatched.effect,
                sha("recovery-guard-other-uncertain"),
                provider_response_id="resp_recovery_guard_other",
            )

    successor = execution(model_database)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            await insert_checker_run(session, successor)
            attached = await service(session, ports).attach_recovery(successor, dispatched.effect)
            assert attached.replayed is False
            stored = (
                (
                    await session.execute(
                        text(
                            "select attempt_id,checker_run_id,worker_lease_id,"
                            "worker_lease_generation,execution_facts,effect_facts,"
                            "authorization_evidence_id from checker_model_usage_recoveries "
                            "where attempt_id=:effect"
                        ),
                        {"effect": dispatched.effect.attempt_id},
                    )
                )
                .mappings()
                .one()
            )
            authority = (
                (
                    await session.execute(
                        text(
                            "select actor_id,action_id,permission_id,after_facts "
                            "from audit_events where id=:id"
                        ),
                        {"id": stored["authorization_evidence_id"]},
                    )
                )
                .mappings()
                .one()
            )

    unrelated_run = execution(model_database)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            await insert_checker_run(session, unrelated_run)

    base_execution = deepcopy(stored["execution_facts"])
    base_effect = deepcopy(stored["effect_facts"])
    wrong_project = str(new_record_id())
    wrong_lease = str(new_record_id())
    mutations = {
        "project": lambda row: row["execution"].__setitem__("project_id", wrong_project),
        "run": lambda row: row.__setitem__("run", str(unrelated_run.checker_run_id)),
        "lease": lambda row: row.__setitem__("lease", wrong_lease),
        "generation": lambda row: row.__setitem__("generation", 99),
        "effect": lambda row: (
            row.__setitem__("effect_id", str(other_dispatched.effect.attempt_id)),
            row.__setitem__("effect", other_dispatched.effect.model_dump(mode="json")),
        ),
        "action": lambda row: row.__setitem__("action", "checker.model_call.dispatch"),
        "actor": lambda row: row.__setitem__("actor", str(new_record_id())),
        "resource_digest": lambda row: row.__setitem__(
            "after", {"allowed": True, "resource_context_digest": sha("wrong-recover")}
        ),
    }
    for label, mutate in mutations.items():
        row = {
            "effect_id": str(stored["attempt_id"]),
            "run": str(stored["checker_run_id"]),
            "lease": str(stored["worker_lease_id"]),
            "generation": stored["worker_lease_generation"],
            "execution": deepcopy(base_execution),
            "effect": deepcopy(base_effect),
            "actor": authority["actor_id"],
            "action": authority["action_id"],
            "permission": authority["permission_id"],
            "after": authority["after_facts"],
        }
        mutate(row)
        async with AsyncSession(model_database.engine) as session:
            with pytest.raises(DBAPIError, match="recovery (ancestry|authority) is invalid"):
                async with session.begin():
                    if label == "actor":
                        await session.execute(
                            text(
                                "insert into actor_profiles(id,actor_kind,status) "
                                "values (:id,'human','active')"
                            ),
                            {"id": row["actor"]},
                        )
                    evidence_id = new_record_id()
                    await session.execute(
                        text(
                            "insert into audit_events(id,event_domain,event_type,actor_ref_kind,"
                            "actor_id,action_id,permission_id,denial_code,after_facts) values "
                            "(:id,'authority','SensitiveAuthorizationAllowed','actor_profile',"
                            ":actor,:action,:permission,null,cast(:after as json))"
                        ),
                        {
                            "id": evidence_id,
                            "actor": row["actor"],
                            "action": row["action"],
                            "permission": row["permission"],
                            "after": json.dumps(row["after"]),
                        },
                    )
                    await session.execute(
                        text(
                            "insert into checker_model_usage_recoveries("
                            "id,attempt_id,checker_run_id,worker_lease_id,"
                            "worker_lease_generation,execution_facts,effect_facts,"
                            "authorization_evidence_id) values "
                            "(:id,:effect,:run,:lease,:generation,cast(:execution as jsonb),"
                            "cast(:effect_facts as jsonb),:authority)"
                        ),
                        {
                            "id": new_record_id(),
                            "effect": row["effect_id"],
                            "run": row["run"],
                            "lease": row["lease"],
                            "generation": row["generation"],
                            "execution": json.dumps(row["execution"]),
                            "effect_facts": json.dumps(row["effect"]),
                            "authority": evidence_id,
                        },
                    )


async def test_reservation_rollback_and_completion_settle_exactly_once(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    run = execution(model_database)
    paid_slot = slot(model_database, profile, "model_rollback")
    request_sha = sha("rollback-request")
    request_art = evidence("request", request_sha)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            prepared = await service(session, ports).prepare_attempt(
                run,
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                request_sha256=request_sha,
            )
        with pytest.raises(RuntimeError, match="force rollback"):
            async with session.begin():
                await service(session, ports).reserve_dispatch(run, prepared, request_art)
                raise RuntimeError("force rollback")
        async with session.begin():
            dispatched = await service(session, ports).reserve_dispatch(run, prepared, request_art)

    usage = ModelCallUsage(
        input_tokens=40,
        cached_input_tokens=10,
        output_tokens=12,
        reasoning_tokens=7,
    )
    response_art = evidence("response", sha("response"))
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            completed = await owner.complete(
                dispatched.effect,
                provider_response_id="resp_exact_once",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            replay = await owner.complete(
                dispatched.effect,
                provider_response_id="resp_exact_once",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == completed.settled_nanodollars
            assert replay.replayed

    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            await insert_checker_run(session, run)
            ports.events.clear()
            attached = await service(session, ports).attach_completed(run, dispatched.effect)
            assert attached.replayed is False
            assert ports.events == ["recover", "current"]
