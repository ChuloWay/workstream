"""Canonical current-head lookup for current-schema assertions."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _config():
    return Config(Path(__file__).resolve().parents[1] / "alembic.ini")


def current_schema_revision():
    """Require one canonical Alembic head for current-schema assertions."""
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert len(heads) == 1
    return heads[0]


async def add_current_art_seed_column(database_url):
    """Let current ART seed real records; caller must restore before migration proof."""
    import asyncpg
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        columns = await connection.fetch("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='pre_submit_evidence_sets' ORDER BY ordinal_position")
        names = tuple(row[0] for row in columns)
        assert "semantic_manifest_body" not in names
        await connection.execute("ALTER TABLE public.pre_submit_evidence_sets ADD COLUMN semantic_manifest_body json")
        return names
    finally:
        await connection.close()


async def restore_predecessor_evidence_schema(database_url, original_columns):
    """Restore predecessor row shape before snapshots, upgrades, and concurrency probes."""
    import asyncpg
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        before = await connection.fetch("SELECT id FROM public.pre_submit_evidence_sets ORDER BY id")
        assert before, "historical fixture must retain actual evidence"
        await connection.execute("ALTER TABLE public.pre_submit_evidence_sets DROP COLUMN semantic_manifest_body")
        columns = await connection.fetch("SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='pre_submit_evidence_sets' ORDER BY ordinal_position")
        assert tuple(row[0] for row in columns) == original_columns
        assert await connection.fetch("SELECT id FROM public.pre_submit_evidence_sets ORDER BY id") == before
    finally:
        await connection.close()
