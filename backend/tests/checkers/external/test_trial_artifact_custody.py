"""Real trial owner and ART custody retain exact bytes across publication replay."""

import hashlib

import pytest
from sqlalchemy import select, func

from app.adapters.artifacts import checker_output_binding, checker_output_storage
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactBinding
from app.modules.artifacts.service import ArtifactAdmissionRelationshipError
from app.modules.checkers.api.output_custody import CheckerOutputUnavailable
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceArtifactRequest,
    TrialEvidenceBindingRequest,
    TrialEvidenceSelector,
)
from app.modules.checkers.models import CheckerTrialEvidence
from tests.checkers.execution.support import (
    ControlledSelectedExecution,
    live_executor,
    reserve,
    provision_post_submit_service,
)
from tests.checkers.external.test_trial_evidence import _owner, _subject, _trial_fixture
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_checker_materialization import _limits


async def _bytes(value):
    """Stream one bounded receipt without exposing provider coordinates."""
    yield value


class PublishingExecution(ControlledSelectedExecution):
    """Use real owner authorization, storage admission, verification and binding."""

    def __init__(self, harness, catalog, projected):
        super().__init__()
        self.h, self.catalog, self.projected = harness, catalog, projected
        self.ack = None

    async def execute(self, request, grant):
        h = self.h

        def reservations(session):
            return _owner(session, request, self.catalog)

        async with h.factory() as session, session.begin():
            ticket = await reservations(session).reserve(_subject(request, self.projected))
        data = b'{"trial":"retained-original"}'
        selector = TrialEvidenceSelector(
            trial_evidence_id=ticket.trial_evidence_id,
            project_id=request.identity.project_id,
            content_sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        )
        outputs = checker_output_storage(
            sessions=h.factory,
            store=h.store.wrapped,
            namespace=h.namespace,
            preparation=h.preparation,
            settings=h.settings,
            reservations=reservations,
        )
        # Probing an unfinished reservation must commit without pinning content.
        assert await outputs.recover_trial_evidence(selector) is None
        async with h.factory() as session:
            row = await session.get(CheckerTrialEvidence, str(ticket.trial_evidence_id))
            assert row.content_sha256 is None
        with pytest.raises(ArtifactAdmissionRelationshipError):
            await outputs.store_trial_evidence(
                TrialEvidenceArtifactRequest(selector, _bytes(b"{}"))
            )
        async with h.factory() as session:
            row = await session.get(CheckerTrialEvidence, str(ticket.trial_evidence_id))
            assert row.content_sha256 is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactPutAttempt)
                    .where(
                        ArtifactPutAttempt.checker_trial_evidence_id
                        == str(ticket.trial_evidence_id),
                    )
                )
                == 0
            )
        stored = await outputs.store_trial_evidence(
            TrialEvidenceArtifactRequest(selector, _bytes(data))
        )
        assert stored.status == "verified" and not stored.replayed
        # The caller lost its storage response: recover instead of regenerating.
        recovered = await outputs.recover_trial_evidence(selector)
        assert recovered.put_attempt_id == stored.put_attempt_id and recovered.replayed
        binding_request = TrialEvidenceBindingRequest(
            selector,
            stored.put_attempt_id,
            stored.verification_receipt_id,
        )
        async with h.factory() as session, session.begin():
            ack = await checker_output_binding(
                session,
                namespace=h.namespace,
                reservations=reservations(session),
            ).bind_trial_evidence(binding_request)
        assert not ack.replayed
        assert await outputs.read_trial_evidence(selector, ack) == data
        async with h.factory() as session, session.begin():
            replay = await checker_output_binding(
                session,
                namespace=h.namespace,
                reservations=reservations(session),
            ).bind_trial_evidence(binding_request)
        assert replay.replayed and replay.binding_id == ack.binding_id
        with pytest.raises(CheckerOutputUnavailable):
            await outputs.read_trial_evidence(
                selector, ack.model_copy(update={"owner_digest": "sha256:" + "f" * 64})
            )
        async with h.factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ArtifactBinding)
                    .where(
                        ArtifactBinding.resource_type == "checker_trial_evidence",
                        ArtifactBinding.resource_id == str(ticket.trial_evidence_id),
                    )
                )
                == 1
            )
        self.ack = ack
        return await super().execute(request, grant)


async def test_trial_bytes_use_real_art_custody_and_recover_exact_original(
    tmp_path,
    isolated_database_env,
):
    """A failed admission rolls back the pin; verified replay never duplicates effects."""
    from tests.test_s3_artifact_store import provision_minio_bucket

    await provision_minio_bucket.__wrapped__()
    spec, parameters, projected, catalog = _trial_fixture()
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        provider="minio",
        post_submit_registry_spec=spec,
        post_submit_binding_setup=parameters,
        scratch_limits=_limits(
            maximum_files=4,
            maximum_concurrency=4,
            total_deadline_seconds=120.0,
            reservation_ttl_seconds=150.0,
        ),
    ) as h:
        await provision_post_submit_service(h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT)
        await reserve(h)
        adapter = PublishingExecution(h, catalog, projected)
        result = await live_executor(h, selected_execution=adapter).evaluate_post_submission(
            h.request
        )
        assert result.outcome == "completed", result.model_dump_json()
        assert adapter.ack is not None
