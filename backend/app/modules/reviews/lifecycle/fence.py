"""The one REV mutation lock, retained until the caller ends its root transaction."""

import hashlib

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.api.lifecycle import (
    JointLifecycleControlFacts,
    JointLifecyclePhase,
    JointLifecycleUnavailable,
)
from app.modules.reviews.lifecycle.models import JointLifecycleReleaseControl

# Stable across processes and future transition writers; not derived from requests.
JOINT_LIFECYCLE_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"workstream.review.joint_lifecycle_mutation").digest()[:8],
    "big",
    signed=True,
)


class PostgresJointLifecycleMutationFence:
    """Acquire advisory then controller-row locks without owning commit or AUTH."""

    def __init__(self, session: AsyncSession) -> None:
        """Use the caller's session for all fence and later participant work."""
        self._session = session

    async def acquire(self, expected_generation: int) -> JointLifecycleControlFacts:
        """Return current locked scalar facts only for the expected generation."""
        transaction = self._session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
            or type(expected_generation) is not int
            or not 0 <= expected_generation <= 9_223_372_036_854_775_807
        ):
            raise JointLifecycleUnavailable(
                "lifecycle requires a root transaction and exact generation"
            )
        await self._session.execute(
            text("SELECT pg_catalog.pg_advisory_xact_lock(:key)"),
            {"key": JOINT_LIFECYCLE_LOCK_KEY},
        )
        # Scalar selection cannot reuse a stale ORM identity-map instance.
        row = (
            await self._session.execute(
                select(
                    JointLifecycleReleaseControl.id,
                    JointLifecycleReleaseControl.phase,
                    JointLifecycleReleaseControl.generation,
                    JointLifecycleReleaseControl.created_at,
                )
                .where(JointLifecycleReleaseControl.singleton.is_(True))
                .with_for_update()
            )
        ).one_or_none()
        if row is None or row.generation != expected_generation:
            raise JointLifecycleUnavailable("lifecycle controller missing or generation changed")
        try:
            return JointLifecycleControlFacts(
                singleton_id=row.id,
                phase=JointLifecyclePhase(row.phase),
                generation=row.generation,
                created_at=row.created_at,
            )
        except (ValueError, ValidationError) as exc:
            raise JointLifecycleUnavailable("lifecycle controller malformed") from exc
