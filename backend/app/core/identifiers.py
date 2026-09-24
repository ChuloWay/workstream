"""Workstream-owned record identity generation, independent of request keys."""

from uuid import UUID

from uuid6 import uuid7


def new_record_id() -> UUID:
    """Return an RFC 9562 UUIDv7 as the standard-library UUID value type.

    Generate once for a new record; retries recover the persisted identity through
    the owning operation's unique request key. This is not a clock, secret,
    authorization decision, or globally ordered transaction sequence.
    """
    return UUID(int=uuid7().int)
