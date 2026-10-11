"""Exact task/source display selected by a contribution evidence reader."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContributionTaskEvidence(BaseModel):
    """Source identifiers and task title, without task authority or economic internals."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    project_id: UUID
    task_id: UUID
    title: str
    source_type: str
    source_ref: str | None
    external_task_id: str | None


class ContributionTaskEvidencePort(Protocol):
    """The caller authorizes the canonical contribution set before loading labels."""

    async def read_contribution_tasks(
        self, selectors: tuple[tuple[UUID, UUID], ...]
    ) -> tuple[ContributionTaskEvidence, ...]:
        """Select only exact project/task pairs from the bounded evidence set."""
        ...
