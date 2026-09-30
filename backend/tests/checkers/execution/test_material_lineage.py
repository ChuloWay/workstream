"""Canonical ART membership is enforced at commit, including retained failed runs."""

import pytest
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.modules.checkers.models import CheckerRun, CheckerResult
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from app.modules.outbox.models import OutboxEvent
from tests.post_submit_materialization_helpers import material_fixture
from .support import controlled_executor, reserve
from .test_concurrency import final_facts
from .material_storage_helpers import write_terminal


def terminal_facts(h, lease, outcome):
    facts = final_facts(h, lease)
    if outcome == "infrastructure_failed":
        body = facts.result.model_dump(exclude={"result_digest"})
        body.update(outcome=outcome, member_results=(), infrastructure_failure_code="implementation_unavailable")
        facts = facts.model_copy(update={"result": make_post_submit_result(**body)})
    return facts


@pytest.mark.parametrize("outcome", ["completed", "infrastructure_failed"])
async def test_foreign_canonical_material_is_rejected_at_commit(tmp_path, isolated_database_env, outcome):
    async with material_fixture(tmp_path / "own", isolated_database_env) as h:
        async with material_fixture(tmp_path / "foreign", isolated_database_env,
                                    storage_settings=h.settings, provision_services=False) as foreign:
            await reserve(h)
            lease, _ = await controlled_executor(h)._claim(h.request)
            facts = terminal_facts(h, lease, outcome)
            canonical = facts.material.model_dump(mode="json")
            substitutions = {
                "admission_id": str(foreign.created.admission_id),
                "replica_id": str(foreign.replica_id),
                "semantic_manifest_sha256": foreign.manifest.sha256,
            }
            async with h.factory() as session:
                before_events = await session.scalar(select(func.count()).select_from(OutboxEvent))
                before = (await session.get(CheckerRun, str(facts.result.attempt_id))).finalize_evidence_id
            for field, value in substitutions.items():
                assert canonical[field] != value
                async with h.factory() as session:
                    await write_terminal(session, facts, canonical | {field: value})
                    # Only commit invokes the deferred guard; preceding member and
                    # event inserts/terminal UPDATE all completed successfully.
                    with pytest.raises(IntegrityError, match="checker material canonical ART lineage mismatch"):
                        await session.commit()
                    await session.rollback()
                async with h.factory() as session:
                    run = await session.get(CheckerRun, str(facts.result.attempt_id))
                    assert run.status == "running" and run.result_json is None and run.material_custody is None
                    assert run.finalize_evidence_id == before and run.completion_event_id is None
                    assert await session.scalar(select(func.count()).select_from(CheckerResult)) == 0
                    assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == before_events
            async with h.factory() as session, session.begin():
                await write_terminal(session, facts, canonical)
            async with h.factory() as session:
                stored = await session.get(CheckerRun, str(facts.result.attempt_id))
                assert stored.status == outcome and stored.material_custody == canonical
