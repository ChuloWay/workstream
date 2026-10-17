"""Minimal project identity and active guide version for a caller-authorized project set."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

ProjectStatus = Literal["draft", "active", "paused", "archived"]


@dataclass(frozen=True, slots=True)
class ActiveGuideIdentity:
    guide_id: UUID
    version: str


@dataclass(frozen=True, slots=True)
class ProjectSummaryFacts:
    """No description, slug or configuration; the caller decides who may see these."""

    project_id: UUID
    name: str
    status: ProjectStatus
    created_at: datetime
    active_guide: ActiveGuideIdentity | None


class ProjectSummaryReadPort(Protocol):
    """Page a bounded selected project set by ``(created_at, id)``."""

    async def read_project_summaries(
        self, project_ids: frozenset[UUID], *, after: tuple[datetime, UUID] | None, limit: int,
    ) -> tuple[tuple[ProjectSummaryFacts, ...], bool]: ...
