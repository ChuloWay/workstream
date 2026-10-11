"""Real ART replacement comparison against one retained consumed Submission."""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import UUID
from zipfile import ZipFile

import pytest
from sqlalchemy import text
from starlette.requests import Request

from app.adapters.artifacts import get_submission_bundle_preparation_command
from app.adapters.artifacts.local import LocalStorageAdapter
from app.core.identifiers import new_record_id
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.artifacts.api import (
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
from tests.artifact_store_helpers import artifact_byte_stream
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.post_submit_routing.support import revision_archive
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


async def _fixture_revision_context(h) -> None:
    """Supply only the exact existing TASK context needed to exercise ART."""
    async with h.factory() as session, session.begin():
        changed = await session.execute(
            text(
                "UPDATE public.workstream_tasks SET status='needs_revision' "
                "WHERE id=:id AND status='evaluation_pending'"
            ),
            {"id": h.request.task_id},
        )
        assert changed.rowcount == 1


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


async def test_real_replacement_compares_consumed_predecessor_and_replays_exactly(
    tmp_path,
    isolated_database_env,
    monkeypatch,
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

    async with material_fixture(tmp_path, isolated_database_env) as h:
        await _assert_dispatch_valid(h)
        await _fixture_revision_context(h)
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
            assert evidence.predecessor_submission_id == str(predecessor_id)
            assert evidence.predecessor_submission_version == 1
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

        assert len(loaded) == 4
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
    async with material_fixture(tmp_path / "local", isolated_database_env) as local:
        async with material_fixture(
            tmp_path / "foreign",
            isolated_database_env,
            provision_services=False,
            storage_settings=local.settings,
        ) as foreign:
            await _assert_dispatch_valid(local)
            await _assert_dispatch_valid(foreign)
            await _fixture_revision_context(local)
            provider_writes.clear()
            baseline = await _snapshot(local)

            async def forbidden_load(*_args, **_kwargs):
                pytest.fail("foreign predecessor reached ART predecessor loading")

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
