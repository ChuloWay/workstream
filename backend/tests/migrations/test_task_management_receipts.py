"""Real forward migration fences concurrent writers and preserves retained rows."""

import asyncio
from uuid import uuid4

from alembic import command, op
import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.test_outbox_dispatch_identity import config, seed
from tests.project_create_fixtures import insert_historical_project

pytestmark = pytest.mark.postgres_schema_contract
REVISION = "0030_task_management"


async def retained_receipt(url, *, existing_task):
    actor = await seed(url, "workstream.artifact.verifier")
    task, project, receipt = str(uuid4()), str(uuid4()), uuid4()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            if existing_task:
                await insert_historical_project(
                    connection, project_id=project, name="Retained project", slug=uuid4().hex
                )
                await connection.execute(
                    text("""insert into workstream_tasks
                    (id,project_id,title,description,status,created_by,skill_tags,source_type)
                    values(:task,:project,'Draft','Task body','draft',:actor,'[]','manual')"""),
                    {"task": task, "project": project, "actor": actor},
                )
            await connection.execute(
                text("""insert into task_command_receipts
              (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status)
              values(:id,:actor,'task.claim',:key,'sha256:'||repeat('a',64),:task,'pending')"""),
                {"id": receipt, "actor": actor, "key": uuid4(), "task": task},
            )
        return receipt
    finally:
        await engine.dispose()


async def snapshot(url, receipt):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        return await connection.fetchval(
            "select to_jsonb(r)::text from task_command_receipts r where id=$1", receipt
        )
    finally:
        await connection.close()


@pytest.mark.parametrize("existing_task", [True, False])
def test_upgrade_preserves_receipts_or_refuses_unprovable_custody(
    isolated_database_env, migration_lock, migration_schema_at, existing_task
):
    with migration_lock():
        migration_schema_at("0029_assignment_authority")
        receipt = asyncio.run(retained_receipt(isolated_database_env, existing_task=existing_task))
        before = asyncio.run(snapshot(isolated_database_env, receipt))
        if existing_task:
            command.upgrade(config(), REVISION)
        else:
            with pytest.raises(Exception, match="unproven task receipt custody"):
                command.upgrade(config(), REVISION)
        assert asyncio.run(snapshot(isolated_database_env, receipt)) == before


@pytest.mark.parametrize("remove_lock", [False, True])
def test_upgrade_fences_receipt_writer_before_inspecting_rows(
    isolated_database_env, migration_lock, migration_schema_at, monkeypatch, remove_lock
):
    with migration_lock():
        migration_schema_at("0029_assignment_authority")
        actor = asyncio.run(seed(isolated_database_env, "workstream.artifact.verifier"))
        if remove_lock:
            execute = op.execute

            def without_initial_lock(statement, *args, **kwargs):
                if str(statement).startswith("lock table task_command_receipts"):
                    return None
                return execute(statement, *args, **kwargs)

            monkeypatch.setattr(op, "execute", without_initial_lock)

        async def race():
            url = isolated_database_env.replace("+asyncpg", "")
            writer, observer = await asyncpg.connect(url), await asyncpg.connect(url)
            transaction = writer.transaction()
            await transaction.start()
            receipt = uuid4()
            await writer.execute(
                """insert into task_command_receipts
              (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status)
              values($1,$2,'task.claim',$3,'sha256:'||repeat('a',64),$4,'pending')""",
                receipt,
                actor,
                uuid4(),
                str(uuid4()),
            )
            upgrade = asyncio.create_task(asyncio.to_thread(command.upgrade, config(), REVISION))
            try:
                waiting = False
                for _ in range(250):
                    waiting = await observer.fetchval("""select exists(select 1 from pg_locks l
                      join pg_stat_activity a on a.pid=l.pid where a.datname=current_database()
                      and l.relation='task_command_receipts'::regclass and not l.granted
                      and a.query like 'lock table task_command_receipts%')""")
                    if waiting:
                        break
                    await asyncio.sleep(0.02)
                assert waiting and not upgrade.done(), "migration must lock before preflight"
            finally:
                await transaction.commit()
                try:
                    with pytest.raises(Exception) as failure:
                        await asyncio.wait_for(upgrade, 30)
                    if not remove_lock:
                        assert "unproven task receipt custody" in str(failure.value)
                finally:
                    await writer.close()
                    await observer.close()
            assert await snapshot(isolated_database_env, receipt) is not None

        if remove_lock:
            with pytest.raises(AssertionError, match="migration must lock before preflight"):
                asyncio.run(race())
        else:
            asyncio.run(race())


def test_upgrade_preserves_committed_assignment_receipts(
    isolated_database_env, migration_lock, migration_schema_at
):
    """Arrange valid prior-schema assignment custody; upgrade never rewrites evidence."""
    from app.adapters.tasks import task_service
    from app.core.config import get_settings
    from app.core.hashing import canonical_json_hash
    from app.modules.tasks.models import WorkstreamTask, TaskAssignment, TaskCommandReceipt
    from app.modules.tasks.service import LOCKED_CONTEXT_REQUIRED_FIELDS
    from tests.projects.locked_policy_fixtures import activated_context

    async def arrange():
        async with activated_context(isolated_database_env) as (factory, activation, actor, *_):
            async with factory() as session, session.begin():
                task = WorkstreamTask(
                    id=str(uuid4()),
                    project_id=str(activation.command.target.proposal.project_id),
                    title="Retained work",
                    description="Retained description",
                    acceptance_criteria="Complete the guide requirements",
                    status="draft",
                    created_by=str(actor.actor_profile_id),
                )
                session.add(task)
                await session.flush()
                service = task_service(session, settings=get_settings())
                facts = await service._load_active_policy_context(task.project_id)
                service._stamp_locked_context(task, facts)
                task.status = "screening"
                await session.flush()
                task.status = "ready"
                await session.flush()
                assignment = TaskAssignment(
                    id=str(uuid4()),
                    task_id=task.id,
                    project_id=task.project_id,
                    contributor_id=str(actor.actor_profile_id),
                    assigned_by=str(actor.actor_profile_id),
                    status="active",
                    submitter_contribution_policy_version_id=task.locked_contribution_policy_version_id,
                )
                session.add(assignment)
                await session.flush()
                task.assigned_to = assignment.contributor_id
                task.status = "claimed"
                await session.flush()
                digest = canonical_json_hash(
                    {
                        field: str(getattr(task, field))
                        if field == "locked_contribution_policy_version_id"
                        else getattr(task, field)
                        for field in LOCKED_CONTEXT_REQUIRED_FIELDS
                    }
                )
                from datetime import UTC, datetime
                from app.modules.tasks.schemas import AssignmentResponse, TaskWithAssignmentResponse

                await session.refresh(task)
                result = TaskWithAssignmentResponse(
                    task=service.task_response_for_authority(task, can_manage=False),
                    assignment=AssignmentResponse.model_validate(assignment),
                )
                identities = []
                for operation in ("task.claim", "task.start"):
                    identity = uuid4()
                    identities.append(identity)
                    session.add(
                        TaskCommandReceipt(
                            id=identity,
                            actor_profile_id=assignment.contributor_id,
                            action_id=operation,
                            idempotency_key=uuid4(),
                            request_digest=digest,
                            task_id=task.id,
                            status="committed",
                            assignment_id=assignment.id,
                            contributor_id=assignment.contributor_id,
                            locked_context_hash=digest,
                            response=result.model_dump(mode="json")
                            if operation == "task.claim"
                            else result.task.model_copy(
                                update={"status": "in_progress"}
                            ).model_dump(mode="json"),
                            committed_at=datetime.now(UTC),
                        )
                    )
                task.status = "in_progress"
            return identities

    with migration_lock():
        migration_schema_at("0029_assignment_authority")
        identities = asyncio.run(arrange())
        before = [asyncio.run(snapshot(isolated_database_env, identity)) for identity in identities]
        command.upgrade(config(), REVISION)
        assert [
            asyncio.run(snapshot(isolated_database_env, identity)) for identity in identities
        ] == before
