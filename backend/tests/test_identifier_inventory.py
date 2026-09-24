from __future__ import annotations

import json
from pathlib import Path

from scripts.identifier_inventory import (
    FORMAT,
    _sql_created_table,
    build_inventory,
    parse_orm_models,
    render_text,
)


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_current_repository_inventory_has_no_unowned_or_mismatched_keys() -> None:
    report = build_inventory(Path(__file__).resolve().parents[1])
    assert report["unresolved"] == []
    assert report["string_uuid_references"] == []


def test_orm_ast_inventory_captures_multiline_and_table_level_foreign_keys(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend"
    model_path = backend / "app/modules/example/models.py"
    _write(
        model_path,
        """
from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

class Parent:
    __tablename__ = "parents"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)

class Child:
    __tablename__ = "children"
    __table_args__ = (
        ForeignKeyConstraint(
            ["parent_id", "tenant_id"],
            ["parents.id", "tenants.id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str] = mapped_column(
        ForeignKey(
            "parents.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
""",
    )

    tables = parse_orm_models(backend / "app", backend)

    child = tables["children"]
    assert child["primary_key"] == ["id"]
    columns = {column["name"]: column for column in child["columns"]}
    assert columns["parent_id"]["foreign_keys"] == ["parents.id"]
    assert columns["parent_id"]["storage_kind"] == "native_uuid"
    assert columns["parent_id"]["storage_inferred_from_foreign_key"] is True
    assert columns["tenant_id"]["foreign_keys"] == ["tenants.id"]
    assert tables["parents"]["columns"][0]["storage_kind"] == "native_uuid"


def test_sql_inventory_reuses_quote_aware_baseline_statement_splitting() -> None:
    source = """
CREATE FUNCTION ignored() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 'a;still-in-function';
END $$;
CREATE TABLE public.delivery_attempts (
  event_id uuid REFERENCES public.outbox_events(event_id),
  claim_generation bigint NOT NULL,
  note character varying(36),
  CONSTRAINT pk_delivery PRIMARY KEY (event_id, claim_generation)
);
"""

    table = _sql_created_table(source, "migration.py")["delivery_attempts"]

    assert table["primary_key"] == ["event_id", "claim_generation"]
    columns = {column["name"]: column for column in table["columns"]}
    assert columns["event_id"]["storage_kind"] == "native_uuid"
    assert columns["event_id"]["foreign_keys"] == []


def test_build_inventory_reports_cutover_candidates_and_unresolved_schema_objects(
    tmp_path: Path,
) -> None:
    backend = tmp_path / "backend"
    _write(
        backend / "app/modules/example/models.py",
        """
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

class Widget:
    __tablename__ = "widgets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

class WidgetUse:
    __tablename__ = "widget_uses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    widget_id: Mapped[str] = mapped_column(
        ForeignKey(
            "widgets.id",
        ),
        nullable=False,
    )
""",
    )
    _write(
        backend / "app/writers.py",
        """
def reserve():
    from uuid import uuid4
    operation_id = uuid4()
    return operation_id
""",
    )
    _write(
        backend / "scripts/drill.py",
        """
import uuid as identifier_source
request_id = identifier_source.uuid5(identifier_source.NAMESPACE_URL, "drill")
""",
    )
    _write(
        backend / "alembic/baseline/v01_baseline_manifest.json",
        json.dumps(
            {
                "tables": [
                    {"name": "widgets"},
                    {"name": "widget_uses"},
                    {"name": "migration_state"},
                ],
                "columns": [
                    {"table_name": "widgets", "name": "id", "data_type": "varchar(36)"},
                    {"table_name": "widget_uses", "name": "id", "data_type": "varchar(36)"},
                    {
                        "table_name": "widget_uses",
                        "name": "widget_id",
                        "data_type": "varchar(36)",
                    },
                    {"table_name": "migration_state", "name": "id", "data_type": "integer"},
                ],
                "constraints": [
                    {
                        "kind": "p",
                        "table_name": table,
                        "definition": "PRIMARY KEY (id)",
                    }
                    for table in ("widgets", "widget_uses", "migration_state")
                ],
            }
        ),
    )
    _write(
        backend / "alembic/versions/0002_delayed.py",
        """
from alembic import op
import sqlalchemy as sa
def upgrade():
    op.create_table(
        "delayed_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
    )
""",
    )

    report = build_inventory(backend)

    assert report["format"] == FORMAT
    assert report["summary"] == {
        "orm_tables": 2,
        "schema_tables": 4,
        "tables": 4,
        "key_classifications": {"generated_surrogate": 2, "unresolved": 2},
        "string_uuid_reference_candidates": 1,
        "generation_sites": {"uuid4": 1, "uuid5": 1},
        "unresolved": 2,
    }
    assert report["string_uuid_references"] == [
        {
            "table": "widget_uses",
            "column": "widget_id",
            "target": "widgets.id",
            "current_storage": "inferred",
            "candidate": "convert relationship to native UUID",
        }
    ]
    assert {item["table"] for item in report["unresolved"]} == {
        "delayed_records",
        "migration_state",
    }
    assert {site["candidate"] for site in report["generation_sites"]} == {
        "script_boundary_requires_review",
        "uuid4_boundary_requires_review",
    }
    assert json.loads(json.dumps(report))["summary"] == report["summary"]
    text = render_text(report)
    assert "widget_uses.widget_id -> widgets.id" in text
    assert "migration_state: schema table has no ORM owner" in text

    # A manifest that silently loses a model or changes its key must not be
    # treated as a complete inventory just because the remaining types match.
    manifest_path = backend / "alembic/baseline/v01_baseline_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["tables"] = [row for row in manifest["tables"] if row["name"] != "widget_uses"]
    manifest["columns"] = [row for row in manifest["columns"] if row["table_name"] != "widget_uses"]
    manifest["constraints"] = [row for row in manifest["constraints"] if row["table_name"] != "widget_uses"]
    manifest["constraints"][0]["definition"] = "PRIMARY KEY (different_key)"
    _write(manifest_path, json.dumps(manifest))
    unresolved = {(row["kind"], row["table"]) for row in build_inventory(backend)["unresolved"]}
    assert ("missing_schema_table", "widget_uses") in unresolved
    assert ("primary_key_shape_mismatch", "widgets") in unresolved
