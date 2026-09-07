"""Report the installed lineage predicate behind an unexpected fixture failure."""

from dataclasses import asdict
import json
import re

from sqlalchemy import text


async def lineage_mismatches(factory, facts):
    """Evaluate installed guard predicates after the failed transaction rolls back."""
    async with factory() as session:
        definition = await session.scalar(
            text("select pg_get_functiondef('guard_project_guide_setup_finalization()'::regprocedure)")
        )
        condition = definition.split("if c.id is null", 1)[1].split(
            "then raise exception 'finalization compilation lineage mismatch'", 1
        )[0]
        predicates = re.split(r"\s+or\s+", "c.id is null" + condition.rstrip())
        payload = asdict(facts)
        payload["id"] = payload.pop("finalization_id")
        query = "select " + ",".join(
            f"({predicate}) as predicate_{index}" for index, predicate in enumerate(predicates)
        )
        query += (
            " from jsonb_populate_record(null::project_guide_setup_finalizations,cast(:row as jsonb)) new"
            " left join project_guide_compilations c on c.id=new.compilation_id"
            " left join project_guide_compilation_attempts a on a.id=new.attempt_id"
            " left join project_guide_compilation_request_operations q on q.operation_id=new.request_operation_id"
            " left join project_setup_runs s on s.id=new.setup_run_id"
            " left join project_guides g on g.id=new.guide_id"
            " left join guide_source_snapshots snap on snap.id=new.source_snapshot_id"
        )
        result = (await session.execute(text(query), {"row": json.dumps(payload, default=str)})).one()
        return [predicate for predicate, failed in zip(predicates, result, strict=True) if failed]
