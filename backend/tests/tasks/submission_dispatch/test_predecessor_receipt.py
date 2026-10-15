"""Deferred replacement receipt currentness after valid canonical successor staging."""

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.artifacts.models import SubmissionBundleAdmission
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.models import SubmissionDispatch
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from tests.tasks.post_submit_routing.remediation_support import remediation_source, no_economic_effects
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_lineage_support import _verified_admission
from tests.test_submission_predecessor_custody import (
    _fixture_revision_context, _replacement_request, _snapshot,
)


async def test_deferred_dispatch_rejects_foreign_manifest_after_valid_successor_insert(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path / "local", isolated_database_env) as local:
        async with remediation_source(
            tmp_path / "foreign", isolated_database_env,
            provision_services=False, storage_settings=local.settings,
        ) as foreign:
            await _fixture_revision_context(local)
            foreign_source = await _fixture_revision_context(foreign)
            request = _replacement_request(
                local, revision_archive(local.data),
                predecessor_id=local.created.submission_id, idempotency_key=new_record_id(),
            )
            admission_id = await _verified_admission(
                local.factory, local.store, local.namespace, local.settings,
                local.actor_context, request,
            )
            before = await _snapshot(local)
            creation = SubmissionCreationRequest(
                task_id=local.request.task_id, assignment_id=local.request.assignment_id,
                contributor_id=local.actor_context.actor_profile_id,
                predecessor_submission_id=local.created.submission_id,
                admission_id=admission_id, summary=request.summary,
                contributor_attestation=request.contributor_attestation,
            )
            staged = []
            original_create = TaskSubmissionCreationService.create

            def foreign_dispatch_cause(_mapper, _connection, dispatch):
                # Earlier owners use the real local preparation; only the
                # deferred receipt carries a foreign routed cause.
                dispatch.checker_remediation_manifest_id = foreign_source

            async def check_deferred_receipt(service, selected):
                result = await original_create(service, selected)
                assert await service._session.scalar(text(
                    "SELECT count(*) FROM public.submission_dispatches WHERE submission_id=:id"
                ), {"id": result.submission_id}) == 1
                staged.append(result.submission_id)
                await service._session.execute(text(
                    "SET CONSTRAINTS submission_dispatch_complete IMMEDIATE"
                ))
                return result

            monkeypatch.setattr(TaskSubmissionCreationService, "create", check_deferred_receipt)
            event.listen(SubmissionDispatch, "before_insert", foreign_dispatch_cause)
            try:
                with pytest.raises(
                    IntegrityError, match="replacement dispatch evaluation is not current",
                ) as denied:
                    async with local.factory() as session:
                        await compose_hidden_submission_creation_command(
                            session, local.actor_context, request_id=new_record_id(),
                            correlation_id=new_record_id(),
                        ).create(creation)
                assert denied.value.orig.sqlstate == "23514"
            finally:
                event.remove(SubmissionDispatch, "before_insert", foreign_dispatch_cause)
            assert len(staged) == 1
            assert await _snapshot(local) == before
            async with local.factory() as session:
                admission = await session.get(SubmissionBundleAdmission, str(admission_id))
                assert admission.status == "ready"
                assert await session.scalar(text(
                    "SELECT status FROM public.workstream_tasks WHERE id=:id"
                ), {"id": local.request.task_id}) == "needs_revision"
                await no_economic_effects(session)
