"""Internal published policy selectors; disclosure authority belongs to the caller."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PublishedContributionPolicySelection:
    """No draft identity, rule body or economic configuration crosses this port."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID


class PublishedContributionPolicyPort(Protocol):
    """The caller owns the project lock and authorization before disclosure."""

    async def published_selection(self, project_id: UUID) -> PublishedContributionPolicySelection | None: ...
