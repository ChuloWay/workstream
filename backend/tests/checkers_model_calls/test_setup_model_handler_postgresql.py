"""Real PostgreSQL and MinIO custody for one setup-model provider call."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict, replace
import os
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)

from app.adapters.artifacts import (
    create_artifact_store_bootstrap,
    setup_model_evidence,
    setup_model_output_binding,
    setup_model_output_storage,
)
from app.adapters.auth import setup_model_service_authorization
from app.adapters.checkers import model_profile_reader
from app.adapters.model_usage import setup_model_usage_service
from app.adapters.project_agents.openrouter_policy import openrouter_request_options
from app.adapters.project_agents.setup_model_handler import (
    SetupModelProxyHandler,
    SetupProviderResponse,
)
from app.adapters.projects import setup_model_usage_owner
from app.interfaces.artifacts import ArtifactStoreNamespaceClaim
from app.interfaces.setup_model_proxy import (
    SetupModelProxyRequest,
    SetupModelProxySubject,
    canonical_provider_json,
)
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.preparation import (
    ArtifactPreparationService,
    ArtifactScratchManager,
)
from app.modules.artifacts.service import artifact_storage_namespace_spec
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    ProjectGuideCompilationExecutePreflightFacts,
    ProjectGuideCompilationRequestOrigin,
)
from app.modules.model_usage.api import (
    ModelCallUsage,
    ProjectModelProfile,
    ProjectModelProfileSpec,
)
from tests.artifact_store_helpers import (
    artifact_admission_limit_settings,
    artifact_preparation_limits,
)
from tests.checkers.execution.support import provision_post_submit_service
from tests.checkers_model_calls.test_model_call_contract import profile_spec
from tests.projects.guide_compilation.helpers import (
    context,
    identity,
    persistence_facts,
    runtime_configuration,
    seed_database,
    service_actor,
)
from tests.projects.guide_compilation.test_authorized_execution_service import (
    _execution_service,
)
from tests.projects.guide_compilation.test_authorized_request_service import (
    _authorized_service,
    _request,
    _seed_human,
)


def _setup_profile(project_id: UUID) -> ProjectModelProfileSpec:
    source = profile_spec().model_dump(mode="python")
    source.update(
        project_id=project_id,
        profile_version=1,
        provider="openrouter",
        api="chat_completions",
        model_snapshot="openai/model",
        maximum_input_tokens=1_050_000,
        maximum_output_tokens=128_000,
        maximum_calls=1,
        maximum_total_input_tokens=1_050_000,
        maximum_total_output_tokens=128_000,
        allowed_tools=("read_document", "search_document"),
        maximum_tool_calls=10,
        maximum_tool_output_bytes=100_000,
    )
    source["pricing"].update(
        uncached_input_nanodollars_per_token=5_000,
        cached_input_nanodollars_per_token=400,
        output_nanodollars_per_token=18_000,
    )
    return ProjectModelProfileSpec.model_validate(source)


async def _publish_profile(access, project_id: UUID) -> ProjectModelProfile:
    await access.signed.grant(access.admin, access.target, role="operator")
    spec = _setup_profile(project_id)
    response = await access.signed.client.post(
        f"/api/v1/operations/projects/{project_id}/model-profiles",
        headers=access.target.headers | {"Idempotency-Key": str(uuid4())},
        json=spec.model_dump(mode="json"),
    )
    assert response.status_code == 201, response.text
    budget = await access.signed.client.post(
        f"/api/v1/operations/projects/{project_id}/model-budget-configurations",
        headers=access.target.headers | {"Idempotency-Key": str(uuid4())},
        json={
            "project_id": str(project_id),
            "configuration_version": 1,
            "authorized_total_nanodollars": 10_000_000_000,
            "externally_reconciled_prior_spend_nanodollars": 0,
            "lifetime_limit_nanodollars": 10_000_000_000,
        },
    )
    assert budget.status_code == 201, budget.text
    return ProjectModelProfile.model_validate(response.json())


def _runtime(profile: ProjectModelProfile):
    return runtime_configuration().model_copy(
        update={
            "model_provider": profile.spec.provider,
            "model_api": profile.spec.api,
            "model": profile.spec.model_snapshot,
            "model_profile_id": profile.profile_id,
            "model_profile_version": profile.spec.profile_version,
            "model_profile_digest": profile.profile_digest,
        }
    )


def _preflight(values, requested, configuration):
    attempt_identity = identity(context(values, configuration=configuration))
    complete = replace(
        persistence_facts(values, requested.attempt_id, attempt_identity),
        operation_id=requested.operation_id,
    )
    names = ProjectGuideCompilationExecutePreflightFacts.__dataclass_fields__
    return ProjectGuideCompilationExecutePreflightFacts(
        **{name: asdict(complete)[name] for name in names}
    )


async def _fence_setup_attempt(database_url, values, configuration):
    human, link, _grant = await _seed_human(database_url, values)
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            requested = await _authorized_service(session, actor).authorize_request(
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=actor,
                facts=_request(values, configuration),
                identity=identity(context(values, configuration=configuration)),
                runtime_configuration=configuration,
            )
        async with factory() as session:
            fenced = await _execution_service(session, service_actor(values)).fence_dispatch(
                actor=service_actor(values),
                facts=_preflight(values, requested, configuration),
            )
        assert fenced.dispatch_permitted is True
        return requested
    finally:
        await engine.dispose()


def _provider_request(profile: ProjectModelProfile) -> str:
    return canonical_provider_json(
        {
            "model": profile.spec.model_snapshot,
            "messages": [],
            "max_tokens": profile.spec.maximum_output_tokens,
            "stream": False,
            "tools": [
                {"type": "function", "function": {"name": "read_document"}},
                {"type": "function", "function": {"name": "search_document"}},
            ],
            "usage": {"include": True},
            "reasoning_effort": profile.spec.settings.reasoning_effort,
            "verbosity": profile.spec.settings.text_verbosity,
            **openrouter_request_options(),
        }
    )


async def test_setup_request_and_response_use_verified_minio_custody_and_replay(
    tmp_path,
    isolated_database_env,
    admin_access,  # noqa: F811 - imported fixture is intentionally requested here
    monkeypatch,
) -> None:
    """Persist both private payloads in ART and replay without another provider send."""
    from tests import test_s3_artifact_store
    from tests.test_s3_artifact_store import minio_settings, provision_minio_bucket

    monkeypatch.setattr(
        test_s3_artifact_store,
        "MINIO_BUCKET",
        os.environ["WORKSTREAM_TEST_MINIO_BUCKET"],
    )
    await provision_minio_bucket.__wrapped__()
    settings = minio_settings(private_prefix=f"setup-model/{uuid4()}").model_copy(
        update={
            **artifact_admission_limit_settings(64 * 1024),
            "artifact_scratch_root": tmp_path / "setup-model-scratch",
            "artifact_scratch_minimum_free_bytes": 0,
        }
    )
    bootstrap = create_artifact_store_bootstrap(settings, activation_guard=None)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    store = bootstrap.initialize_after_namespace_claim(
        ArtifactStoreNamespaceClaim(
            bootstrap.identity,
            bootstrap.namespace_identity,
            namespace.namespace_fingerprint,
        )
    )
    manager = ArtifactScratchManager(
        root=tmp_path / "setup-model-preparation",
        limits=artifact_preparation_limits(),
    )
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        values = await seed_database(
            isolated_database_env,
            namespace=namespace,
            provider_object_ref="fixture/guide-source-not-read",
        )
        for service_identity in (
            ServiceIdentity.ARTIFACT_CHECKER_OUTPUT,
            ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            ServiceIdentity.ARTIFACT_VERIFIER,
        ):
            await provision_post_submit_service(factory, service_identity)
        profile = await _publish_profile(admin_access, values["project"])
        configuration = _runtime(profile)
        requested = await _fence_setup_attempt(
            isolated_database_env, values, configuration
        )
        attempt = context(values, configuration=configuration)
        subject = SetupModelProxySubject(
            compilation_attempt_id=requested.attempt_id,
            project_id=values["project"],
            guide_id=values["guide"],
            source_snapshot_id=values["snapshot"],
            setup_run_id=values["setup_1"],
            setup_generation=1,
            runtime_configuration_hash=configuration.sha256,
            profile_id=profile.profile_id,
            profile_version=profile.spec.profile_version,
            profile_digest=profile.profile_digest,
            provider=profile.spec.provider,
            api=profile.spec.api,
            model=profile.spec.model_snapshot,
        )
        assert attempt.setup_run_id == subject.setup_run_id
        request = SetupModelProxyRequest(
            subject=subject,
            phase="draft",
            call_index=0,
            provider_request_json=_provider_request(profile),
        )
        response_marker = f"private-setup-response-{uuid4()}"
        response_json = canonical_provider_json(
            {
                "id": "setup-response-1",
                "model": profile.spec.model_snapshot,
                "choices": [{"message": {"content": response_marker}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        )
        provider_calls = 0
        reserve_observations: list[tuple[str, str, str]] = []

        class Provider:
            async def count_input(self, _body):
                return 1

            async def dispatch(self, _body):
                nonlocal provider_calls
                provider_calls += 1
                assert reserve_observations == [
                    ("setup_model_call", "model_request", "verified")
                ]
                return SetupProviderResponse(
                    status_code=200,
                    response_json=response_json,
                    provider_response_id="setup-response-1",
                    provider_model=profile.spec.model_snapshot,
                    usage=ModelCallUsage(
                        input_tokens=1,
                        cached_input_tokens=0,
                        output_tokens=1,
                        reasoning_tokens=0,
                    ),
                )

        @asynccontextmanager
        async def provider(_profile):
            yield Provider()

        def calls(session, authority):
            owner = setup_model_usage_service(
                session,
                authority=authority,
                evidence=setup_model_evidence(session),
                owner=setup_model_usage_owner(session),
            )

            class ObservedCalls:
                def __getattr__(self, name):
                    return getattr(owner, name)

                async def reserve_dispatch(self, prepared, request_evidence):
                    row = (
                        await session.execute(
                            text(
                                "select binding.resource_type,binding.logical_role,receipt.outcome "
                                "from artifact_bindings binding "
                                "join artifact_verification_receipts receipt "
                                "on receipt.id=binding.verification_receipt_id "
                                "where binding.id=:binding and binding.resource_id=:effect"
                            ),
                            {
                                "binding": str(request_evidence.binding_id),
                                "effect": str(prepared.effect_id),
                            },
                        )
                    ).one()
                    reserve_observations.append(tuple(row))
                    return await owner.reserve_dispatch(prepared, request_evidence)

            return ObservedCalls()

        preparation = ArtifactPreparationService(manager)
        outputs = setup_model_output_storage(
            sessions=factory,
            store=store,
            namespace=namespace,
            preparation=preparation,
            settings=settings,
            owner=setup_model_usage_owner,
        )

        def handler() -> SetupModelProxyHandler:
            return SetupModelProxyHandler(
                sessions=factory,
                authorization=setup_model_service_authorization,
                calls=calls,
                profiles=model_profile_reader,
                outputs=outputs,
                bindings=lambda session: setup_model_output_binding(
                    session,
                    namespace=namespace,
                    owner=setup_model_usage_owner(session),
                ),
                provider=provider,
            )

        first = await handler().handle(request)
        assert first.outcome == "completed"
        assert first.response_json == response_json
        assert provider_calls == 1

        async with factory() as session:
            state = (
                await session.execute(
                    text(
                        "select effect.id,effect.state,effect.request_binding_id,"
                        "effect.response_binding_id,effect.settled_nanodollars,"
                        "account.lifetime_reserved_nanodollars,"
                        "account.lifetime_settled_nanodollars "
                        "from model_usage_effects effect "
                        "join setup_model_usage_slots slot on slot.id=effect.setup_slot_id "
                        "join model_usage_budget_accounts account on account.project_id=slot.project_id "
                        "where slot.compilation_attempt_id=:attempt"
                    ),
                    {"attempt": str(requested.attempt_id)},
                )
            ).one()
            bindings = (
                await session.execute(
                    text(
                        "select binding.logical_role,binding.resource_id,receipt.outcome "
                        "from artifact_bindings binding "
                        "join artifact_verification_receipts receipt "
                        "on receipt.id=binding.verification_receipt_id "
                        "where binding.resource_type='setup_model_call' "
                        "and binding.resource_id=:effect order by binding.logical_role"
                    ),
                    {"effect": str(state.id)},
                )
            ).all()
            assert [tuple(row) for row in bindings] == [
                ("model_request", str(state.id), "verified"),
                ("model_response", str(state.id), "verified"),
            ]
            assert state.state == "completed"
            assert state.request_binding_id is not None
            assert state.response_binding_id is not None
            assert state.lifetime_reserved_nanodollars == 0
            assert state.lifetime_settled_nanodollars == state.settled_nanodollars
            settled = state.lifetime_settled_nanodollars
            for table in (
                "model_usage_effects",
                "artifact_contents",
                "artifact_put_attempts",
                "artifact_operation_receipts",
                "artifact_verification_receipts",
                "artifact_bindings",
                "audit_events",
            ):
                leaked = await session.scalar(
                    text(
                        f"select exists(select 1 from {table} row "
                        "where to_jsonb(row)::text like :needle)"
                    ),
                    {"needle": f"%{response_marker}%"},
                )
                assert leaked is False, table

        replay = await handler().handle(request)
        assert replay == first
        assert provider_calls == 1
        async with factory() as session:
            replay_state = (
                await session.execute(
                    text(
                        "select count(*) as effects,min(state) as state,"
                        "min(settled_nanodollars) as settled from model_usage_effects effect "
                        "join setup_model_usage_slots slot on slot.id=effect.setup_slot_id "
                        "where slot.compilation_attempt_id=:attempt"
                    ),
                    {"attempt": str(requested.attempt_id)},
                )
            ).one()
            assert replay_state == (1, "completed", settled)
    finally:
        manager.close()
        bootstrap.close()
        await engine.dispose()
