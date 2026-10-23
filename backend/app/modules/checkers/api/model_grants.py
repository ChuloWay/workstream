"""Private invocation grants linking isolated project images to the model proxy."""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from app.modules.checkers.api.model_calls import (
    ModelActionEvidence,
    ModelCallExecutionFacts,
    ModelPaidSlotKey,
)


class ModelInvocationGrantAuthorityPort(Protocol):
    """Issue one bounded callback capability without authorizing provider spend."""

    async def authorize_grant(
        self, execution: ModelCallExecutionFacts, slot: ModelPaidSlotKey,
        external_request_digest: str, token_hash: str,
    ) -> ModelActionEvidence:
        """Authorize the exact invocation, request binding and opaque token hash."""


@dataclass(frozen=True, slots=True)
class ModelInvocationGrantFacts:
    """Immutable owner facts selected privately by the proxy, never image input."""

    token_hash: str = field(repr=False)
    external_request_digest: str
    execution: ModelCallExecutionFacts
    slot: ModelPaidSlotKey
    registry_entry_id: UUID
