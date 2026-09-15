"""Database lifecycle and commit custody reject bypassed product orchestration."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.models import ProjectGuide
from .pg_support import activation_case, activation_service


async def test_active_guide_cannot_be_superseded_without_exact_successor(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        guide_id = str(command.target.proposal.guide_id)
        # Preserve the valid activation binding; omit only successor activation.
        # The immediate lifecycle guard permits the shape, then commit must fail.
        with pytest.raises(DBAPIError, match="guide supersession requires exact successor activation"):
            async with factory() as session, session.begin():
                status = await session.scalar(
                    text("UPDATE project_guides SET status='superseded',superseded_at=now() "
                         "WHERE id=:id RETURNING status"),
                    dict(id=guide_id),
                )
                assert status == "superseded"
        async with factory() as session:
            guide = await session.get(ProjectGuide, guide_id)
            assert guide.status == "active"
            assert guide.superseded_at is None
            assert guide.mutation_generation == receipt.activation_generation
            assert await load_guide_activation(session, guide) == receipt
            assert await session.scalar(text(
                "SELECT count(*) FROM project_guides WHERE project_id=:project AND status='active'"
            ), dict(project=guide.project_id)) == 1


async def test_project_and_guide_cannot_activate_without_custody(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, _, _, _, _):
        for sql, expected in (
            (
                "UPDATE projects SET status='active' WHERE id=:id",
                "project activation requires exact guide custody",
            ),
            (
                "UPDATE project_guides SET status='active',mutation_generation=mutation_generation+1,approved_by='manager',effective_at=now() WHERE project_id=:id",
                "active guide requires complete activation binding",
            ),
        ):
            with pytest.raises(DBAPIError, match=expected):
                async with factory() as session, session.begin():
                    await session.execute(
                        text(sql), dict(id=str(command.target.proposal.project_id))
                    )
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "draft"
            assert (
                await session.scalar(
                    text("SELECT status FROM projects WHERE id=:id"), dict(id=guide.project_id)
                )
                == "draft"
            )


async def test_pending_activation_receipt_cannot_commit(clean_postgres_database, monkeypatch):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        from app.modules.projects.guide_mutation_repository import GuideMutationRepository

        async def omit_only_receipt(*args, **kwargs):
            return None

        monkeypatch.setattr(GuideMutationRepository, "complete", omit_only_receipt)
        with pytest.raises(DBAPIError, match="guide activation immutable custody mismatch"):
            async with factory() as session, session.begin():
                receipt = await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )
                guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
                assert (
                    guide.status == "active"
                    and guide.activation_operation_id == receipt.operation_id
                )
                assert (
                    guide.contribution_policy_version_id == command.contribution_policy_version_id
                )
                assert (
                    await session.scalar(
                        text(
                            "SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'"
                        )
                    )
                    == 1
                )
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )
            assert (
                await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            ).status == "draft"


async def test_committed_binding_and_receipt_are_immutable(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        for sql, expected in (
            (
                "UPDATE project_guides SET contribution_policy_version_id=:other WHERE activation_operation_id=:operation",
                "guide activation binding is immutable",
            ),
            (
                "UPDATE project_guides SET activation_operation_id=:other WHERE activation_operation_id=:operation",
                "guide activation binding is immutable",
            ),
            (
                "DELETE FROM guide_mutation_idempotency_records WHERE operation_id=:operation",
                "guide mutation custody is immutable",
            ),
            (
                "UPDATE guide_mutation_idempotency_records SET activation_facts_json='{}'::json WHERE operation_id=:operation",
                "guide activation operation is immutable",
            ),
        ):
            with pytest.raises(DBAPIError, match=expected):
                async with factory() as session, session.begin():
                    await session.execute(
                        text(sql), dict(other=uuid4(), operation=receipt.operation_id)
                    )


async def test_activation_audit_preserves_closed_resource_and_privacy_bounds(
    clean_postgres_database,
):
    from sqlalchemy import select
    from app.modules.tasks.models import AuditEvent
    from tests.authorization.contribution_policies.test_migration import clone_decision

    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        async with factory() as session, session.begin():
            await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        async with factory() as session:
            event = await session.scalar(
                select(AuditEvent).where(AuditEvent.action_id == "project.guide.activate")
            )
        control = await clone_decision(event, {})
        async with factory() as session:
            assert await session.get(AuditEvent, control) is not None
        for changes, constraint in (
            (
                {"resource_type": "project_guide_activation_extra"},
                "ck_audit_events_authority_privacy_bounds",
            ),
            (
                {"after_facts": {**event.after_facts, "private_material": "forbidden"}},
                "ck_audit_events_fact_bounds",
            ),
            ({"permission_id": "project.read"}, "ck_audit_events_authorization_action_evidence"),
        ):
            with pytest.raises(DBAPIError, match=constraint):
                await clone_decision(event, changes)


async def test_database_rejects_active_insert_and_copied_activation_audit(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        # Isolate the immediate lifecycle INSERT guard, before deferred creation custody.
        async with factory() as session:
            await session.begin()
            with pytest.raises(DBAPIError, match="new guides must be draft and unbound"):
                await session.execute(
                    text(
                        "INSERT INTO project_guides(id,project_id,version,status,created_by,task_examples,task_examples_hash) "
                        "SELECT :new,project_id,'forged-active','active',created_by,task_examples,task_examples_hash "
                        "FROM project_guides WHERE id=:guide"
                    ),
                    dict(new=str(uuid4()), guide=str(command.target.proposal.guide_id)),
                )
            await session.rollback()
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        async with factory() as session:
            await session.begin()
            # A new row/key/operation cannot reuse the consumed decision. Assert the
            # immediate uniqueness boundary; do not let later custody mask it.
            with pytest.raises(DBAPIError, match="uq_guide_activation_audit_decision"):
                await session.execute(
                    text(
                        "INSERT INTO guide_mutation_idempotency_records "
                        "SELECT (jsonb_populate_record(NULL::guide_mutation_idempotency_records, "
                        "to_jsonb(r) || jsonb_build_object('id',cast(:id as text), "
                        "'operation_id',cast(:operation as text),'idempotency_key',cast(:key as text), "
                        "'status','pending','committed_at',NULL,'response_json',NULL))).* "
                        "FROM guide_mutation_idempotency_records r WHERE operation_id=:original"
                    ),
                    dict(
                        id=str(uuid4()),
                        operation=str(uuid4()),
                        key=str(uuid4()),
                        original=receipt.operation_id,
                    ),
                )
            await session.rollback()


async def test_binding_model_and_migration_share_exact_foreign_keys(clean_postgres_database):
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.modules.projects.models import GuideMutationIdempotencyRecord

    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.connect() as connection:

            def compare(sync):
                inspector = inspect(sync)
                for table, names in (
                    (
                        ProjectGuide.__table__,
                        {
                            "fk_project_guides_contribution_policy",
                            "fk_project_guides_activation_operation",
                        },
                    ),
                    (GuideMutationIdempotencyRecord.__table__, set()),
                ):
                    stored_columns = {row["name"]: row for row in inspector.get_columns(table.name)}
                    for column in table.columns:
                        if column.name.startswith("activation_") or column.name in {
                            "contribution_policy_id",
                            "contribution_policy_version_id",
                        }:
                            actual = stored_columns[column.name]
                            assert actual["nullable"] == column.nullable
                            assert str(actual["type"]) == str(
                                column.type.compile(dialect=sync.dialect)
                            )
                    actual = {row["name"]: row for row in inspector.get_foreign_keys(table.name)}
                    for constraint in table.foreign_key_constraints:
                        if constraint.name not in names:
                            continue
                        row = actual[constraint.name]
                        assert row["constrained_columns"] == [
                            element.parent.name for element in constraint.elements
                        ]
                        assert row["referred_columns"] == [
                            element.column.name for element in constraint.elements
                        ]
                        assert row["referred_table"] == constraint.referred_table.name
                        assert row.get("options", {}).get("deferrable", False) == bool(
                            constraint.deferrable
                        )
                    assert names <= set(actual)

            await connection.run_sync(compare)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(("path", "value"), [
    (("command", "review", "extra"), "unrequested"),
    (("command", "revision", "extra"), "unrequested"),
    (("command", "review", "generation"), "1"),
    (("command", "revision", "generation"), True),
    (("contribution", "rules_and_definitions_digest"), "not-a-digest"),
    (("contribution", "adapter_binding_ids"), {}),
    (("contribution", "adapter_binding_ids"), ["not-a-uuid"]),
    (("contribution", "adapter_binding_ids"), [None]),
    (("contribution", "version_number"), "1"),
    (("command", "guide_mutation_generation"), "as_text"),
    (("activation_generation",), "as_text"),
    (("effective_at",), "without_timezone"),
])
async def test_database_rejects_unreadable_nested_receipt(
    clean_postgres_database, monkeypatch, path, value,
):
    """A faulty serializer cannot strand a binding with otherwise consistent custody."""
    from copy import deepcopy
    from app.core.hashing import canonical_json_hash
    from app.modules.projects.api.guide_activation import GuideActivationFacts
    from app.modules.projects.guide_mutation_repository import GuideMutationRepository

    original_facts = GuideActivationFacts.resource_json
    original_reserve = GuideMutationRepository.reserve
    original_complete = GuideMutationRepository.complete

    def corrupt(receipt):
        body = deepcopy(receipt)
        parent = body
        for key in path[:-1]:
            parent = parent[key]
        if value == "as_text":
            parent[path[-1]] = str(parent[path[-1]])
        elif value == "without_timezone":
            parent[path[-1]] = parent[path[-1]].removesuffix("+00:00").removesuffix("Z")
        else:
            parent[path[-1]] = value
        return body

    def malformed_facts(self):
        body = original_facts(self)
        body["receipt"] = corrupt(body["receipt"])
        return body

    async def reserve(self, **kwargs):
        # The real authority participant records this altered facts digest in its
        # fresh audit decision. Match the command digest too, isolating shape.
        kwargs["request_digest"] = canonical_json_hash(
            kwargs["activation_facts_json"]["receipt"]["command"]
        )
        return await original_reserve(self, **kwargs)

    async def complete(self, record, *, response_json):
        body = corrupt(response_json)
        assert record.request_digest == canonical_json_hash(body["command"])
        assert record.activation_facts_json["receipt"] == body
        assert record.resource_context_digest == canonical_json_hash(record.activation_facts_json)
        assert record.activation_authority_json["resource_context_digest"] == record.resource_context_digest
        return await original_complete(self, record, response_json=body)

    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        with monkeypatch.context() as patch:
            patch.setattr(GuideActivationFacts, "resource_json", malformed_facts)
            patch.setattr(GuideMutationRepository, "reserve", reserve)
            patch.setattr(GuideMutationRepository, "complete", complete)
            with pytest.raises(DBAPIError, match="guide activation nested receipt shape mismatch"):
                async with factory() as session, session.begin():
                    await activation_service(session, actor, command, grant).activate(
                        command, actor=actor, request_id=uuid4()
                    )
        async with factory() as session:
            assert (await session.get(ProjectGuide, str(command.target.proposal.guide_id))).status == "draft"
            assert await session.scalar(text(
                "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
            )) == 0
            assert await session.scalar(text(
                "SELECT count(*) FROM audit_events WHERE action_id='project.guide.activate'"
            )) == 0
        # The same exact approved input commits and remains readable after repair.
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        async with factory() as session:
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert await load_guide_activation(session, guide) == receipt
