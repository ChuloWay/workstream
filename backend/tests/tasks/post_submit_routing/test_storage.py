"""PostgreSQL proof for immutable route-neutral TASK source custody."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.identifiers import new_record_id
from app.modules.artifacts.models import ArtifactReplica
from app.modules.checkers.api.execution import FinalizeFacts
from app.modules.checkers.models import CheckerRun
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from app.modules.projects.models import ProjectGuide
from app.modules.reviews.models import ReviewQueueEntry
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from tests.checkers.execution.support import live_executor, reserve

from .support import (
    SOURCE_COLUMNS,
    activate_successor_guide,
    as_uuid,
    completed_source,
    insert_source,
    joined_source_facts,
    next_request,
    other_hash,
    source_count,
    source_rows,
    source_values,
)


pytestmark = pytest.mark.postgres_schema_contract


async def _reject(session, values, message: str) -> None:
    with pytest.raises((DBAPIError, IntegrityError), match=message):
        async with session.begin_nested():
            await insert_source(session, values)


async def test_source_matches_real_completed_run(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            database_created_at = await session.scalar(select(func.now()))
            await insert_source(session, h.source)
        async with h.factory() as session:
            stored = await session.get(TaskPostSubmitRoutingManifest, h.source["id"])
            assert stored is not None
            values = {column: getattr(stored, column) for column in SOURCE_COLUMNS}
            submission = await session.get(Submission, str(stored.submission_id))
            task = await session.get(WorkstreamTask, str(stored.task_id))
        facts = await joined_source_facts(h, values)
        expected_lineage = TaskPolicyLineage(
            locked_guide_version=submission.locked_guide_version,
            locked_guide_source_snapshot_id=as_uuid(
                submission.locked_guide_source_snapshot_id
            ),
            locked_guide_source_snapshot_hash=submission.locked_guide_source_snapshot_hash,
            locked_effective_project_submission_artifact_policy_id=as_uuid(
                submission.locked_effective_project_submission_artifact_policy_id
            ),
            locked_effective_project_submission_artifact_policy_hash=(
                submission.locked_effective_project_submission_artifact_policy_hash
            ),
            locked_pre_submit_checker_policy_id=as_uuid(
                submission.locked_pre_submit_checker_policy_id
            ),
            locked_pre_submit_checker_bundle_hash=(
                submission.locked_pre_submit_checker_bundle_hash
            ),
            locked_post_submit_checker_policy_id=as_uuid(
                submission.locked_post_submit_checker_policy_id
            ),
            locked_post_submit_checker_policy_version=(
                submission.locked_post_submit_checker_policy_version
            ),
            locked_post_submit_checker_policy_hash=(
                submission.locked_post_submit_checker_policy_hash
            ),
            locked_review_policy_id=as_uuid(submission.locked_review_policy_id),
            locked_review_policy_generation=submission.locked_review_policy_generation,
            locked_review_policy_hash=submission.locked_review_policy_hash,
            locked_revision_policy_id=as_uuid(submission.locked_revision_policy_id),
            locked_revision_policy_generation=(
                submission.locked_revision_policy_generation
            ),
            locked_revision_policy_hash=submission.locked_revision_policy_hash,
            locked_contribution_policy_version_id=as_uuid(
                task.locked_contribution_policy_version_id
            ),
        )

        assert set(values) == set(SOURCE_COLUMNS)
        assert values["created_at"] == database_created_at
        assert facts.model_dump(include=set(SOURCE_COLUMNS)) == values
        assert facts.project_id == h.request.project_id
        assert facts.task_id == h.request.task_id
        assert facts.assignment_id == h.request.assignment_id
        assert facts.submission_id == h.request.submission_id
        assert facts.submission_version == h.request.submission_version
        assert facts.checker_run_id == h.result.attempt_id
        assert facts.evaluation_request_id == h.request.evaluation_request_id
        assert facts.request_digest == h.request.request_sha256
        assert facts.result_id == h.result.result_id
        assert facts.result_digest == h.result.result_digest
        assert facts.predecessor_submission_id is None
        assert facts.predecessor_submission_version is None
        assert facts.admission_id == h.created.admission_id
        assert facts.binding_id == h.created.artifact_binding_id
        assert facts.content_id == h.created.artifact_content_id
        assert facts.locked_policy == expected_lineage
        assert facts.routing_recommendation == "allow_review"


async def test_source_rejects_null_scalar(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            for field in SOURCE_COLUMNS:
                bad = h.source | {"id": new_record_id(), field: None}
                await _reject(session, bad, f'null value in column "{field}"')
                assert await source_count(session) == 0, field
            await insert_source(session, h.source)
            await session.commit()
        async with h.factory() as session:
            assert await source_count(session) == 1


async def test_source_rejects_scalar_substitution(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            other_replica = await session.scalar(
                select(ArtifactReplica.id)
                .where(ArtifactReplica.id != str(h.source["replica_id"]))
                .limit(1)
            )
            assert other_replica is not None
            cases = (
                ("evaluation_request_id", new_record_id(), "checker source mismatch"),
                ("request_digest", other_hash(h.source["request_digest"]), "checker source mismatch"),
                ("evaluation_generation", h.source["evaluation_generation"] + 1, "checker source mismatch"),
                ("result_id", new_record_id(), "checker source mismatch"),
                ("result_digest", other_hash(h.source["result_digest"]), "checker source mismatch"),
                ("content_sha256", other_hash(h.source["content_sha256"]), "material mismatch"),
                ("byte_count", h.source["byte_count"] + 1, "material mismatch"),
                (
                    "semantic_manifest_sha256",
                    other_hash(h.source["semantic_manifest_sha256"]),
                    "material mismatch",
                ),
                ("replica_id", as_uuid(other_replica), "material mismatch"),
                ("human_review_required", False, "review policy mismatch"),
            )
            for field, replacement, message in cases:
                bad = h.source | {"id": new_record_id(), field: replacement}
                await _reject(session, bad, message)
                assert await source_count(session) == 0, field
            await insert_source(session, h.source)
            await session.commit()


async def test_source_rejects_foreign_lineage(tmp_path, isolated_database_env):
    async with completed_source(tmp_path / "one", isolated_database_env) as first:
        async with completed_source(
            tmp_path / "two",
            isolated_database_env,
            provision_services=False,
            storage_settings=first.settings,
        ) as other:
            async with first.factory() as session:
                cases = (
                    ("project_id", other.source["project_id"]),
                    ("task_id", other.source["task_id"]),
                    ("submission_id", other.source["submission_id"]),
                    ("submission_version", first.source["submission_version"] + 1),
                    ("assignment_id", other.source["assignment_id"]),
                    ("contributor_id", other.source["contributor_id"]),
                    (
                        "contribution_policy_version_id",
                        other.source["contribution_policy_version_id"],
                    ),
                )
                for field, replacement in cases:
                    bad = first.source | {"id": new_record_id(), field: replacement}
                    await _reject(session, bad, "source lineage mismatch")
                    assert await source_count(session) == 0, field

                coherent = first.source | {
                    "id": new_record_id(),
                    **{
                        field: other.source[field]
                        for field in (
                            "project_id",
                            "task_id",
                            "submission_id",
                            "submission_version",
                            "assignment_id",
                            "contributor_id",
                            "contribution_policy_version_id",
                        )
                    },
                }
                await _reject(session, coherent, "checker source mismatch")
                await insert_source(session, first.source)
                await session.commit()


async def _completed_successor(h):
    await next_request(h)
    await reserve(h)
    result = await live_executor(h).evaluate_post_submission(h.request)
    assert result.outcome == "completed"
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(result.attempt_id))
        assert run.routing_recommendation == "allow_review"
    h.result = result
    return await source_values(h)


async def test_source_rejects_sibling_completion_event(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        original = dict(h.source)
        successor = await _completed_successor(h)
        async with h.factory() as session:
            bad = original | {
                "id": new_record_id(),
                "completion_event_id": successor["completion_event_id"],
            }
            await _reject(session, bad, "checker source mismatch")
            await insert_source(session, original)
            await session.commit()


async def test_source_rejects_phase_receipt(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        original = dict(h.source)
        successor = await _completed_successor(h)
        cases = (
            ("execute", {"execute_evidence_id": successor["execute_evidence_id"]}),
            ("finalize", {"finalize_evidence_id": successor["finalize_evidence_id"]}),
            (
                "swap",
                {
                    "execute_evidence_id": original["finalize_evidence_id"],
                    "finalize_evidence_id": original["execute_evidence_id"],
                },
            ),
        )
        async with h.factory() as session:
            for label, changes in cases:
                await _reject(
                    session,
                    original | {"id": new_record_id(), **changes},
                    "checker source mismatch",
                )
                assert await source_count(session) == 0, label
            await insert_source(session, original)
            await session.commit()


async def test_source_rejects_ineligible_checker_source(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        original = dict(h.source)
        executor = live_executor(h)
        await next_request(h)
        reservation = await reserve(h)
        queued = await source_values(h, reservation.attempt_id)
        async with h.factory() as session:
            await _reject(
                session,
                queued | {"id": new_record_id()},
                "checker source mismatch",
            )
            assert await source_count(session) == 0

        lease, replay = await executor._claim(h.request)
        assert replay is None
        running = await source_values(h, reservation.attempt_id)
        async with h.factory() as session:
            await _reject(
                session,
                running | {"id": new_record_id()},
                "checker source mismatch",
            )
            assert await source_count(session) == 0

        failure = make_post_submit_result(
            request_id=h.request.evaluation_request_id,
            request_digest=h.request.request_sha256,
            attempt_id=reservation.attempt_id,
            result_id=reservation.result_id,
            evaluation_generation=h.request.evaluation_generation,
            outcome="infrastructure_failed",
            member_results=(),
            infrastructure_failure_code="deadline_exceeded",
        )
        await executor.finalize(
            FinalizeFacts(
                request=h.request,
                lease=lease,
                result=failure,
                material=None,
                output_binding_ids=(),
            )
        )
        infrastructure_failed = await source_values(h, reservation.attempt_id)
        async with h.factory() as session:
            await _reject(
                session,
                infrastructure_failed | {"id": new_record_id()},
                "checker source mismatch",
            )
            assert await source_count(session) == 0

        empty_evidence = h.request.structural_input.model_copy(update={"evidence": ()})
        await next_request(h, structural_input=empty_evidence)
        await reserve(h)
        blocked_result = await live_executor(h).evaluate_post_submission(h.request)
        async with h.factory() as session:
            blocked_run = await session.get(CheckerRun, str(blocked_result.attempt_id))
            assert blocked_result.outcome == "completed"
            assert blocked_run.routing_recommendation == "needs_revision"
        blocking_completed = await source_values(h, blocked_result.attempt_id)

        async with h.factory() as session:
            await _reject(
                session,
                blocking_completed | {"id": new_record_id()},
                "checker source mismatch",
            )
            assert await source_count(session) == 0
            await insert_source(session, original)
            await session.commit()


async def test_source_rejects_unactivated_guide(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            guide = await session.scalar(
                select(ProjectGuide).where(
                    ProjectGuide.project_id == str(h.source["project_id"]),
                    ProjectGuide.version == h.request.expected_context.guide_version,
                )
            )
            assert guide.status == "active"
            await session.execute(
                text(
                    "ALTER TABLE public.project_guides "
                    "DISABLE TRIGGER guide_lineage_lifecycle_guard"
                )
            )
            await session.execute(
                text("UPDATE public.project_guides SET status='draft' WHERE id=:id"),
                {"id": guide.id},
            )
            await _reject(session, h.source, "guide activation mismatch")
            await session.execute(
                text("UPDATE public.project_guides SET status='active' WHERE id=:id"),
                {"id": guide.id},
            )
            await insert_source(session, h.source)
            await session.execute(
                text(
                    "ALTER TABLE public.project_guides "
                    "ENABLE TRIGGER guide_lineage_lifecycle_guard"
                )
            )
            await session.commit()
        async with h.factory() as session:
            assert await source_count(session) == 1


async def test_source_retains_historical_guide_and_generation(
    tmp_path, isolated_database_env
):
    async with completed_source(tmp_path, isolated_database_env) as h:
        original = dict(h.source)
        async with h.factory() as session:
            guide = await session.scalar(
                select(ProjectGuide).where(
                    ProjectGuide.project_id == str(original["project_id"]),
                    ProjectGuide.version == h.request.expected_context.guide_version,
                )
            )
            activation = guide.activation_operation_id

        successor_guide = await activate_successor_guide(h)
        async with h.factory() as session, session.begin():
            await insert_source(session, original)
        async with h.factory() as session:
            before = await source_rows(session)
            retained = await session.get(ProjectGuide, guide.id)
            assert retained.activation_operation_id == activation
            assert retained.status == "superseded"

        successor_run = await _completed_successor(h)
        assert successor_guide.command.target.proposal.guide_version == "v2"
        assert successor_run["evaluation_generation"] == original["evaluation_generation"] + 1
        assert successor_run["checker_run_id"] != original["checker_run_id"]
        async with h.factory() as session:
            assert await source_rows(session) == before
            retained = await session.get(ProjectGuide, guide.id)
            assert retained.activation_operation_id == activation
            assert retained.status == "superseded"


async def test_source_is_immutable(tmp_path, isolated_database_env):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session, session.begin():
            await insert_source(session, h.source)
        async with h.factory() as session:
            before = await source_rows(session)
        statements = (
            "UPDATE public.task_post_submit_routing_manifests SET human_review_required=false",
            "DELETE FROM public.task_post_submit_routing_manifests",
            "TRUNCATE public.task_post_submit_routing_manifests",
        )
        for statement in statements:
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="source is immutable"):
                    await session.execute(text(statement))
                    await session.commit()
                await session.rollback()
                assert await source_rows(session) == before


async def test_source_uniqueness_and_caller_rollback(
    tmp_path, isolated_database_env
):
    async with completed_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            task_status = await session.scalar(
                select(WorkstreamTask.status).where(
                    WorkstreamTask.id == str(h.source["task_id"])
                )
            )
            assignment_status = await session.scalar(
                select(TaskAssignment.status).where(
                    TaskAssignment.id == str(h.source["assignment_id"])
                )
            )
            review_count = await session.scalar(
                select(func.count()).select_from(ReviewQueueEntry)
            )

        async with h.factory() as session:
            transaction = await session.begin()
            try:
                await insert_source(session, h.source)
                duplicate = h.source | {"id": new_record_id()}
                with pytest.raises(IntegrityError, match="uq_task_routing_manifest_source"):
                    await insert_source(session, duplicate)
            finally:
                await transaction.rollback()

        async with h.factory() as session:
            assert await source_count(session) == 0
            assert await session.scalar(
                select(WorkstreamTask.status).where(
                    WorkstreamTask.id == str(h.source["task_id"])
                )
            ) == task_status
            assert await session.scalar(
                select(TaskAssignment.status).where(
                    TaskAssignment.id == str(h.source["assignment_id"])
                )
            ) == assignment_status
            assert await session.scalar(
                select(func.count()).select_from(ReviewQueueEntry)
            ) == review_count
            await insert_source(session, h.source)
            await session.commit()
        async with h.factory() as session:
            assert await source_count(session) == 1
