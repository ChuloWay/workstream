"""Statically inventory record identifiers without importing application code."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any, Iterable

if __package__:
    from scripts.schema_baseline_sql import split_sql_statements
else:
    from schema_baseline_sql import split_sql_statements

FORMAT = "workstream-identifier-inventory-1"
SEMANTIC_KEYS = {
    "actor_profile_migration_state": ("seeded schema-state singleton, not a record sequence", ("id",)),
    "api_rate_control_counters": ("rate-limit scope and digest", ("control_scope", "key_digest")),
    "artifact_admission_scopes": ("artifact quota scope", ("scope_type", "scope_id")),
    "artifact_put_attempt_charges": ("attempt-to-charge association", ("attempt_id", "charge_id")),
    "artifact_storage_namespaces": ("storage namespace name", ("id",)),
    "authority_control": ("singleton control row", ("id",)),
    "guide_source_extraction_retry_budgets": ("binding-owned shared primary key", ("binding_id",)),
    "iso_4217_currency_codes": ("ISO currency code", ("code",)),
    "legacy_actor_identities": ("external legacy actor key", ("actor_id",)),
    "outbox_delivery_attempts": ("event delivery generation", ("event_id", "claim_generation")),
    "project_compensation_units": (
        "project instrument and unit code",
        ("project_id", "instrument_type", "unit_code"),
    ),
}
_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:public\.)?\"?([A-Za-z_]\w*)\"?\s*\((.*)\)\s*$", re.I | re.S
)
_IDENTIFIER = re.compile(r"^(?:id|.*_id)$")


def _name(node: ast.AST) -> str | None:
    return (
        node.id
        if isinstance(node, ast.Name)
        else node.attr
        if isinstance(node, ast.Attribute)
        else None
    )


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _kind(source: str, annotation: str = "") -> str:
    compact = source.replace(" ", "")
    if re.search(r"(?:^|\.)(?:Uuid|UUID)(?:\(|$)", compact, re.I) or source.lower() == "uuid":
        return "native_uuid"
    if re.search(
        r"(?:^|\.)(?:String|VARCHAR|CHAR)(?:\(|$)", compact, re.I
    ) or source.lower().startswith(("character varying", "varchar", "text")):
        return "string"
    if re.search(
        r"(?:^|\.)(?:SmallInteger|Integer|BigInteger)(?:\(|$)", compact
    ) or source.lower().startswith(("smallint", "integer", "bigint", "serial")):
        return "integer"
    if source == "inferred":
        return (
            "native_uuid"
            if "UUID" in annotation
            else "string"
            if "str" in annotation
            else "integer"
            if "int" in annotation
            else "other"
        )
    return "other"


def _columns(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {column["name"]: column for column in table["columns"]}


def _mapped_column(statement: ast.AnnAssign) -> dict[str, Any] | None:
    if (
        not isinstance(statement.target, ast.Name)
        or not isinstance(statement.value, ast.Call)
        or _name(statement.value.func) != "mapped_column"
    ):
        return None
    call = statement.value
    type_node = next(
        (
            item
            for item in call.args
            if _string(item) is None
            and not (isinstance(item, ast.Call) and _name(item.func) == "ForeignKey")
        ),
        None,
    )
    annotation = ast.unparse(statement.annotation)
    storage_type = ast.unparse(type_node) if type_node else "inferred"
    return {
        "name": (_string(call.args[0]) if call.args else None) or statement.target.id,
        "annotation": annotation,
        "storage_type": storage_type,
        "storage_kind": _kind(storage_type, annotation),
        "primary_key": any(
            keyword.arg == "primary_key"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in call.keywords
        ),
        "foreign_keys": sorted(
            {
                target
                for child in ast.walk(call)
                if isinstance(child, ast.Call) and _name(child.func) == "ForeignKey" and child.args
                if (target := _string(child.args[0]))
            }
        ),
        "line": statement.lineno,
    }


def parse_orm_models(app_root: Path, report_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Map all declarative columns and multiline column/table foreign keys."""
    report_root = report_root or app_root.parent
    tables: dict[str, dict[str, Any]] = {}
    for path in sorted(app_root.rglob("models.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in (item for item in tree.body if isinstance(item, ast.ClassDef)):
            table_name = None
            for statement in node.body:
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    targets = (
                        statement.targets
                        if isinstance(statement, ast.Assign)
                        else [statement.target]
                    )
                    if any(
                        isinstance(target, ast.Name) and target.id == "__tablename__"
                        for target in targets
                    ):
                        table_name = _string(statement.value)
            if not table_name:
                continue
            columns = [
                column
                for statement in node.body
                if isinstance(statement, ast.AnnAssign) and (column := _mapped_column(statement))
            ]
            primary_key = [column["name"] for column in columns if column["primary_key"]]
            by_column = {column["name"]: column for column in columns}
            for statement in node.body:
                if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = (
                    statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                )
                if not any(
                    isinstance(target, ast.Name) and target.id == "__table_args__"
                    for target in targets
                ):
                    continue
                for call in (
                    item for item in ast.walk(statement.value) if isinstance(item, ast.Call)
                ):
                    if _name(call.func) == "PrimaryKeyConstraint":
                        primary_key.extend(value for arg in call.args if (value := _string(arg)))
                    if _name(call.func) == "ForeignKeyConstraint" and len(call.args) > 1:
                        local = [_string(item) for item in getattr(call.args[0], "elts", ())]
                        remote = [_string(item) for item in getattr(call.args[1], "elts", ())]
                        for source, target in zip(local, remote, strict=False):
                            if source and target:
                                by_column[source]["foreign_keys"].append(target)
            for column in columns:
                column["foreign_keys"] = sorted(set(column["foreign_keys"]))
            tables[table_name] = {
                "name": table_name,
                "orm_path": path.relative_to(report_root).as_posix(),
                "orm_class": node.name,
                "columns": columns,
                "primary_key": list(dict.fromkeys(primary_key)),
            }
    # SQLAlchemy infers mapped_column(ForeignKey(...)) SQL types from targets.
    for _ in range(len(tables)):
        changed = False
        for table in tables.values():
            for column in table["columns"]:
                kinds = {
                    target_column["storage_kind"]
                    for target in column["foreign_keys"]
                    for owner in [tables.get(target.rpartition(".")[0])]
                    if column["storage_type"] == "inferred" and owner
                    for target_column in [_columns(owner).get(target.rpartition(".")[2])]
                    if target_column and target_column["storage_kind"] != "other"
                    and (target_column["storage_type"] != "inferred"
                         or target_column.get("storage_inferred_from_foreign_key"))
                }
                if len(kinds) == 1 and column["storage_kind"] != next(iter(kinds)):
                    column["storage_kind"] = next(iter(kinds))
                    column["storage_inferred_from_foreign_key"] = True
                    changed = True
        if not changed:
            break
    return tables


def _manifest_schema(backend_root: Path) -> dict[str, dict[str, Any]]:
    """Read the deterministic output of schema_baseline_manifest.py."""
    path = backend_root / "alembic/baseline/v01_baseline_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    tables = {
        item["name"]: {
            "name": item["name"],
            "columns": [],
            "primary_key": [],
            "schema_sources": [path.relative_to(backend_root).as_posix()],
        }
        for item in manifest["tables"]
    }
    for item in manifest["columns"]:
        tables[item["table_name"]]["columns"].append(
            {
                "name": item["name"],
                "storage_type": item["data_type"],
                "storage_kind": _kind(item["data_type"]),
                "foreign_keys": [],
            }
        )
    for item in manifest["constraints"]:
        match = (
            re.search(r"PRIMARY KEY \(([^)]+)\)", item["definition"], re.I)
            if item["kind"] == "p"
            else None
        )
        if match and item["table_name"] in tables:
            tables[item["table_name"]]["primary_key"] = [
                value.strip().strip('"') for value in match.group(1).split(",")
            ]
    return tables


def _sql_created_table(source: str, path: str) -> dict[str, dict[str, Any]]:
    """Use the shared SQL splitter to extract only migration-created table keys."""
    result = {}
    for statement in split_sql_statements(source):
        if not (match := _CREATE.search(statement)):
            continue
        name, body = match.groups()
        primary_key = []
        if key := re.search(r"PRIMARY KEY\s*\(([^)]+)\)", body, re.I):
            primary_key.extend(value.strip().strip('"') for value in key.group(1).split(","))
        inline = re.findall(r"(?m)^\s*\"?([A-Za-z_]\w*)\"?\s+[^,\n]+\bPRIMARY KEY\b", body, re.I)
        primary_key.extend(value for value in inline if value.upper() != "CONSTRAINT")
        columns = []
        for column_name in dict.fromkeys(primary_key):
            type_match = re.search(
                rf"(?m)^\s*\"?{re.escape(column_name)}\"?\s+([A-Za-z_]+(?:\(\d+\))?)", body
            )
            storage_type = type_match.group(1) if type_match else "unresolved"
            columns.append(
                {
                    "name": column_name,
                    "storage_type": storage_type,
                    "storage_kind": _kind(storage_type),
                    "foreign_keys": [],
                }
            )
        result[name] = {
            "name": name,
            "columns": columns,
            "primary_key": list(dict.fromkeys(primary_key)),
            "schema_sources": [path],
        }
    return result


def parse_schema(backend_root: Path) -> dict[str, dict[str, Any]]:
    tables = _manifest_schema(backend_root)
    for path in sorted((backend_root / "alembic/versions").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(backend_root).as_posix()
        for item in ast.walk(tree):
            if (
                isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and re.search(r"\bCREATE\s+TABLE\b", item.value, re.I)
            ):
                tables.update(_sql_created_table(item.value, relative))
            if (
                not isinstance(item, ast.Call)
                or _name(item.func) != "create_table"
                or not item.args
                or not (table_name := _string(item.args[0]))
            ):
                continue
            columns = []
            for argument in item.args[1:]:
                if (
                    not isinstance(argument, ast.Call)
                    or _name(argument.func) != "Column"
                    or not argument.args
                    or not (column_name := _string(argument.args[0]))
                ):
                    continue
                if any(
                    keyword.arg == "primary_key"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in argument.keywords
                ):
                    storage_type = (
                        ast.unparse(argument.args[1]) if len(argument.args) > 1 else "unresolved"
                    )
                    columns.append(
                        {
                            "name": column_name,
                            "storage_type": storage_type,
                            "storage_kind": _kind(storage_type),
                            "foreign_keys": [],
                        }
                    )
            tables[table_name] = {
                "name": table_name,
                "columns": columns,
                "primary_key": [column["name"] for column in columns],
                "schema_sources": [relative],
            }
    return tables


def scan_generation_sites(roots: Iterable[Path], report_root: Path) -> list[dict[str, Any]]:
    sites = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if path.name == Path(__file__).name:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            direct, modules = {}, set()
            for item in ast.walk(tree):
                if isinstance(item, ast.ImportFrom) and item.module == "uuid":
                    direct.update(
                        {
                            alias.asname or alias.name: alias.name
                            for alias in item.names
                            if alias.name in {"uuid4", "uuid5"}
                        }
                    )
                if isinstance(item, ast.Import):
                    modules.update(
                        alias.asname or alias.name for alias in item.names if alias.name == "uuid"
                    )
            for call in (item for item in ast.walk(tree) if isinstance(item, ast.Call)):
                generator = direct.get(call.func.id) if isinstance(call.func, ast.Name) else None
                if (
                    isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id in modules
                    and call.func.attr in {"uuid4", "uuid5"}
                ):
                    generator = call.func.attr
                if generator:
                    relative = path.relative_to(report_root).as_posix()
                    candidate = (
                        "script_boundary_requires_review"
                        if relative.startswith("scripts/")
                        else "deterministic_replay_requires_owner_review"
                        if generator == "uuid5"
                        else "uuid4_boundary_requires_review"
                    )
                    sites.append(
                        {
                            "generator": generator,
                            "path": relative,
                            "line": call.lineno,
                            "column": call.col_offset + 1,
                            "candidate": candidate,
                        }
                    )
    return sorted(sites, key=lambda item: (item["path"], item["line"], item["column"]))


def _key(table: dict[str, Any], orm_present: bool) -> dict[str, str]:
    if exception := SEMANTIC_KEYS.get(table["name"]):
        reason, expected = exception
        return (
            {"classification": "natural_or_composite", "reason": reason}
            if tuple(table["primary_key"]) == expected
            else {"classification": "unresolved", "reason": "semantic key shape changed"}
        )
    if not orm_present:
        return {"classification": "unresolved", "reason": "schema table has no ORM owner"}
    if len(table["primary_key"]) == 1 and table["primary_key"][0] in {
        "id",
        "event_id",
        "operation_id",
    }:
        return {
            "classification": "generated_surrogate",
            "reason": "conventional Workstream record key",
        }
    return {
        "classification": "unresolved",
        "reason": "non-conventional key requires owner classification",
    }


def build_inventory(backend_root: Path) -> dict[str, Any]:
    backend_root = backend_root.resolve()
    orm = parse_orm_models(backend_root / "app", backend_root)
    schema = parse_schema(backend_root)
    tables, unresolved = [], []
    for name in sorted(set(orm) | set(schema)):
        owner, ddl = orm.get(name), schema.get(name)
        structural = owner or ddl
        assert structural
        key = _key(structural, owner is not None)
        key_columns = _columns(structural)
        entry = {
            "name": name,
            "orm_path": owner["orm_path"] if owner else None,
            "orm_class": owner["orm_class"] if owner else None,
            "schema_sources": ddl["schema_sources"] if ddl else [],
            "primary_key": structural["primary_key"],
            "key_storage": [
                key_columns.get(item, {}).get("storage_kind", "unresolved")
                for item in structural["primary_key"]
            ],
            "key": key,
            "columns": owner["columns"] if owner else ddl["columns"],
            "schema_key_columns": ddl["columns"] if ddl else [],
            "candidates": [],
        }
        if key["classification"] == "generated_surrogate":
            if "string" in entry["key_storage"]:
                entry["candidates"].append("convert surrogate key to native UUID")
            entry["candidates"].append("switch generation to shared UUIDv7 helper")
        if key["classification"] == "unresolved":
            unresolved.append({"kind": "table_key", "table": name, "reason": key["reason"]})
        if owner and not ddl:
            unresolved.append({
                "kind": "missing_schema_table", "table": name,
                "reason": "ORM table is absent from the schema inventory",
            })
        if owner and ddl and owner["primary_key"] != ddl["primary_key"]:
            unresolved.append({
                "kind": "primary_key_shape_mismatch", "table": name,
                "reason": "ORM and schema primary keys differ",
            })
        if owner and ddl and owner["primary_key"] == ddl["primary_key"]:
            for column_name in owner["primary_key"]:
                left, right = _columns(owner).get(column_name), _columns(ddl).get(column_name)
                if left and right and left["storage_kind"] != right["storage_kind"]:
                    unresolved.append(
                        {
                            "kind": "primary_key_storage_mismatch",
                            "table": name,
                            "column": column_name,
                            "orm": left["storage_type"],
                            "schema": right["storage_type"],
                            "reason": "ORM and schema manifest do not yet agree",
                        }
                    )
                    entry["candidates"].append("reconcile primary key in fresh schema baseline")
        tables.append(entry)

    table_names = {table["name"] for table in tables}
    references = [
        {
            "table": table["name"],
            "column": column["name"],
            "target": target,
            "current_storage": column["storage_type"],
            "candidate": "convert relationship to native UUID",
        }
        for table in tables
        for column in table["columns"]
        if column["storage_kind"] == "string" and _IDENTIFIER.match(column["name"])
        for target in column.get("foreign_keys", [])
        if target.rpartition(".")[0] in table_names and _IDENTIFIER.match(target.rpartition(".")[2])
        if target.rpartition(".")[0] not in SEMANTIC_KEYS
    ]
    generation = scan_generation_sites(
        (backend_root / "app", backend_root / "scripts"), backend_root
    )
    classifications = Counter(table["key"]["classification"] for table in tables)
    generators = Counter(site["generator"] for site in generation)
    return {
        "format": FORMAT,
        "scope": {
            "backend_root": backend_root.as_posix(),
            "method": "static AST plus checked-in schema manifest",
        },
        "summary": {
            "orm_tables": len(orm),
            "schema_tables": len(schema),
            "tables": len(tables),
            "key_classifications": dict(sorted(classifications.items())),
            "string_uuid_reference_candidates": len(references),
            "generation_sites": dict(sorted(generators.items())),
            "unresolved": len(unresolved),
        },
        "tables": tables,
        "string_uuid_references": sorted(
            references, key=lambda item: (item["table"], item["column"], item["target"])
        ),
        "generation_sites": generation,
        "unresolved": unresolved,
    }


def render_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"Identifier inventory {report['format']}",
        f"tables: orm={summary['orm_tables']} schema={summary['schema_tables']} union={summary['tables']} unresolved={summary['unresolved']}",
        "TABLE | PRIMARY KEY | KEY CLASS | STORAGE | CANDIDATES",
    ]
    lines.extend(
        " | ".join(
            (
                table["name"],
                ",".join(table["primary_key"]) or "<missing>",
                table["key"]["classification"],
                ",".join(table["key_storage"]) or "<missing>",
                "; ".join(table["candidates"]) or "-",
            )
        )
        for table in report["tables"]
    )
    lines.extend(
        [
            "STRING UUID RELATIONSHIP CANDIDATES",
            *(
                f"{item['table']}.{item['column']} -> {item['target']}"
                for item in report["string_uuid_references"]
            ),
            "GENERATION SITES",
            *(
                f"{item['generator']} {item['path']}:{item['line']} {item['candidate']}"
                for item in report["generation_sites"]
            ),
            "UNRESOLVED",
            *(f"{item['kind']} {item['table']}: {item['reason']}" for item in report["unresolved"]),
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_inventory(args.backend_root)
    payload = (
        json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.format == "json"
        else render_text(report)
    )
    args.output.write_text(payload, encoding="utf-8") if args.output else print(payload, end="")


if __name__ == "__main__":
    main()
