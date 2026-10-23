"""Real PostgreSQL and MinIO custody for one setup-model provider call."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, replace
import json
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

from asyncpg.pgproto.pgproto import UUID as AsyncpgUUID
import pytest
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
from app.core.identifiers import new_record_id
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
    ModelCallUnavailable,
    ModelCallUsage,
    ModelUsageEffectInspection,
    ProjectModelProfile,
    ProjectModelProfileSpec,
)
from app.modules.projects.guide_compilation.orchestrator import _setup_model_subject
from app.modules.projects.guide_compilation.service import (
    load_compilation_execution_state,
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
    return ProjectModelProfile.model_validate_json(json.dumps(response.json()))


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


def test_setup_subject_normalizes_database_uuid_subclasses_at_owner_projection() -> None:
    """Keep the wire exact while accepting UUID values returned by asyncpg."""
    configuration_type = type(runtime_configuration())
    configuration = configuration_type.model_validate(
        runtime_configuration().model_dump(mode="json")
        | {
            "model_profile_id": str(new_record_id()),
            "model_profile_version": 1,
            "model_profile_digest": "sha256:" + "1" * 64,
        }
    )
    database_ids = {
        name: AsyncpgUUID(str(new_record_id()))
        for name in (
            "attempt",
            "project",
            "guide",
            "snapshot",
            "setup",
        )
    }
    raw = dict(
        compilation_attempt_id=database_ids["attempt"],
        project_id=database_ids["project"],
        guide_id=database_ids["guide"],
        source_snapshot_id=database_ids["snapshot"],
        setup_run_id=database_ids["setup"],
        setup_generation=1,
        runtime_configuration_hash=configuration.sha256,
        profile_id=configuration.model_profile_id,
        profile_version=configuration.model_profile_version,
        profile_digest=configuration.model_profile_digest,
        provider=configuration.model_provider,
        api=configuration.model_api,
        model=configuration.model,
    )
    assert all(isinstance(value, UUID) and type(value) is not UUID for value in database_ids.values())
    with pytest.raises(ValueError, match="subject is invalid"):
        SetupModelProxySubject(**raw)

    state = SimpleNamespace(
        preflight_facts=SimpleNamespace(attempt_id=database_ids["attempt"]),
        identity=SimpleNamespace(
            project_id=database_ids["project"],
            guide_id=database_ids["guide"],
            source_snapshot_id=database_ids["snapshot"],
            setup_run_id=database_ids["setup"],
            setup_generation=1,
        ),
    )
    subject = _setup_model_subject(state, configuration)

    assert subject is not None
    assert all(
        type(getattr(subject, name)) is UUID
        for name in (
            "compilation_attempt_id",
            "project_id",
            "guide_id",
            "source_snapshot_id",
            "setup_run_id",
            "profile_id",
        )
    )
    assert str(subject.compilation_attempt_id) == str(database_ids["attempt"])


@dataclass(slots=True)
class _StorageCase:
    database_url: str
    factory: object
    engine: object
    bootstrap: object
    manager: ArtifactScratchManager
    settings: object
    namespace: object
    store: object
    values: dict


@asynccontextmanager
async def _storage_case(tmp_path, database_url, monkeypatch) -> AsyncIterator[_StorageCase]:
    """Own one real MinIO namespace and its exact PostgreSQL namespace row."""
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
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        values = await seed_database(
            database_url,
            namespace=namespace,
            provider_object_ref="fixture/guide-source-not-read",
        )
        for service_identity in (
            ServiceIdentity.ARTIFACT_CHECKER_OUTPUT,
            ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            ServiceIdentity.ARTIFACT_VERIFIER,
        ):
            await provision_post_submit_service(factory, service_identity)
        yield _StorageCase(
            database_url,
            factory,
            engine,
            bootstrap,
            manager,
            settings,
            namespace,
            store,
            values,
        )
    finally:
        manager.close()
        bootstrap.close()
        await engine.dispose()


@dataclass(slots=True)
class _Journey:
    storage: _StorageCase
    profile: ProjectModelProfile
    request: SetupModelProxyRequest
    response_json: str
    response_marker: str
    provider_calls: list[str]
    reserve_observations: list[tuple[str, str, str]]
    fail_completion: list[bool]
    outputs: object

    def handler(self) -> SetupModelProxyHandler:
        return SetupModelProxyHandler(
            sessions=self.storage.factory,
            authorization=setup_model_service_authorization,
            calls=lambda session, authority: _ObservedCalls(session, authority, self),
            profiles=model_profile_reader,
            outputs=self.outputs,
            bindings=lambda session: setup_model_output_binding(
                session,
                namespace=self.storage.namespace,
                owner=setup_model_usage_owner(session),
            ),
            provider=lambda profile: _provider(self, profile),
        )


class _Provider:
    def __init__(self, journey: _Journey) -> None:
        self.journey = journey

    async def count_input(self, _body):
        return 1

    async def dispatch(self, _body):
        self.journey.provider_calls.append("dispatch")
        assert self.journey.reserve_observations == [
            ("setup_model_call", "model_request", "verified")
        ]
        return SetupProviderResponse(
            status_code=200,
            response_json=self.journey.response_json,
            provider_response_id="setup-response-1",
            provider_model=self.journey.profile.spec.model_snapshot,
            usage=ModelCallUsage(
                input_tokens=1,
                cached_input_tokens=0,
                output_tokens=1,
                reasoning_tokens=0,
            ),
        )


@asynccontextmanager
async def _provider(journey: _Journey, _profile) -> AsyncIterator[_Provider]:
    yield _Provider(journey)


class _ObservedCalls:
    def __init__(self, session, authority, journey: _Journey) -> None:
        self.session = session
        self.journey = journey
        self.owner = setup_model_usage_service(
            session,
            authority=authority,
            evidence=setup_model_evidence(session),
            owner=setup_model_usage_owner(session),
        )

    def __getattr__(self, name):
        return getattr(self.owner, name)

    async def reserve_dispatch(self, prepared, request_evidence):
        row = (
            await self.session.execute(
                text(
                    "select binding.resource_type,binding.logical_role,receipt.outcome "
                    "from artifact_bindings binding join artifact_verification_receipts receipt "
                    "on receipt.id=binding.verification_receipt_id "
                    "where binding.id=:binding and binding.resource_id=:effect"
                ),
                {
                    "binding": str(request_evidence.binding_id),
                    "effect": str(prepared.effect_id),
                },
            )
        ).one()
        self.journey.reserve_observations.append(tuple(row))
        return await self.owner.reserve_dispatch(prepared, request_evidence)

    async def complete(self, *args, **kwargs):
        if self.journey.fail_completion[0]:
            self.journey.fail_completion[0] = False
            raise ModelCallUnavailable("simulated_setup_ledger_unavailable")
        return await self.owner.complete(*args, **kwargs)


async def _journey(storage: _StorageCase, access) -> _Journey:
    profile = await _publish_profile(access, storage.values["project"])
    configuration = _runtime(profile)
    requested = await _fence_setup_attempt(
        storage.database_url, storage.values, configuration
    )
    async with storage.factory() as session:
        state = await load_compilation_execution_state(session, requested.attempt_id)
    assert state.runtime_configuration == configuration
    subject = _setup_model_subject(state, configuration)
    assert subject is not None
    assert subject.profile_id == profile.profile_id
    request = SetupModelProxyRequest(
        subject, "draft", 0, _provider_request(profile)
    )
    marker = f"private-setup-response-{uuid4()}"
    response = canonical_provider_json(
        {
            "id": "setup-response-1",
            "model": profile.spec.model_snapshot,
            "choices": [{"message": {"content": marker}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    outputs = setup_model_output_storage(
        sessions=storage.factory,
        store=storage.store,
        namespace=storage.namespace,
        preparation=ArtifactPreparationService(storage.manager),
        settings=storage.settings,
        owner=setup_model_usage_owner,
    )
    return _Journey(storage, profile, request, response, marker, [], [], [True], outputs)


async def _state(journey: _Journey):
    async with journey.storage.factory() as session:
        return (
            await session.execute(
                text(
                    "select effect.id,effect.state,effect.request_binding_id,"
                    "effect.request_content_id,effect.request_put_attempt_id,"
                    "effect.request_verification_receipt_id,effect.request_content_sha256,"
                    "effect.request_byte_count,effect.response_binding_id,"
                    "effect.response_content_id,effect.response_put_attempt_id,"
                    "effect.response_verification_receipt_id,effect.response_content_sha256,"
                    "effect.response_byte_count,effect.settled_nanodollars,"
                    "account.lifetime_reserved_nanodollars,"
                    "account.lifetime_settled_nanodollars "
                    "from model_usage_effects effect "
                    "join setup_model_usage_slots slot on slot.id=effect.setup_slot_id "
                    "join model_usage_budget_accounts account on account.project_id=slot.project_id "
                    "where slot.compilation_attempt_id=:attempt"
                ),
                {"attempt": str(journey.request.subject.compilation_attempt_id)},
            )
        ).one()


async def _assert_bound_private_art(journey: _Journey, state) -> None:
    async with journey.storage.factory() as session:
        bindings = (
            await session.execute(
                text(
                    "select binding.logical_role,binding.resource_id,receipt.outcome "
                    "from artifact_bindings binding join artifact_verification_receipts receipt "
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
                {"needle": f"%{journey.response_marker}%"},
            )
            assert leaked is False, table


def _assert_evidence_identity(observed, state, role: str) -> None:
    assert observed is not None
    for field in ("binding_id", "content_id", "put_attempt_id", "verification_receipt_id"):
        assert str(getattr(observed, field)) == str(getattr(state, f"{role}_{field}"))
    assert observed.content_sha256 == getattr(state, f"{role}_content_sha256")
    assert observed.byte_count == getattr(state, f"{role}_byte_count")


async def _assert_operator_inspection(journey: _Journey, state, access) -> None:
    endpoint = (
        f"/api/v1/operations/projects/{journey.request.subject.project_id}"
        f"/model-usage/effects/{state.id}"
    )
    response = await access.signed.client.get(endpoint, headers=access.target.headers)
    assert response.status_code == 200, response.text
    observed = ModelUsageEffectInspection.model_validate_json(response.text)
    assert observed.project_id == journey.request.subject.project_id
    assert observed.effect_id == UUID(str(state.id))
    assert observed.owner_kind == "setup"
    assert observed.owner.compilation_attempt_id == journey.request.subject.compilation_attempt_id
    assert observed.state == "completed"
    assert observed.provider_response_known is True
    assert observed.usage == ModelCallUsage(
        input_tokens=1,
        cached_input_tokens=0,
        output_tokens=1,
        reasoning_tokens=0,
    )
    assert observed.settled_nanodollars == 23_000
    _assert_evidence_identity(observed.request_evidence, state, "request")
    _assert_evidence_identity(observed.response_evidence, state, "response")
    assert journey.response_marker not in response.text
    assert "setup-response-1" not in response.text
    assert "provider_response_id" not in response.json()

    wrong_project = await access.signed.client.get(
        endpoint.replace(str(journey.request.subject.project_id), str(new_record_id())),
        headers=access.target.headers,
    )
    assert wrong_project.status_code == 404, wrong_project.text
    missing = await access.signed.client.get(
        endpoint.rsplit("/", 1)[0] + f"/{new_record_id()}",
        headers=access.target.headers,
    )
    assert missing.status_code == 404, missing.text


async def test_setup_response_recovers_from_verified_minio_after_ledger_loss(
    tmp_path,
    isolated_database_env,
    admin_access,  # noqa: F811 - imported fixture is intentionally requested here
    monkeypatch,
) -> None:
    """Recover exact response ART after a crash boundary without a second send."""
    async with _storage_case(tmp_path, isolated_database_env, monkeypatch) as storage:
        journey = await _journey(storage, admin_access)
        first = await journey.handler().handle(journey.request)
        assert first.outcome == "unavailable"
        uncertain = await _state(journey)
        assert uncertain.state == "uncertain"
        assert uncertain.response_binding_id is None
        assert uncertain.lifetime_reserved_nanodollars > 0
        assert uncertain.lifetime_settled_nanodollars == 0
        await _assert_bound_private_art(journey, uncertain)

        recovered = await journey.handler().handle(journey.request)
        assert recovered.outcome == "completed"
        assert recovered.response_json == journey.response_json
        completed = await _state(journey)
        assert completed.state == "completed"
        assert completed.request_binding_id is not None
        assert completed.response_binding_id is not None
        assert completed.lifetime_reserved_nanodollars == 0
        assert completed.settled_nanodollars == 23_000
        assert completed.lifetime_settled_nanodollars == 23_000
        await _assert_bound_private_art(journey, completed)
        await _assert_operator_inspection(journey, completed, admin_access)

        replay = await journey.handler().handle(journey.request)
        assert replay == recovered
        assert journey.provider_calls == ["dispatch"]
        assert await _state(journey) == completed
