"""PostgreSQL protects one current unified approval independently of repository reads."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval, GuideProposalCorrection, GuideProposalError,
)
from app.modules.projects.guide_compilation.proposal_repository import GuideProposalRepository
from .pg_support import finalize_corrected_attempt, proposal_case, read_package
from .test_postgresql import approve, correct


async def test_database_rejects_duplicate_approved_root_and_allows_linked_successor(
    clean_postgres_database, monkeypatch,
):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        first = await approve(factory, command, actor, grant, GuideProposalApproval(
            target=package.target, idempotency_key=uuid4()))
        correction = await correct(factory, command, actor, grant, GuideProposalCorrection(
            target=package.target, idempotency_key=uuid4(), reason="Reconsider the required inputs."))
        successor = await finalize_corrected_attempt(factory, values, actor, correction)
        next_package = await read_package(factory, successor, actor, grant)
        assert next_package.current_approval_operation_id == first.operation_id
        async with factory() as session:
            audit_count = await session.scalar(text("SELECT count(*) FROM audit_events"))

        async def omit_current_approval(self, guide_id):
            return None

        # Only the application lookup is removed. Actual authority, reservation,
        # canonical compiler outputs and database custody remain active.
        with monkeypatch.context() as patch:
            patch.setattr(GuideProposalRepository, "current_approval", omit_current_approval)
            with pytest.raises(GuideProposalError) as error:
                await approve(factory, successor, actor, grant, GuideProposalApproval(
                    target=next_package.target, idempotency_key=uuid4()))
            assert error.value.code == "storage_unavailable"
            assert isinstance(error.value.__cause__, IntegrityError)
            assert "uq_proposal_approval_root_guide" in str(error.value.__cause__)
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM audit_events")) == audit_count
            for table in ("project_guide_proposal_approvals", "effective_project_submission_artifact_policies",
                          "pre_submit_checker_policies", "submission_policy_mutation_idempotency_records"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 1
            assert await session.scalar(text("SELECT lifecycle_status FROM submission_artifact_policies WHERE id=:id"),
                                        {"id": str(next_package.target.artifact_policy_id)}) == "draft"

        second = await approve(factory, successor, actor, grant, GuideProposalApproval(
            target=next_package.target, idempotency_key=uuid4(),
            expected_previous_approval_operation_id=first.operation_id,
            expected_previous_approval_output_digest=next_package.current_approval_output_digest))
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM submission_artifact_policies "
                                             "WHERE guide_id=:guide AND lifecycle_status='approved'"),
                                        {"guide": str(command.guide_id)}) == 1
            assert await session.scalar(text("SELECT lifecycle_status FROM submission_artifact_policies WHERE id=:id"),
                                        {"id": str(first.artifact_policy_id)}) == "superseded"
            assert await session.scalar(text("SELECT prior_approval_operation_id FROM project_guide_proposal_approvals "
                                             "WHERE operation_id=:id"), {"id": second.operation_id}) == first.operation_id
