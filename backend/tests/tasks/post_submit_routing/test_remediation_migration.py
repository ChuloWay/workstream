"""0032 preserves genuine retained success outcomes and their exact evidence."""

import asyncio

import asyncpg
import pytest
from alembic import command

from app.db import session as db_session
from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests.migration_fixtures import (
    _add_current_cause_seed_columns,
    _config,
    _restore_current_cause_seed_columns,
)
from tests.reviews.lifecycle.transition_support import command_for, transition
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
)

pytestmark = pytest.mark.postgres_schema_contract


async def _activate_acceptance_lifecycle(access) -> None:
    """Use signed human authority to activate the retained false-policy branch."""
    administrator = await access.signed.actor("migration-administrator")
    operator = await access.signed.actor("migration-operator")
    code, result = await run_bootstrap(administrator.id, execute=True)
    assert code == 0 and result["result_code"] == "bootstrapped"
    await access.signed.grant(administrator, operator)
    await transition(await command_for(operator.id, "shadow"))
    live = await transition(await command_for(operator.id, "live"))
    assert live.generation == 2


async def _snapshot(connection) -> dict[str, list[asyncpg.Record]]:
    """Capture every retained owner touched by routing, excluding only the new column."""
    queries = {
        "manifests": (
            "SELECT (to_jsonb(r)-'routing_recommendation')::text AS value "
            "FROM public.task_post_submit_routing_manifests r ORDER BY r.id"
        ),
        "requests": (
            "SELECT to_jsonb(r)::text AS value "
            "FROM public.task_post_submit_routing_requests r ORDER BY r.route_operation_id"
        ),
        "audit": (
            "SELECT to_jsonb(r)::text AS value FROM public.audit_events r ORDER BY r.id"
        ),
        "outbox": (
            "SELECT to_jsonb(r)::text AS value FROM public.outbox_events r ORDER BY r.event_id"
        ),
        "acceptances": (
            "SELECT to_jsonb(r)::text AS value FROM public.final_acceptances r ORDER BY r.id"
        ),
        "contributions": (
            "SELECT to_jsonb(r)::text AS value FROM public.contribution_records r ORDER BY r.id"
        ),
        "tasks": (
            "SELECT to_jsonb(r)::text AS value FROM public.workstream_tasks r ORDER BY r.id"
        ),
        "assignments": (
            "SELECT to_jsonb(r)::text AS value FROM public.task_assignments r ORDER BY r.id"
        ),
    }
    return {name: await connection.fetch(sql) for name, sql in queries.items()}


async def _routing_validity(connection) -> list[asyncpg.Record]:
    """Return exact receipt hashes and all success-closure predicates."""
    return await connection.fetch(
        """
        SELECT m.id, m.human_review_required,
          m.authority_context->'source'->>'routing_recommendation' AS source_recommendation,
          public.task_routing_resource_digest(m) AS resource_digest,
          a.after_facts->>'resource_context_digest' AS receipt_digest,
          m.authorization_decision_id, m.audit_event_id, m.outcome_event_id,
          public.task_routing_receipt_valid(m) AS receipt_valid,
          public.task_routing_context_valid(m) AS context_valid,
          public.task_routing_outcome_complete(m) AS outcome_complete,
          CASE WHEN m.human_review_required THEN true ELSE
            public.task_routing_acceptance_matches(
              m.id,m.final_acceptance_id,m.authorization_decision_id,m.router_actor_id,
              m.project_id,m.task_id,m.submission_id,
              (m.authority_context#>>'{source,locked_policy,locked_review_policy_id}')::uuid,
              m.authorized_lifecycle_generation,false)
          END AS acceptance_valid
        FROM public.task_post_submit_routing_manifests m
        JOIN public.audit_events a ON a.id=m.authorization_decision_id
        ORDER BY m.human_review_required DESC
        """
    )


async def test_routing_upgrade_preserves_success_evidence(
    tmp_path,
    isolated_database_env,
    migration_lock,
    admin_access,
):
    """Upgrade real 0031 true/false outcomes without rewriting their evidence."""
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await connection.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0031_task_import_source")

        # Current application construction needs later nullable columns while it
        # writes genuine predecessor outcomes. Restore exact 0031 shape before upgrade.
        connection = await asyncpg.connect(url)
        try:
            await connection.execute(
                "ALTER TABLE public.task_post_submit_routing_manifests "
                "ADD COLUMN routing_recommendation varchar(32) NOT NULL"
            )
            cause_originals = await _add_current_cause_seed_columns(connection)
        finally:
            await connection.close()

        await _activate_acceptance_lifecycle(admin_access)
        async with authorized_routing_source(
            tmp_path / "human",
            isolated_database_env,
            human_review_required=True,
        ) as human:
            async with human.factory() as session, session.begin():
                human_result = await apply_outcome(session, human, None)
            async with authorized_routing_source(
                tmp_path / "automatic",
                isolated_database_env,
                human_review_required=False,
                storage_settings=human.settings,
                provision_services=False,
            ) as automatic:
                async with automatic.factory() as session, session.begin():
                    automatic_result = await apply_outcome(session, automatic, 2)

        assert human_result.final_acceptance_id is None
        assert automatic_result.final_acceptance_id is not None
        await db_session.dispose_engine()
        connection = await asyncpg.connect(url)
        try:
            await _restore_current_cause_seed_columns(connection, cause_originals)
            await connection.execute(
                "ALTER TABLE public.task_post_submit_routing_manifests "
                "DROP COLUMN routing_recommendation"
            )
            assert await connection.fetchval(
                "SELECT version_num FROM public.alembic_version"
            ) == "0031_task_import_source"
            before = await _snapshot(connection)
            before_validity = await _routing_validity(connection)
            assert len(before_validity) == 2
            assert all(
                row["source_recommendation"] == "allow_review"
                and row["resource_digest"] == row["receipt_digest"]
                and row["receipt_valid"]
                and row["context_valid"]
                and row["outcome_complete"]
                and row["acceptance_valid"]
                for row in before_validity
            )
        finally:
            await connection.close()

        await asyncio.to_thread(command.upgrade, _config(), "0032_checker_remediation")
        connection = await asyncpg.connect(url)
        try:
            assert await connection.fetchval(
                "SELECT version_num FROM public.alembic_version"
            ) == "0032_checker_remediation"
            assert await _snapshot(connection) == before
            after_validity = await _routing_validity(connection)
            assert after_validity == before_validity
            assert await connection.fetch(
                "SELECT routing_recommendation FROM "
                "public.task_post_submit_routing_manifests ORDER BY id"
            ) == [("allow_review",), ("allow_review",)]
        finally:
            await connection.close()
