"""Real ART replacement comparison against one retained consumed Submission."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from io import BytesIO
import json
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.adapters.checkers import evaluation_coordinator
from app.adapters.artifacts import get_submission_bundle_preparation_command
from app.adapters.tasks import task_post_submit_outcome
from app.adapters.artifacts.local import LocalStorageAdapter
from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
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
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.artifacts.models import (
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
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.api.submission_context import (
    TaskSubmissionContextRequest, TaskSubmissionContextUnavailable,
)
from app.modules.tasks.models import SubmissionDispatch
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from app.modules.tasks.submission_context import TaskSubmissionContextService
from app.adapters.tasks import task_submission_context_port
from tests.auth_concurrency_support import wait_for_named_database_lock
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
    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=human_review_required,
    ) as h:
        await _assert_dispatch_valid(h)
        source_id = await _fixture_revision_context(h)
        provider_writes.clear()
        predecessor_id = h.created.submission_id
        changed_data = revision_archive(h.data)
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
            selected = await session.get(SelectedPreSubmitRun, admission.selected_pre_submit_run_id)
            assert predecessor_admission.status == "consumed"
            assert admission.status == "ready"
            assert admission.predecessor_submission_id == str(predecessor_id)
            assert admission.predecessor_submission_version == 1
            assert admission.checker_remediation_manifest_id == source_id
            assert admission.pre_submit_evidence_set_id is None
            assert selected is not None and selected.eligible
            lineage = selected.request_json["admission_lineage"]
            assert lineage["predecessor_submission_id"] == str(predecessor_id)
            assert lineage["predecessor_submission_version"] == 1
            assert lineage["checker_remediation_manifest_id"] == str(source_id)
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


async def test_replacement_without_routed_cause_denied_before_bytes(
    tmp_path, isolated_database_env, monkeypatch,
):
    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        before_route = await _snapshot(h)
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
        assert await _snapshot(h) == before_route
        assert provider_writes == []

        source_id = await _fixture_revision_context(h)
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context,
            _replacement_request(
                h, revision_archive(h.data), predecessor_id=h.created.submission_id,
                idempotency_key=new_record_id(),
            ),
        )
        async with h.factory() as session:
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.checker_remediation_manifest_id == source_id


async def test_unchanged_replacement_archive_or_manifest_denied(
    tmp_path, isolated_database_env, monkeypatch,
):
    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        baseline = await _snapshot(h)
        provider_writes.clear()
        predecessor_id = h.created.submission_id
        for data, expected in (
            (h.data, SubmissionChangeFailureCode.ARCHIVE_UNCHANGED),
            (
                _same_semantics_different_archive(h.data),
                SubmissionChangeFailureCode.MANIFEST_UNCHANGED,
            ),
        ):
            request = _replacement_request(
                h, data, predecessor_id=predecessor_id, idempotency_key=new_record_id(),
            )
            with pytest.raises(SubmissionChangeRejectedError) as failure:
                await _prepare(h, request)
            assert failure.value.code is expected
            assert await _snapshot(h) == baseline
            assert provider_writes == []

        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context,
            _replacement_request(
                h, revision_archive(h.data), predecessor_id=predecessor_id,
                idempotency_key=new_record_id(),
            ),
        )
        async with h.factory() as session:
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "ready"


async def test_blocked_replacement_precheck_preserves_revision_state(
    tmp_path, isolated_database_env, monkeypatch,
):
    provider_writes = _trace_provider_writes(monkeypatch)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        provider_writes.clear()
        changed_data = revision_archive(h.data)
        with pytest.raises(SubmissionBundlePreparationCheckFailed) as blocked:
            await _prepare(h, replace(
                _replacement_request(
                    h, changed_data, predecessor_id=h.created.submission_id,
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

        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context,
            _replacement_request(
                h, changed_data, predecessor_id=h.created.submission_id,
                idempotency_key=new_record_id(),
            ),
        )
        async with h.factory() as session:
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "ready"


async def test_replacement_loads_exact_consumed_predecessor(
    tmp_path, isolated_database_env, monkeypatch,
):
    loaded = []
    original_load = PreparedSubmissionBundlePreparationCommand._load_predecessor

    async def traced_load(self, task_context):
        predecessor = await original_load(self, task_context)
        loaded.append((task_context.predecessor, predecessor))
        return predecessor

    monkeypatch.setattr(
        PreparedSubmissionBundlePreparationCommand, "_load_predecessor", traced_load,
    )
    async with remediation_source(tmp_path, isolated_database_env) as h:
        predecessor_id = h.created.submission_id
        await _fixture_revision_context(h)
        loaded.clear()
        for data in (h.data, _same_semantics_different_archive(h.data)):
            with pytest.raises(SubmissionChangeRejectedError):
                await _prepare(h, _replacement_request(
                    h, data, predecessor_id=predecessor_id,
                    idempotency_key=new_record_id(),
                ))
        changed_data = revision_archive(h.data)
        with pytest.raises(SubmissionBundlePreparationCheckFailed):
            await _prepare(h, replace(
                _replacement_request(
                    h, changed_data, predecessor_id=predecessor_id,
                    idempotency_key=new_record_id(),
                ),
                contributor_attestation="",
            ))
        idempotency_key = new_record_id()
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context,
            _replacement_request(
                h, changed_data, predecessor_id=predecessor_id,
                idempotency_key=idempotency_key,
            ),
        )
        replay = await _prepare(h, _replacement_request(
            h, changed_data, predecessor_id=predecessor_id,
            idempotency_key=idempotency_key,
        ))
        assert replay.admission_id == admission_id
        async with h.factory() as session:
            predecessor_admission = await session.get(
                SubmissionBundleAdmission, str(h.creation_request.admission_id)
            )
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "ready"
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


async def test_replacement_dispatch_sql_rejects_cause_and_receipt_substitution(
    tmp_path, isolated_database_env,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        request = _replacement_request(
            h, revision_archive(h.data), predecessor_id=h.created.submission_id,
            idempotency_key=new_record_id(),
        )
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context, request,
        )
        async with h.factory() as session:
            created = await compose_hidden_submission_creation_command(
                session, h.actor_context, request_id=new_record_id(),
                correlation_id=new_record_id(),
            ).create(SubmissionCreationRequest(
                task_id=h.request.task_id,
                assignment_id=h.request.assignment_id,
                contributor_id=h.actor_context.actor_profile_id,
                predecessor_submission_id=h.created.submission_id,
                admission_id=admission_id,
                summary=request.summary,
                contributor_attestation=request.contributor_attestation,
            ))
        async with h.factory() as session:
            dispatch_body = await session.scalar(text(
                "SELECT to_jsonb(d) FROM public.submission_dispatches d WHERE submission_id=:id"
            ), {"id": created.submission_id})
            assert dispatch_body["checker_remediation_manifest_id"] == str(source_id)
            validate = text(
                "SELECT public.submission_dispatch_valid("
                "pg_catalog.jsonb_populate_record(NULL::public.submission_dispatches, "
                "CAST(:body AS jsonb)))"
            )
            assert await session.scalar(validate, {"body": json.dumps(dispatch_body)}) is True
            for field, substituted in (
                ("checker_remediation_manifest_id", None),
                ("checker_remediation_manifest_id", str(new_record_id())),
                ("creation_decision_id", str(h.created.creation_decision_id)),
                ("binding_decision_id", str(h.created.binding_decision_id)),
            ):
                assert await session.scalar(
                    validate, {"body": json.dumps(dispatch_body | {field: substituted})}
                ) is False, field


async def test_sql_evidence_insert_rejects_superseded_checker_cause(
    tmp_path, isolated_database_env,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context,
            _replacement_request(
                h, revision_archive(h.data), predecessor_id=h.created.submission_id,
                idempotency_key=new_record_id(),
            ),
        )
        async with h.factory() as session:
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "ready"
            assert admission.checker_remediation_manifest_id == source_id
            donor_id = admission.pre_submit_evidence_set_id
            donor = (await session.execute(text(
                "SELECT attempt_id,attempt_request_digest FROM public.pre_submit_evidence_sets "
                "WHERE id=:id"
            ), {"id": donor_id})).one()
            result_ids = list((await session.execute(text(
                "SELECT id FROM public.pre_submit_evidence_results "
                "WHERE evidence_set_id=:id ORDER BY result_order"
            ), {"id": donor_id})).scalars())
            assert result_ids

        await reserve(h, await next_request(h))
        before = await _snapshot(h)
        async with h.factory() as session:
            current_run_id = await session.scalar(text(
                "SELECT current_run_id FROM public.checker_submission_fences "
                "WHERE submission_id=:id"
            ), {"id": h.created.submission_id})
            routed_run_id = await session.scalar(text(
                "SELECT checker_run_id FROM public.task_post_submit_routing_manifests "
                "WHERE id=:id"
            ), {"id": source_id})
            assert current_run_id != routed_run_id
        attempt_id, evidence_id = new_record_id(), new_record_id()
        operation = canonical_json_hash({"test_clone_evidence_id": str(evidence_id)})
        with pytest.raises(
            IntegrityError, match="pre-submit remediation evaluation is not current",
        ):
            async with h.factory() as session, session.begin():
                await session.execute(text("""
                    INSERT INTO public.pre_submit_execution_attempts
                    SELECT (pg_catalog.jsonb_populate_record(
                      NULL::public.pre_submit_execution_attempts,
                      pg_catalog.to_jsonb(a) || pg_catalog.jsonb_build_object(
                        'id', CAST(:attempt_id AS text),
                        'idempotency_key', CAST(:idempotency_key AS text),
                        'claim_nonce', CAST(:claim_nonce AS text),
                        'status', 'reserved', 'evidence_set_id', NULL,
                        'created_at', transaction_timestamp()
                      ))).*
                    FROM public.pre_submit_execution_attempts a WHERE a.id=:donor_attempt
                """), {
                    "attempt_id": str(attempt_id), "idempotency_key": str(new_record_id()),
                    "claim_nonce": str(new_record_id()), "donor_attempt": donor.attempt_id,
                })
                await session.execute(text("""
                    INSERT INTO public.pre_submit_evidence_sets
                    SELECT (pg_catalog.jsonb_populate_record(
                      NULL::public.pre_submit_evidence_sets,
                      pg_catalog.to_jsonb(e) || pg_catalog.jsonb_build_object(
                        'id', CAST(:evidence_id AS text),
                        'operation_identity', CAST(:operation AS text),
                        'attempt_id', CAST(:attempt_id AS text),
                        'created_at', transaction_timestamp()
                      ))).*
                    FROM public.pre_submit_evidence_sets e WHERE e.id=:donor_id
                """), {
                    "evidence_id": str(evidence_id), "operation": operation,
                    "attempt_id": str(attempt_id), "donor_id": donor_id,
                })
                for result_id in result_ids:
                    await session.execute(text("""
                        INSERT INTO public.pre_submit_evidence_results
                        SELECT (pg_catalog.jsonb_populate_record(
                          NULL::public.pre_submit_evidence_results,
                          pg_catalog.to_jsonb(r) || pg_catalog.jsonb_build_object(
                            'id', CAST(:new_id AS text),
                            'evidence_set_id', CAST(:evidence_id AS text),
                            'created_at', transaction_timestamp()
                          ))).*
                        FROM public.pre_submit_evidence_results r WHERE r.id=:donor_id
                    """), {
                        "new_id": str(new_record_id()),
                        "evidence_id": str(evidence_id), "donor_id": result_id,
                    })
                await session.execute(text("""
                    UPDATE public.pre_submit_execution_attempts
                    SET status='completed',evidence_set_id=:evidence_id WHERE id=:attempt_id
                """), {"evidence_id": evidence_id, "attempt_id": attempt_id})
        assert await _snapshot(h) == before


async def test_sql_attempt_reconstruction_rejects_foreign_routed_cause(
    tmp_path, isolated_database_env,
):
    async with remediation_source(tmp_path / "local", isolated_database_env) as local:
        async with remediation_source(
            tmp_path / "foreign", isolated_database_env, provision_services=False,
            storage_settings=local.settings,
        ) as foreign:
            local_source = await _fixture_revision_context(local)
            foreign_source = await _fixture_revision_context(foreign)
            admission_id = await _verified_admission(
                local.factory, local.store, local.namespace, local.settings,
                local.actor_context,
                _replacement_request(
                    local, revision_archive(local.data),
                    predecessor_id=local.created.submission_id,
                    idempotency_key=new_record_id(),
                ),
            )
            async with local.factory() as session:
                admission = await session.get(SubmissionBundleAdmission, str(admission_id))
                assert admission.status == "ready"
                assert admission.checker_remediation_manifest_id == local_source
                donor_id = admission.pre_submit_evidence_set_id
                donor = (await session.execute(text("""
                    SELECT e.attempt_id, a.request_json::jsonb AS request_body
                    FROM public.pre_submit_evidence_sets e
                    JOIN public.pre_submit_execution_attempts a ON a.id=e.attempt_id
                    WHERE e.id=:id
                """), {"id": donor_id})).mappings().one()
                result_ids = list((await session.execute(text(
                    "SELECT id FROM public.pre_submit_evidence_results "
                    "WHERE evidence_set_id=:id ORDER BY result_order"
                ), {"id": donor_id})).scalars())
            assert result_ids
            request_body = dict(donor["request_body"])
            assert request_body["checker_remediation_manifest_id"] == str(local_source)
            request_body["checker_remediation_manifest_id"] = str(foreign_source)
            request_digest = canonical_json_hash(request_body)
            attempt_id, evidence_id = new_record_id(), new_record_id()
            operation = canonical_json_hash({"test_clone_evidence_id": str(evidence_id)})
            before = await _snapshot(local)
            with pytest.raises(IntegrityError, match="pre-submit evidence resource mismatch"):
                async with local.factory.begin() as session:
                    await session.execute(text("""
                        INSERT INTO public.pre_submit_execution_attempts
                        SELECT (pg_catalog.jsonb_populate_record(
                          NULL::public.pre_submit_execution_attempts,
                          pg_catalog.to_jsonb(a) || pg_catalog.jsonb_build_object(
                            'id', CAST(:attempt_id AS text),
                            'idempotency_key', CAST(:idempotency_key AS text),
                            'claim_nonce', CAST(:claim_nonce AS text),
                            'request_json', CAST(:request_body AS jsonb),
                            'request_digest', CAST(:request_digest AS text),
                            'status', 'reserved', 'evidence_set_id', NULL,
                            'created_at', transaction_timestamp()
                          ))).*
                        FROM public.pre_submit_execution_attempts a WHERE a.id=:donor_attempt
                    """), {
                        "attempt_id": str(attempt_id),
                        "idempotency_key": str(new_record_id()),
                        "claim_nonce": str(new_record_id()),
                        "request_body": json.dumps(request_body),
                        "request_digest": request_digest,
                        "donor_attempt": donor["attempt_id"],
                    })
                    await session.execute(text("""
                        INSERT INTO public.pre_submit_evidence_sets
                        SELECT (pg_catalog.jsonb_populate_record(
                          NULL::public.pre_submit_evidence_sets,
                          pg_catalog.to_jsonb(e) || pg_catalog.jsonb_build_object(
                            'id', CAST(:evidence_id AS text),
                            'operation_identity', CAST(:operation AS text),
                            'attempt_id', CAST(:attempt_id AS text),
                            'attempt_request_digest', CAST(:request_digest AS text),
                            'created_at', transaction_timestamp()
                          ))).*
                        FROM public.pre_submit_evidence_sets e WHERE e.id=:donor_id
                    """), {
                        "evidence_id": str(evidence_id), "operation": operation,
                        "attempt_id": str(attempt_id), "request_digest": request_digest,
                        "donor_id": donor_id,
                    })
                    for result_id in result_ids:
                        await session.execute(text("""
                            INSERT INTO public.pre_submit_evidence_results
                            SELECT (pg_catalog.jsonb_populate_record(
                              NULL::public.pre_submit_evidence_results,
                              pg_catalog.to_jsonb(r) || pg_catalog.jsonb_build_object(
                                'id', CAST(:new_id AS text),
                                'evidence_set_id', CAST(:evidence_id AS text),
                                'created_at', transaction_timestamp()
                              ))).*
                            FROM public.pre_submit_evidence_results r WHERE r.id=:donor_id
                        """), {
                            "new_id": str(new_record_id()),
                            "evidence_id": str(evidence_id), "donor_id": result_id,
                        })
                    await session.execute(text("""
                        UPDATE public.pre_submit_execution_attempts
                        SET status='completed',evidence_set_id=:evidence_id WHERE id=:attempt_id
                    """), {"evidence_id": evidence_id, "attempt_id": attempt_id})
            assert await _snapshot(local) == before


@pytest.mark.parametrize("advance_fence", [False, True])
async def test_dispatch_commit_requires_current_predecessor_checker_fence(
    tmp_path, isolated_database_env, monkeypatch, advance_fence,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        request = _replacement_request(
            h, revision_archive(h.data), predecessor_id=h.created.submission_id,
            idempotency_key=new_record_id(),
        )
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context, request,
        )
        async with h.factory.begin() as session:
            frozen = await task_submission_context_port(session).lock_submission_context(
                _context_request(h)
            )
        assert frozen.checker_remediation_manifest_id == source_id
        creation = SubmissionCreationRequest(
            task_id=h.request.task_id,
            assignment_id=h.request.assignment_id,
            contributor_id=h.actor_context.actor_profile_id,
            predecessor_submission_id=h.created.submission_id,
            admission_id=admission_id,
            summary=request.summary,
            contributor_attestation=request.contributor_attestation,
        )

        if advance_fence:
            await reserve(h, await next_request(h))
            async with h.factory.begin() as session:
                with pytest.raises(TaskSubmissionContextUnavailable):
                    await task_submission_context_port(session).lock_submission_context(
                        _context_request(h)
                    )

        class FrozenTaskContextPort:
            async def lock_submission_context(self, selected):
                assert selected == _context_request(h)
                return frozen

        staged = []
        original_create = TaskSubmissionCreationService.create

        async def traced_create(service, selected):
            result = await original_create(service, selected)
            assert await service._session.scalar(text(
                "SELECT count(*) FROM public.submission_dispatches WHERE submission_id=:id"
            ), {"id": result.submission_id}) == 1
            staged.append(result.submission_id)
            return result

        monkeypatch.setattr(TaskSubmissionCreationService, "create", traced_create)
        if advance_fence:
            # Deliberately stale TASK port only: the writer still executes real
            # AUTH, ART consumption, CHECKERS reservation, outbox and SQL commit.
            monkeypatch.setattr(
                "app.adapters.tasks.task_submission_context_port",
                lambda _session: FrozenTaskContextPort(),
            )
            with pytest.raises(
                IntegrityError, match="replacement dispatch evaluation is not current",
            ):
                async with h.factory() as session:
                    await compose_hidden_submission_creation_command(
                        session, h.actor_context, request_id=new_record_id(),
                        correlation_id=new_record_id(),
                    ).create(creation)
            assert len(staged) == 1
            async with h.factory() as session:
                assert await session.scalar(text("SELECT count(*) FROM public.submissions")) == 1
                assert await session.scalar(text("SELECT count(*) FROM public.submission_dispatches")) == 1
                admission = await session.get(SubmissionBundleAdmission, str(admission_id))
                assert admission.status == "ready"
                assert await session.scalar(text(
                    "SELECT status FROM public.workstream_tasks WHERE id=:id"
                ), {"id": h.request.task_id}) == "needs_revision"
        else:
            async with h.factory() as session:
                created = await compose_hidden_submission_creation_command(
                    session, h.actor_context, request_id=new_record_id(),
                    correlation_id=new_record_id(),
                ).create(creation)
            assert staged == [created.submission_id]
            assert created.submission_version == 2
            async with h.factory() as session:
                dispatch = await session.get(SubmissionDispatch, str(created.submission_id))
                assert dispatch.checker_remediation_manifest_id == source_id
                assert await session.scalar(text(
                    "SELECT public.submission_dispatch_valid(d) "
                    "FROM public.submission_dispatches d WHERE d.submission_id=:id"
                ), {"id": created.submission_id}) is True


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


async def test_replacement_holds_task_custody_against_successor_generation(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        request = _replacement_request(
            h, revision_archive(h.data), predecessor_id=h.created.submission_id,
            idempotency_key=new_record_id(),
        )
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context, request,
        )
        creation = SubmissionCreationRequest(
            task_id=h.request.task_id, assignment_id=h.request.assignment_id,
            contributor_id=h.actor_context.actor_profile_id,
            predecessor_submission_id=h.created.submission_id,
            admission_id=admission_id, summary=request.summary,
            contributor_attestation=request.contributor_attestation,
        )
        successor = await next_request(h)
        async with h.factory() as session:
            prior = (await session.execute(text("""
                SELECT f.current_run_id,
                  (SELECT count(*) FROM public.checker_runs WHERE submission_id=:prior),
                  (SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m
                   WHERE m.id=:source)
                FROM public.checker_submission_fences f WHERE f.submission_id=:prior
            """), {"prior": h.created.submission_id, "source": source_id})).one()

        held, release = asyncio.Event(), asyncio.Event()
        creator_pid: list[int] = []
        original = TaskSubmissionContextService.lock_submission_context

        async def pause_after_real_context(service, selected):
            facts = await original(service, selected)
            if service._session.info.get("replacement_race"):
                assert facts.checker_remediation_manifest_id == source_id
                creator_pid.append(await service._session.scalar(text("SELECT pg_backend_pid()")))
                held.set()
                await asyncio.wait_for(release.wait(), 30)
            return facts

        async def create_replacement():
            async with h.factory() as session:
                session.info["replacement_race"] = True
                return await compose_hidden_submission_creation_command(
                    session, h.actor_context, request_id=new_record_id(),
                    correlation_id=new_record_id(),
                ).create(creation)

        waiter_name = "replacement-successor-" + new_record_id().hex

        async def reserve_successor():
            async with h.factory() as session, session.begin():
                await session.execute(text(
                    "SELECT set_config('application_name',:name,true)"
                ), {"name": waiter_name})
                return await evaluation_coordinator(session).reserve_current_evaluation(successor)

        with monkeypatch.context() as patch:
            patch.setattr(TaskSubmissionContextService, "lock_submission_context", pause_after_real_context)
            creator = asyncio.create_task(create_replacement())
            waiter = None
            try:
                await asyncio.wait_for(held.wait(), 30)
                waiter = asyncio.create_task(reserve_successor())
                await asyncio.wait_for(wait_for_named_database_lock(
                    isolated_database_env, waiter_name, expected_blocker_pid=creator_pid[0],
                ), 15)
                async with h.factory() as observer:
                    waiting_query = await observer.scalar(text(
                        "SELECT query FROM pg_stat_activity "
                        "WHERE application_name=:name AND wait_event_type='Lock'"
                    ), {"name": waiter_name})
                assert waiting_query is not None and "workstream_tasks" in waiting_query
                assert not waiter.done()
                release.set()
                created = await asyncio.wait_for(creator, 60)
                with pytest.raises(
                    CheckerExecutionUnavailable, match="checker_reservation_scope_unavailable",
                ):
                    await asyncio.wait_for(waiter, 30)
            finally:
                release.set()
                for pending in (creator, waiter):
                    if pending is not None and not pending.done():
                        pending.cancel()
                await asyncio.gather(
                    *(pending for pending in (creator, waiter) if pending is not None),
                    return_exceptions=True,
                )

        assert created.submission_version == 2
        async with h.factory() as session:
            after = (await session.execute(text("""
                SELECT f.current_run_id,
                  (SELECT count(*) FROM public.checker_runs WHERE submission_id=:prior),
                  (SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m
                   WHERE m.id=:source)
                FROM public.checker_submission_fences f WHERE f.submission_id=:prior
            """), {"prior": h.created.submission_id, "source": source_id})).one()
            assert after == prior
            assert await session.scalar(text(
                "SELECT count(*) FROM public.submissions WHERE task_id=:task"
            ), {"task": h.request.task_id}) == 2
            assert await session.scalar(text(
                "SELECT count(*) FROM public.submission_dispatches WHERE task_id=:task"
            ), {"task": h.request.task_id}) == 2
            assert await session.scalar(text(
                "SELECT public.submission_dispatch_valid(d) "
                "FROM public.submission_dispatches d WHERE d.submission_id=:id"
            ), {"id": created.submission_id}) is True
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "consumed"
            assert await session.scalar(text(
                "SELECT status FROM public.workstream_tasks WHERE id=:task"
            ), {"task": h.request.task_id}) == "evaluation_pending"
