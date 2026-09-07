"""Rebind forged SQL receipts so ownership probes cannot fail on stale digests."""

import json
from uuid import uuid4

from sqlalchemy import text

from app.modules.tasks.models import AuditEvent


async def rebind_forged_evidence(session, row):
    """Intentionally forge self-consistent evidence; the database must still deny wrong custody."""

    async def digest(function):
        payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        return await session.scalar(
            text(
                "select "
                + function
                + "(jsonb_populate_record(null::project_guide_setup_finalizations, "
                "cast(:payload as jsonb)))"
            ),
            {"payload": json.dumps(payload, default=str)},
        )

    row.facts_digest = await digest("project_guide_finalization_digest")
    row.authority_resource_digest = await digest("project_guide_finalization_authority_digest")
    decision = str(uuid4())
    columns = [column.name for column in AuditEvent.__table__.columns]
    overrides = {
        "id": ":decision",
        "entity_id": ":decision",
        "after_facts": "jsonb_build_object('allowed',true,'resource_context_digest',cast(:digest as text))::json",
    }
    await session.execute(
        text(
            "insert into audit_events ("
            + ",".join(columns)
            + ") select "
            + ",".join(overrides.get(column, column) for column in columns)
            + " from audit_events where id=:original"
        ),
        {
            "decision": decision,
            "original": row.authorization_decision_event_id,
            "digest": row.authority_resource_digest,
        },
    )
    row.authorization_decision_event_id = decision
