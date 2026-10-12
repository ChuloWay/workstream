"""Canonical current-head lookup for current-schema assertions."""

from pathlib import Path
from contextlib import asynccontextmanager

from alembic.config import Config
from alembic.script import ScriptDirectory


def _config():
    return Config(Path(__file__).resolve().parents[1] / "alembic.ini")


def current_schema_revision():
    """Require one canonical Alembic head for current-schema assertions."""
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1
    return heads[0]


_CAUSE_SEED_TABLES = (
    ("pre_submit_evidence_sets", "id"),
    ("submission_bundle_admissions", "id"),
    ("submission_dispatches", "submission_id"),
)


async def _add_current_cause_seed_columns(connection):
    """Let the current initial writer seed older tables without inventing a cause."""
    originals = {}
    for table, _ in _CAUSE_SEED_TABLES:
        columns = await connection.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position", table,
        )
        names = tuple(row[0] for row in columns)
        if names and "checker_remediation_manifest_id" not in names:
            revision = await connection.fetchval("SELECT version_num FROM public.alembic_version")
            assert int(revision[:4]) < 33, "only a predecessor may need seeding columns"
            await connection.execute(
                f"ALTER TABLE public.{table} ADD COLUMN checker_remediation_manifest_id uuid"
            )
            originals[table] = names
    return originals


async def _restore_current_cause_seed_columns(connection, originals):
    for table, names in originals.items():
        key = next(order for name, order in _CAUSE_SEED_TABLES if name == table)
        assert await connection.fetchval(
            f"SELECT count(*) FROM public.{table} "
            "WHERE checker_remediation_manifest_id IS NOT NULL"
        ) == 0
        before = await connection.fetch(
            f"SELECT (to_jsonb(r) - 'checker_remediation_manifest_id')::text AS value "
            f"FROM public.{table} r ORDER BY {key}"
        )
        await connection.execute(
            f"ALTER TABLE public.{table} DROP COLUMN checker_remediation_manifest_id"
        )
        columns = await connection.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position", table,
        )
        assert tuple(row[0] for row in columns) == names
        assert await connection.fetch(
            f"SELECT to_jsonb(r)::text AS value FROM public.{table} r ORDER BY {key}"
        ) == before


@asynccontextmanager
async def current_art_attempt_seed_schema(database_url):
    """Restore a predecessor's attempt shape before the migration under test."""
    import asyncpg
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    owned = False
    cause_originals = {}
    try:
        columns = await connection.fetch("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='artifact_put_attempts' ORDER BY ordinal_position")
        names = tuple(row[0] for row in columns)
        if "task_import_source_id" not in names:
            revision = await connection.fetchval("SELECT version_num FROM public.alembic_version")
            assert int(revision[:4]) < 31 and names, "only a populated predecessor may need seeding columns"
            await connection.execute("ALTER TABLE public.artifact_put_attempts ADD COLUMN task_import_source_id uuid")
            owned = True
        cause_originals = await _add_current_cause_seed_columns(connection)
        yield
    finally:
        try:
            await _restore_current_cause_seed_columns(connection, cause_originals)
            if owned:
                assert await connection.fetchval("SELECT count(*) FROM public.artifact_put_attempts "
                    "WHERE task_import_source_id IS NOT NULL") == 0
                before = await connection.fetch("SELECT (to_jsonb(r) - 'task_import_source_id')::text AS value "
                    "FROM public.artifact_put_attempts r ORDER BY id")
                await connection.execute("ALTER TABLE public.artifact_put_attempts DROP COLUMN task_import_source_id")
                restored = await connection.fetch("SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='artifact_put_attempts' ORDER BY ordinal_position")
                assert tuple(row[0] for row in restored) == names
                assert await connection.fetch("SELECT to_jsonb(r)::text AS value FROM public.artifact_put_attempts r ORDER BY id") == before
        finally:
            await connection.close()


async def add_current_art_seed_column(database_url):
    """Temporarily admit current ART columns; restore the predecessor before proof."""
    import asyncpg
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        columns = await connection.fetch("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='pre_submit_evidence_sets' ORDER BY ordinal_position")
        names = tuple(row[0] for row in columns)
        assert "semantic_manifest_body" not in names
        attempt_columns = await connection.fetch("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='artifact_put_attempts' ORDER BY ordinal_position")
        attempt_names = tuple(row[0] for row in attempt_columns)
        assert "task_import_source_id" not in attempt_names
        await connection.execute("ALTER TABLE public.pre_submit_evidence_sets ADD COLUMN semantic_manifest_body jsonb")
        await connection.execute("ALTER TABLE public.artifact_put_attempts ADD COLUMN task_import_source_id uuid")
        cause_originals = await _add_current_cause_seed_columns(connection)
        return names, attempt_names, cause_originals
    finally:
        await connection.close()


async def restore_predecessor_evidence_schema(database_url, original_columns):
    """Restore predecessor row shape before snapshots, upgrades, and concurrency probes."""
    import asyncpg
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await _restore_current_cause_seed_columns(connection, original_columns[2])
        evidence_before = await connection.fetch("SELECT (to_jsonb(r) - 'semantic_manifest_body')::text AS value "
            "FROM public.pre_submit_evidence_sets r ORDER BY id")
        assert evidence_before, "historical fixture must retain actual evidence"
        attempts_before = await connection.fetch("SELECT (to_jsonb(r) - 'task_import_source_id')::text AS value "
            "FROM public.artifact_put_attempts r ORDER BY id")
        assert await connection.fetchval("SELECT count(*) FROM public.artifact_put_attempts "
            "WHERE task_import_source_id IS NOT NULL") == 0
        await connection.execute("ALTER TABLE public.pre_submit_evidence_sets DROP COLUMN semantic_manifest_body")
        await connection.execute("ALTER TABLE public.artifact_put_attempts DROP COLUMN task_import_source_id")
        columns = await connection.fetch("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='pre_submit_evidence_sets' ORDER BY ordinal_position")
        assert tuple(row[0] for row in columns) == original_columns[0]
        attempt_columns = await connection.fetch("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='artifact_put_attempts' ORDER BY ordinal_position")
        assert tuple(row[0] for row in attempt_columns) == original_columns[1]
        assert await connection.fetch("SELECT to_jsonb(r)::text AS value FROM public.pre_submit_evidence_sets r ORDER BY id") == evidence_before
        assert await connection.fetch("SELECT to_jsonb(r)::text AS value FROM public.artifact_put_attempts r ORDER BY id") == attempts_before
    finally:
        await connection.close()
