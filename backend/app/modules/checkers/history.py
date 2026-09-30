"""Fixed history projection from closed results and the sole currentness fence."""

from sqlalchemy import select, literal_column, tuple_

from app.modules.checkers.models import CheckerRun, CheckerResult, CheckerSubmissionFence
from app.modules.checkers.api.history import (
    ContributorCheckerHistory, ManagementCheckerHistory,
    ContributorCheckerResult, ManagementCheckerResult,
)
from app.modules.checkers.execution_results import RESULT_MESSAGES


class CheckerHistoryRepository:
    def __init__(self, session):
        self._session = session

    async def read(self, *, submission_id, task_id, manager, run_id=None, limit=25, after=None):
        schema = ManagementCheckerHistory if manager else ContributorCheckerHistory
        result_schema = ManagementCheckerResult if manager else ContributorCheckerResult
        current = select(CheckerSubmissionFence.submission_id).where(
            CheckerSubmissionFence.submission_id == CheckerRun.submission_id,
            CheckerSubmissionFence.current_run_id == CheckerRun.id,
            CheckerRun.status == "completed",
        ).correlate(CheckerRun).exists().label("is_current_for_submission")
        fields = []
        for name in schema.model_fields:
            if name == "results":
                continue
            fields.append(current if name == "is_current_for_submission" else
                          CheckerRun.evaluation_generation.label(name) if name == "attempt_number" else
                          getattr(CheckerRun, name))
        statement = select(*fields).where(CheckerRun.submission_id == str(submission_id),
                                          CheckerRun.task_id == str(task_id))
        if run_id is not None:
            statement = statement.where(CheckerRun.id == str(run_id))
        if after is not None:
            statement = statement.where(tuple_(CheckerRun.created_at, CheckerRun.id) > (after[0], str(after[1])))
        rows = (await self._session.execute(statement.order_by(CheckerRun.created_at, CheckerRun.id).limit(limit + 1))).mappings().all()
        values = []
        for row in rows[:limit]:
            columns = [getattr(CheckerResult, name) for name in ("id", "checker_name", "status", "severity", "code", "failure_category")]
            if manager:
                columns.append(literal_column("(checker_results.status<>'passed' AND (checker_runs.request_json::jsonb #> '{policy,blocking_severities}') ? checker_results.severity)").label("blocks_review"))
            result_query = select(*columns).join(CheckerRun, CheckerRun.id == CheckerResult.checker_run_id).where(
                CheckerResult.checker_run_id == row["id"],
                CheckerResult.submission_id == str(submission_id), CheckerResult.task_id == str(task_id),
            )
            if not manager:
                result_query = result_query.where(
                    CheckerResult.failure_category != "task_configuration",
                    CheckerRun.routing_recommendation != "task_setup_blocked",
                )
            results = (await self._session.execute(result_query.order_by(CheckerResult.member_order))).mappings().all()
            projected = []
            for member in results:
                message, fix = RESULT_MESSAGES[member["code"]]
                visible = member["failure_category"] != "task_configuration"
                item = {key: member[key] for key in ("id", "checker_name", "status", "severity")}
                item.update(worker_message=message if visible else None, worker_suggested_fix=fix if visible else None)
                if manager:
                    item.update(message=message, blocks_review=member["blocks_review"])
                projected.append(result_schema(**item))
            values.append(schema(**row, results=projected))
        return values, len(rows) > limit
