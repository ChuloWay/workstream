"""Real ART replacement comparison against one retained consumed Submission."""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest
from sqlalchemy import text
from starlette.requests import Request

from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.adapters.artifacts import get_submission_bundle_preparation_command
from app.adapters.tasks import task_post_submit_outcome
from app.adapters.artifacts.local import LocalStorageAdapter
from app.core.identifiers import new_record_id
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.artifacts.api import (
    SubmissionBundlePreparationCheckFailed,
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationRequest,
)
from app.modules.artifacts.authorization import (
    PreparedArtifactInternalAuthority,
    PreparedSubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.models import (
    PreSubmitEvidenceSet,
    SubmissionBundleAdmission,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionChangeFailureCode,
    SubmissionChangeRejectedError,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.api.submission_context import (
    TaskSubmissionContextRequest,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import SubmissionDispatch
from app.adapters.tasks import task_submission_context_port
from tests.artifact_store_helpers import artifact_byte_stream
from tests.checkers.execution.support import reserve
from tests.checkers.execution.completion_fixture import completed_evidence
from tests.tasks.post_submit_routing.remediation_support import (
    no_economic_effects,
    remediation_source,
)
from tests.tasks.post_submit_routing.support import next_request, revision_archive
from tests.tasks.submission_lineage_support import _verified_admission


_PREPARATION_TABLES = (
    "pre_submit_execution_attempts",
    "pre_submit_evidence_sets",
    "pre_submit_evidence_results",
    "submission_bundle_durable_intents",
    "artifact_put_attempts",
    "artifact_put_attempt_charges",
    "artifact_contents",
    "artifact_replicas",
    "artifact_operation_receipts",
    "artifact_put_observation_receipts",
    "artifact_verification_jobs",
    "artifact_verification_receipts",
    "submission_bundle_admissions",
)


def _trace_provider_writes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    for operation in ("put", "observe_put_result"):
        original = getattr(LocalStorageAdapter, operation)

        async def traced(self, *args, _original=original, _operation=operation, **kwargs):
            calls.append(_operation)
            return await _original(self, *args, **kwargs)

        monkeypatch.setattr(LocalStorageAdapter, operation, traced)
    return calls


def _http_request(settings) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [],
            "app": SimpleNamespace(
                state=SimpleNamespace(
                    settings=settings,
                    pre_submission_checker_catalogue=(build_pre_submission_checker_catalogue()),
                )
            ),
        }
    )


def _replacement_request(h, data: bytes, *, predecessor_id: UUID, idempotency_key: UUID):
    return SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            h.actor_context.actor_profile_id,
            h.actor_context.identity_link_id,
            ActorKind.HUMAN,
        ),
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        predecessor_submission_id=predecessor_id,
        idempotency_key=idempotency_key,
        summary=h.request.structural_input.summary,
        contributor_attestation=h.request.structural_input.worker_attestation,
        media_type="application/zip",
        byte_source=artifact_byte_stream(data),
    )


async def _prepare(h, request: SubmissionBundlePreparationRequest):
    http = _http_request(h.settings)
    async with h.factory() as session:
        internal = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        )
        return await get_submission_bundle_preparation_command(
            http,
            session,
            internal,
            PreparedSubmissionBundlePreparationAuthorization(session, h.actor_context),
        ).prepare(request)


async def _snapshot(h) -> tuple[tuple[str, int], ...]:
    async with h.factory() as session:
        rows = []
        for table in _PREPARATION_TABLES:
            count = await session.scalar(text(f"SELECT pg_catalog.count(*) FROM public.{table}"))
            assert count is not None
            rows.append((table, int(count)))
        return tuple(rows)


async def _fixture_revision_context(h):
    """Commit the real routed checker failure before replacement intake."""
    async with h.factory() as session, session.begin():
        outcome = task_post_submit_outcome(session, h.factory)
        assert await outcome.observe_delivery_generation(h.envelope) is None
        result = await outcome.apply(h.envelope, current_generation=None)
        assert result.routing_recommendation == "needs_revision"
    async with h.factory() as session:
        source = (await session.execute(text("""
            SELECT m.id,m.submission_id,m.assignment_id,m.routing_recommendation,
              t.status AS task_status,a.status AS assignment_status,
              public.task_routing_outcome_complete(m) AS complete
            FROM public.task_post_submit_routing_manifests m
            JOIN public.workstream_tasks t ON t.id=m.task_id
            JOIN public.task_assignments a ON a.id=m.assignment_id
            WHERE m.id=:id
        """), {"id": result.routing_manifest_id})).mappings().one()
        assert source["submission_id"] == h.created.submission_id
        assert source["assignment_id"] == h.request.assignment_id
        assert source["routing_recommendation"] == source["task_status"] == "needs_revision"
        assert source["assignment_status"] == "active" and source["complete"] is True
        await no_economic_effects(session)
    return result.routing_manifest_id


def _same_semantics_different_archive(data: bytes) -> bytes:
    repacked = BytesIO(data)
    with ZipFile(repacked, "a") as archive:
        archive.comment = b"different archive bytes; identical governed members"
    result = repacked.getvalue()
    assert result != data
    return result


async def _assert_dispatch_valid(h) -> None:
    async with h.factory() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT public.submission_dispatch_valid(dispatch) "
                    "FROM public.submission_dispatches dispatch "
                    "WHERE submission_id=:submission_id"
                ),
                {"submission_id": h.created.submission_id},
            )
            is True
        )


async def _forbidden_bytes():
    pytest.fail("rejected replacement consumed contributor ZIP bytes")
    yield b""


def _context_request(h) -> TaskSubmissionContextRequest:
    return TaskSubmissionContextRequest(
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        contributor_id=h.actor_context.actor_profile_id,
        predecessor_submission_id=h.created.submission_id,
    )


@pytest.mark.parametrize("human_review_required", [True, False])
async def test_real_replacement_compares_consumed_predecessor_and_replays_exactly(
    tmp_path,
    isolated_database_env,
    monkeypatch,
    human_review_required,
):
    provider_writes = _trace_provider_writes(monkeypatch)
    loaded = []
    original_load = PreparedSubmissionBundlePreparationCommand._load_predecessor

    async def traced_load(self, task_context):
        predecessor = await original_load(self, task_context)
        loaded.append((task_context.predecessor, predecessor))
        return predecessor

    monkeypatch.setattr(
        PreparedSubmissionBundlePreparationCommand,
        "_load_predecessor",
        traced_load,
    )

    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=human_review_required,
    ) as h:
        await _assert_dispatch_valid(h)
        provider_writes.clear()
        before_route = await _snapshot(h)
        with pytest.raises(
            SubmissionBundlePreparationRejected,
            match="submission_bundle_preparation_context_changed",
        ):
            await _prepare(h, replace(
                _replacement_request(
                    h, revision_archive(h.data), predecessor_id=h.created.submission_id,
                    idempotency_key=new_record_id(),
                ),
                byte_source=_forbidden_bytes(),
            ))
        assert await _snapshot(h) == before_route
        assert provider_writes == []
        source_id = await _fixture_revision_context(h)
        provider_writes.clear()
        loaded.clear()

        baseline = await _snapshot(h)
        predecessor_id = h.created.submission_id
        for data, expected in (
            (h.data, SubmissionChangeFailureCode.ARCHIVE_UNCHANGED),
            (
                _same_semantics_different_archive(h.data),
                SubmissionChangeFailureCode.MANIFEST_UNCHANGED,
            ),
        ):
            request = _replacement_request(
                h,
                data,
                predecessor_id=predecessor_id,
                idempotency_key=new_record_id(),
            )
            with pytest.raises(SubmissionChangeRejectedError) as failure:
                await _prepare(h, request)
            assert failure.value.code is expected
            assert await _snapshot(h) == baseline
            assert provider_writes == []

        changed_data = revision_archive(h.data)
        with pytest.raises(SubmissionBundlePreparationCheckFailed) as blocked:
            await _prepare(h, replace(
                _replacement_request(
                    h, changed_data, predecessor_id=predecessor_id,
                    idempotency_key=new_record_id(),
                ),
                contributor_attestation="",
            ))
        assert blocked.value.facts.eligible is False
        assert any(entry.checker_execution_status == "failed"
                   for entry in blocked.value.facts.entries)
        assert provider_writes == []
        async with h.factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM public.submissions")) == 1
            assert await session.scalar(text(
                "SELECT status FROM public.workstream_tasks WHERE id=:id"
            ), {"id": h.request.task_id}) == "needs_revision"
        idempotency_key = new_record_id()
        changed_request = _replacement_request(
            h,
            changed_data,
            predecessor_id=predecessor_id,
            idempotency_key=idempotency_key,
        )
        admission_id = await _verified_admission(
            h.factory,
            h.store,
            h.namespace,
            h.settings,
            h.actor_context,
            changed_request,
        )
        assert provider_writes == ["put"]

        async with h.factory() as session:
            predecessor_admission = await session.get(
                SubmissionBundleAdmission, str(h.creation_request.admission_id)
            )
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            evidence = await session.get(PreSubmitEvidenceSet, admission.pre_submit_evidence_set_id)
            assert predecessor_admission.status == "consumed"
            assert admission.status == "ready"
            assert admission.predecessor_submission_id == str(predecessor_id)
            assert admission.predecessor_submission_version == 1
            assert admission.checker_remediation_manifest_id == str(source_id)
            assert evidence.predecessor_submission_id == str(predecessor_id)
            assert evidence.predecessor_submission_version == 1
            assert evidence.checker_remediation_manifest_id == str(source_id)
            assert admission.archive_sha256 != predecessor_admission.archive_sha256
            assert (
                admission.semantic_manifest_sha256 != predecessor_admission.semantic_manifest_sha256
            )

        ready = await _snapshot(h)
        replay = await _prepare(
            h,
            _replacement_request(
                h,
                changed_data,
                predecessor_id=predecessor_id,
                idempotency_key=idempotency_key,
            ),
        )
        assert replay.replayed is True
        assert replay.admission_id == admission_id
        assert await _snapshot(h) == ready
        assert provider_writes == ["put"]

        async with h.factory() as session:
            immutable_before = (await session.execute(text("""
                SELECT (SELECT to_jsonb(s) FROM public.submissions s WHERE s.id=:prior),
                  (SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m WHERE m.id=:cause),
                  (SELECT to_jsonb(r) FROM public.checker_results r WHERE r.id=:result)
            """), {"prior": predecessor_id, "cause": source_id,
                   "result": h.completion.reference.result_id})).one()
        creation = SubmissionCreationRequest(
            task_id=h.request.task_id,
            assignment_id=h.request.assignment_id,
            contributor_id=h.actor_context.actor_profile_id,
            predecessor_submission_id=predecessor_id,
            admission_id=admission_id,
            summary=changed_request.summary,
            contributor_attestation=changed_request.contributor_attestation,
        )
        async with h.factory() as session:
            created = await compose_hidden_submission_creation_command(
                session, h.actor_context, request_id=new_record_id(),
                correlation_id=new_record_id(),
            ).create(creation)
        assert created.submission_version == 2
        async with h.factory() as session:
            receipt = await session.get(SubmissionDispatch, str(created.submission_id))
            assert receipt is not None
            assert receipt.creation_kind == "checker_remediation"
            assert receipt.checker_remediation_manifest_id == source_id
            assert await session.scalar(text("""
                SELECT public.submission_dispatch_valid(d) FROM public.submission_dispatches d
                WHERE d.submission_id=:id
            """), {"id": created.submission_id}) is True
            dispatch_body = await session.scalar(text(
                "SELECT to_jsonb(d) FROM public.submission_dispatches d WHERE submission_id=:id"
            ), {"id": created.submission_id})
            validate = text(
                "SELECT public.submission_dispatch_valid("
                "pg_catalog.jsonb_populate_record(NULL::public.submission_dispatches, "
                "CAST(:body AS jsonb)))"
            )
            for field, substituted in (
                ("checker_remediation_manifest_id", None),
                ("checker_remediation_manifest_id", str(new_record_id())),
                ("creation_decision_id", str(h.created.creation_decision_id)),
                ("binding_decision_id", str(h.created.binding_decision_id)),
            ):
                assert await session.scalar(
                    validate, {"body": json.dumps(dispatch_body | {field: substituted})}
                ) is False, field
            immutable_after = (await session.execute(text("""
                SELECT (SELECT to_jsonb(s) FROM public.submissions s WHERE s.id=:prior),
                  (SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m WHERE m.id=:cause),
                  (SELECT to_jsonb(r) FROM public.checker_results r WHERE r.id=:result)
            """), {"prior": predecessor_id, "cause": source_id,
                   "result": h.completion.reference.result_id})).one()
            assert immutable_after == immutable_before
            await no_economic_effects(session)
        async with h.factory() as session:
            assert await compose_hidden_submission_creation_command(
                session, h.actor_context, request_id=new_record_id(),
                correlation_id=new_record_id(),
            ).create(creation) == created

        assert len(loaded) == 5
        for task_predecessor, artifact_predecessor in loaded:
            assert task_predecessor.submission_id == predecessor_id
            assert task_predecessor.version == 1
            assert artifact_predecessor.submission_id == predecessor_id
            assert artifact_predecessor.submission_version == 1
            assert artifact_predecessor.archive_sha256 == predecessor_admission.archive_sha256
            assert (
                artifact_predecessor.semantic_manifest_sha256
                == predecessor_admission.semantic_manifest_sha256
            )


async def test_foreign_predecessor_stops_at_task_context_before_art_effects(
    tmp_path,
    isolated_database_env,
    monkeypatch,
):
    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path / "local", isolated_database_env) as local:
        async with remediation_source(
            tmp_path / "foreign",
            isolated_database_env,
            provision_services=False,
            storage_settings=local.settings,
        ) as foreign:
            await _assert_dispatch_valid(local)
            await _assert_dispatch_valid(foreign)
            local_source = await _fixture_revision_context(local)
            foreign_source = await _fixture_revision_context(foreign)
            async with local.factory.begin() as session:
                contexts = task_submission_context_port(session)
                own = _context_request(local)
                assert (await contexts.lock_submission_context(
                    own
                )).checker_remediation_manifest_id == local_source
                for field, value in (
                    ("task_id", foreign.request.task_id),
                    ("assignment_id", foreign.request.assignment_id),
                    ("contributor_id", foreign.actor_context.actor_profile_id),
                    ("predecessor_submission_id", foreign.created.submission_id),
                ):
                    with pytest.raises(TaskSubmissionContextUnavailable):
                        await contexts.lock_submission_context(replace(own, **{field: value}))
            provider_writes.clear()
            baseline = await _snapshot(local)

            async def forbidden_load(*_args, **_kwargs):
                pytest.fail("foreign predecessor reached ART predecessor loading")

            original_load = PreparedSubmissionBundlePreparationCommand._load_predecessor
            monkeypatch.setattr(
                PreparedSubmissionBundlePreparationCommand,
                "_load_predecessor",
                forbidden_load,
            )
            request = _replacement_request(
                local,
                revision_archive(local.data),
                predecessor_id=foreign.created.submission_id,
                idempotency_key=new_record_id(),
            )
            with pytest.raises(
                SubmissionBundlePreparationRejected,
                match="submission_bundle_preparation_context_changed",
            ):
                await _prepare(local, request)
            assert await _snapshot(local) == baseline
            assert provider_writes == []
            monkeypatch.setattr(
                PreparedSubmissionBundlePreparationCommand,
                "_load_predecessor",
                original_load,
            )

            changed_data = revision_archive(local.data)
            admission_id = await _verified_admission(
                local.factory, local.store, local.namespace, local.settings,
                local.actor_context,
                _replacement_request(
                    local, changed_data, predecessor_id=local.created.submission_id,
                    idempotency_key=new_record_id(),
                ),
            )
            async with local.factory() as session:
                created = await compose_hidden_submission_creation_command(
                    session, local.actor_context, request_id=new_record_id(),
                    correlation_id=new_record_id(),
                ).create(SubmissionCreationRequest(
                    task_id=local.request.task_id,
                    assignment_id=local.request.assignment_id,
                    contributor_id=local.actor_context.actor_profile_id,
                    predecessor_submission_id=local.created.submission_id,
                    admission_id=admission_id,
                    summary=local.creation_request.summary,
                    contributor_attestation=local.creation_request.contributor_attestation,
                ))
            async with local.factory() as session:
                body = await session.scalar(text(
                    "SELECT to_jsonb(d) FROM public.submission_dispatches d WHERE submission_id=:id"
                ), {"id": created.submission_id})
                assert body["checker_remediation_manifest_id"] == str(local_source)
                validate = text(
                    "SELECT public.submission_dispatch_valid("
                    "pg_catalog.jsonb_populate_record(NULL::public.submission_dispatches, "
                    "CAST(:body AS jsonb)))"
                )
                assert await session.scalar(validate, {"body": json.dumps(body)}) is True
                assert await session.scalar(validate, {"body": json.dumps(
                    body | {"checker_remediation_manifest_id": str(foreign_source)}
                )}) is False


@pytest.mark.parametrize("recommendation", ["task_setup_blocked", "allow_review"])
async def test_setup_fault_or_success_cannot_authorize_replacement_before_bytes(
    tmp_path, isolated_database_env, monkeypatch, recommendation,
):
    provider_writes = _trace_provider_writes(monkeypatch)
    async with completed_evidence(tmp_path, isolated_database_env, recommendation) as h:
        assert h.run.routing_recommendation == recommendation
        before = await _snapshot(h)
        provider_writes.clear()
        with pytest.raises(
            SubmissionBundlePreparationRejected,
            match="submission_bundle_preparation_context_changed",
        ):
            await _prepare(h, replace(
                _replacement_request(
                    h, revision_archive(h.data), predecessor_id=h.created.submission_id,
                    idempotency_key=new_record_id(),
                ),
                byte_source=_forbidden_bytes(),
            ))
        assert await _snapshot(h) == before
        assert provider_writes == []


async def test_source_superseded_during_zip_read_stops_before_art_effects(
    tmp_path, isolated_database_env, monkeypatch,
):
    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        async with h.factory.begin() as session:
            current = await task_submission_context_port(session).lock_submission_context(
                _context_request(h)
            )
            assert current.checker_remediation_manifest_id == source_id
        before = await _snapshot(h)
        provider_writes.clear()
        opened = []

        async def superseding_bytes():
            opened.append(True)
            await reserve(h, await next_request(h))
            yield revision_archive(h.data)

        with pytest.raises(
            SubmissionBundlePreparationRejected,
            match="submission_bundle_preparation_context_changed",
        ):
            await _prepare(h, replace(
                _replacement_request(
                    h, revision_archive(h.data), predecessor_id=h.created.submission_id,
                    idempotency_key=new_record_id(),
                ),
                byte_source=superseding_bytes(),
            ))
        assert opened == [True]
        assert await _snapshot(h) == before
        assert provider_writes == []
        async with h.factory.begin() as session:
            with pytest.raises(TaskSubmissionContextUnavailable):
                await task_submission_context_port(session).lock_submission_context(
                    _context_request(h)
                )
