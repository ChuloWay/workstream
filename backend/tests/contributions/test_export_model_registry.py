"""Canonical-only process discovery must include private export membership custody."""

from pathlib import Path
import subprocess
import sys


def test_export_membership_is_registered_without_loading_its_read_repository():
    code = '''
import sys
import app.db.models
from app.db.base import Base
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects.postgresql import dialect
assert "app.modules.contributions.records.read_repository" not in sys.modules
for name in ("contribution_export_memberships", "contribution_export_members"):
    assert name in Base.metadata.tables, name
    table = Base.metadata.tables[name]
    assert table.foreign_keys
    for foreign_key in table.foreign_keys:
        assert foreign_key.column is not None
    assert str(CreateTable(table).compile(dialect=dialect()))
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
