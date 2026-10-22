"""Dependency-safe public contracts for project compensation-unit creation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

CompensationUnitAction = Literal["contribution.compensation_unit.create"]
CompensationUnitInstrument = Literal["project_points"]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectCompensationUnitCreateRequest:
    """Enable one project-scoped points unit for later award definitions."""

    operation_id: UUID
    actor_profile_id: UUID
    project_id: UUID
    instrument_type: CompensationUnitInstrument
    unit_code: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectCompensationUnitCreateResult:
    """Immutable result reconstructed only from the stored creation event."""

    event_id: UUID
    operation_id: UUID
    request_digest: str
    actor_profile_id: UUID
    project_id: UUID
    instrument_type: CompensationUnitInstrument
    unit_code: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CompensationUnitCreateAuthorizationFacts:
    """Exact server-owned facts bound to opaque unit-creation authority."""

    action: CompensationUnitAction
    actor_profile_id: UUID
    operation_id: UUID
    request_digest: str
    project_id: UUID
    instrument_type: CompensationUnitInstrument
    unit_code: str


class ProjectCompensationUnitOperationsPort(Protocol):
    """Caller-owned unit creation used by internal operator composition."""

    async def create(
        self, request: ProjectCompensationUnitCreateRequest
    ) -> ProjectCompensationUnitCreateResult:
        """Create, or exactly replay, one project points unit."""
