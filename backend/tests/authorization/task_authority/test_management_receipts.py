"""Independent SQL guards for pre-assignment command receipts."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    create_active_project,
    create_draft_task,
)


async def test_manager_receipt_rejects_unproven_sql_shape(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    for field, value, constraint in [
        ("task", str(uuid4()), "fk_task_command_task"),
        ("assignment", str(uuid4()), "task_command_state_shape"),
        ("contributor", str(uuid4()), "task_command_state_shape"),
        ("hash", None, "task_command_state_shape"),
        ("hash", "not-a-digest", "task_command_state_shape"),
        ("action", "task.claim", "task_command_state_shape"),
        ("action", "project.task.unknown", "task_command_action"),
    ]:
        params = dict(
            actor=task["created_by"],
            task=task["id"],
            action="project.task.create",
            assignment=None,
            contributor=None,
            hash="sha256:" + "a" * 64,
        )
        params[field] = value
        async with db_session.get_session_factory()() as session:
            with pytest.raises(IntegrityError, match=constraint):
                await session.execute(
                    text("""insert into task_command_receipts
                  (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status,
                   assignment_id,contributor_id,locked_context_hash,response,committed_at)
                  values(gen_random_uuid(),:actor,:action,gen_random_uuid(),'sha256:'||repeat('a',64),
                         :task,'committed',:assignment,:contributor,:hash,'{}'::jsonb,now())"""),
                    params,
                )
                await session.commit()
            await session.rollback()


async def test_pending_create_requires_task_by_commit(task_client):
    project = await create_active_project(task_client)
    existing = await create_draft_task(task_client, project["id"])
    for insert_task in (False, True):
        task_id = str(uuid4())
        async with db_session.get_session_factory()() as session:
            await session.execute(
                text("""insert into task_command_receipts
              (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status)
              values(gen_random_uuid(),:actor,'project.task.create',gen_random_uuid(),
                     'sha256:'||repeat('a',64),:task,'pending')"""),
                {"actor": existing["created_by"], "task": task_id},
            )
            if insert_task:
                await session.execute(
                    text("""insert into workstream_tasks
                    (id,project_id,title,description,status,created_by,skill_tags,source_type)
                    values(:task,:project,'Draft','Task body','draft',:actor,'[]','manual')"""),
                    {"task": task_id, "project": project["id"], "actor": existing["created_by"]},
                )
                await session.commit()
            else:
                with pytest.raises(IntegrityError, match="fk_task_command_task"):
                    await session.commit()
                await session.rollback()


async def test_missing_task_proof_detects_removed_custody_guard(task_client):
    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])

    async def assert_missing_task_rejected(session):
        with pytest.raises(IntegrityError, match="fk_task_command_task"):
            await session.execute(
                text("""insert into task_command_receipts
              (id,actor_profile_id,action_id,idempotency_key,request_digest,task_id,status)
              values(gen_random_uuid(),:actor,'project.task.create',gen_random_uuid(),
                     'sha256:'||repeat('a',64),:task,'pending')"""),
                {"actor": task["created_by"], "task": str(uuid4())},
            )
            await session.execute(text("set constraints all immediate"))

    async with db_session.get_session_factory()() as session:
        await assert_missing_task_rejected(session)
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        try:
            await session.execute(
                text("alter table task_command_receipts drop constraint fk_task_command_task")
            )
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                await assert_missing_task_rejected(session)
        finally:
            # Both the deliberately broken schema and orphan row are rolled back.
            await session.rollback()


async def test_manager_audit_sql_binds_complete_task_lineage(task_client):
    import json
    from tests.test_tasks import auth_headers

    project = await create_active_project(task_client)
    task = await create_draft_task(task_client, project["id"])
    response = await task_client.post(f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers())
    assert response.status_code == 200, response.text
    async with db_session.get_session_factory()() as session:
        original = await session.scalar(
            text("""select to_jsonb(a) from audit_events a
            where entity_id=:task and event_type='TaskScreened'"""),
            {"task": task["id"]},
        )
    for change in ("valid", "missing", "substitution", "extra"):
        candidate = json.loads(json.dumps(original))
        candidate["id"] = str(uuid4())
        payload = candidate["event_payload"]
        if change == "missing":
            del payload["locked_review_policy_hash"]
        elif change == "substitution":
            payload["locked_review_policy_hash"] = "sha256:" + "a" * 64
        elif change == "extra":
            payload["private_material"] = "must not persist"
        async with db_session.get_session_factory()() as session:
            statement = text("""insert into audit_events select * from
                jsonb_populate_record(null::audit_events, cast(:row as jsonb))""")
            try:
                if change == "valid":
                    await session.execute(statement, {"row": json.dumps(candidate)})
                else:
                    with pytest.raises(IntegrityError, match="task management audit mismatch"):
                        await session.execute(statement, {"row": json.dumps(candidate)})
            finally:
                await session.rollback()
