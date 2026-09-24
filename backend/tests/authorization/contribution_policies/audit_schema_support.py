"""Shared direct-SQL helpers for contribution-policy audit schema tests."""

import json

from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.db import session as db_session


CONSTRAINTS = (
    "ck_audit_events_authority_privacy_bounds",
    "ck_audit_events_authorization_action_evidence",
    "ck_audit_events_authority_registries",
)


async def schema_value(statement: str):
    """Read one installed schema fact through an independent session."""
    async with db_session.get_session_factory()() as session:
        return await session.scalar(text(statement))


async def clone_decision(event, changes: dict) -> str:
    """Clone an audit row to exercise the database's closed vocabulary."""
    identity = str(new_record_id())
    payload = {"id": identity, "entity_id": identity, **changes}
    async with db_session.get_session_factory()() as session, session.begin():
        await session.execute(
            text(
                "insert into audit_events select "
                "(jsonb_populate_record(null::audit_events, "
                "to_jsonb(a) || cast(:changes as jsonb))).* "
                "from audit_events a where a.id=:id"
            ),
            {"id": event.id, "changes": json.dumps(payload)},
        )
    return identity
