"""Current actor-specific work context returned by the existing authorized owner."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.projects.api.guide_activation import GuidePolicySelection
from app.modules.projects.api.locked_policy import GuideDisplayFacts, ProjectDisplayFacts
from app.modules.tasks.api.task_detail import ContributorTaskDetail, ManagementTaskDetail


class ContributorTaskLifecycle(BaseModel):
    """Current assignment and bounded action hints; executing actions reauthorizes."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    assigned_to_current_actor: bool
    next_actions: tuple[Literal["claim", "start"], ...] = Field(max_length=1)


class _TaskWorkContext(BaseModel):
    """Detached display and exact receipt-selected governing policy identities."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    project: ProjectDisplayFacts
    guide: GuideDisplayFacts
    review_policy: GuidePolicySelection
    revision_policy: GuidePolicySelection
    contribution_policy_version_id: UUID

    @model_validator(mode="after")
    def exact_project(self):
        """Reject display facts belonging to different projects."""
        if self.project.id != self.guide.project_id:
            raise ValueError("work context project differs from guide")
        return self


class ContributorTaskWorkContext(_TaskWorkContext):
    """Contributor work instructions without management data or obsolete economics."""

    task: ContributorTaskDetail
    lifecycle: ContributorTaskLifecycle

    @model_validator(mode="after")
    def exact_task(self):
        """Keep the task audience and project exact without response redaction."""
        if type(self.task) is not ContributorTaskDetail or self.task.project_id != self.project.id:
            raise ValueError("contributor work context task is invalid")
        return self


class ManagementTaskWorkContext(_TaskWorkContext):
    """Manager work instructions and provenance without contributor action hints."""

    task: ManagementTaskDetail

    @model_validator(mode="after")
    def exact_task(self):
        """Keep management facts scoped to the context project."""
        if type(self.task) is not ManagementTaskDetail or self.task.project_id != self.project.id:
            raise ValueError("management work context task is invalid")
        return self
