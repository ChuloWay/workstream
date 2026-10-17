"""Read retained selected PRE runs for their own contributor without leasing or finalizing."""

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitRunView, SelectedPreSubmitTerminalFacts, SelectedPreSubmitUnavailable,
)
from app.modules.checkers.models import SelectedPreSubmitRun


class SelectedPreSubmitRunReader:
    """Fixed columns and revalidated terminal bodies; the caller owns authority."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_contributor_runs(self, *, actor_profile_id, task_id, run_id, limit, before):
        run = SelectedPreSubmitRun
        statement = select(run).where(
            run.actor_profile_id == str(actor_profile_id), run.task_id == str(task_id),
        )
        if run_id is not None:
            statement = statement.where(run.id == str(run_id))
        if before is not None:
            statement = statement.where(tuple_(run.queued_at, run.id) < (before[0], str(before[1])))
        rows = (await self._session.scalars(
            statement.order_by(run.queued_at.desc(), run.id.desc()).limit(limit + 1),
        )).all()
        views = []
        for row in rows[:limit]:
            try:
                terminal = (
                    SelectedPreSubmitTerminalFacts.from_canonical_body(row.terminal_json)
                    if row.terminal_json is not None else None
                )
            except (TypeError, ValueError):
                raise SelectedPreSubmitUnavailable("selected_pre_submit_stored_facts_invalid") from None
            if terminal is not None and (
                terminal.terminal_digest != row.terminal_digest
                or terminal.lease.reservation.attempt_id != UUID(str(row.id))
                or (terminal.execution is not None and terminal.execution.eligible != row.eligible)
            ):
                raise SelectedPreSubmitUnavailable("selected_pre_submit_stored_facts_invalid")
            views.append(SelectedPreSubmitRunView(
                run_id=UUID(str(row.id)), task_id=UUID(str(row.task_id)),
                assignment_id=UUID(str(row.assignment_id)), status=row.status,
                archive_sha256=row.archive_sha256, archive_byte_count=row.archive_byte_count,
                queued_at=row.queued_at, completed_at=row.completed_at, terminal=terminal,
            ))
        return tuple(views), len(rows) > limit
