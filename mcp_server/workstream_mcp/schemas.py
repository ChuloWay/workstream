from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

EMPTY_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
PROFILE_UPDATE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "display_name": {"type": ["string", "null"], "maxLength": 200},
        "contact_email": {"type": ["string", "null"], "maxLength": 320},
    },
    "minProperties": 1,
    "additionalProperties": False,
}
AUTHORIZATION_CONTEXT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "pattern": r"^[^\u0000]*$",
        }
    },
    "required": ["project_id"],
    "additionalProperties": False,
}

_UUID_INPUT = {"type": "string", "format": "uuid", "minLength": 36, "maxLength": 36}
_REASON_INPUT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 500,
    "pattern": r"^[^\u0000]*$",
}
_IDEMPOTENCY_KEY_INPUT = {
    "type": "string",
    "format": "uuid",
    "minLength": 36,
    "maxLength": 36,
}
_ACTOR_INPUT = {
    "type": "object",
    "properties": {"actor_profile_id": _UUID_INPUT},
    "required": ["actor_profile_id"],
    "additionalProperties": False,
}
_GRANT_PROPERTIES = {
    "scope_type": {"type": "string", "enum": ["system", "project"]},
    "scope_project_id": _UUID_INPUT,
    "status": {"type": "string", "enum": ["active", "revoked", "all"]},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "cursor": {"type": "string", "maxLength": 512},
}
_GRANT_SCOPE_CONSTRAINTS = [
    {
        "if": {"properties": {"scope_type": {"const": "project"}}, "required": ["scope_type"]},
        "then": {"required": ["scope_project_id"]},
    },
    {
        "if": {"properties": {"scope_type": {"const": "system"}}, "required": ["scope_type"]},
        "then": {"not": {"required": ["scope_project_id"]}},
    },
]
ACCESS_READ_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "permissions_list": EMPTY_INPUT_SCHEMA,
    "admin_roles_list": EMPTY_INPUT_SCHEMA,
    "admin_grants_list": {
        "type": "object",
        "properties": _GRANT_PROPERTIES,
        "required": ["scope_type"],
        "allOf": _GRANT_SCOPE_CONSTRAINTS,
        "additionalProperties": False,
    },
    "actor_admin_grants_list": {
        "type": "object",
        "properties": {"actor_profile_id": _UUID_INPUT, **_GRANT_PROPERTIES},
        "required": ["actor_profile_id", "scope_type"],
        "allOf": _GRANT_SCOPE_CONSTRAINTS,
        "additionalProperties": False,
    },
    "actor_get": _ACTOR_INPUT,
    "actor_identity_link_get": _ACTOR_INPUT,
}

ADMIN_GRANT_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "admin_grants_issue": {
        "type": "object",
        "properties": {
            "body": {
                "type": "object",
                "properties": {
                    "target_actor_profile_id": _UUID_INPUT,
                    "role": {
                        "type": "string",
                        "enum": [
                            "access_administrator",
                            "operator",
                            "project_manager",
                            "finance_authority",
                            "audit_authority",
                        ],
                    },
                    "scope_type": {"type": "string", "enum": ["system", "project"]},
                    "scope_project_id": {"anyOf": [_UUID_INPUT, {"type": "null"}]},
                    "reason": _REASON_INPUT,
                },
                "required": ["target_actor_profile_id", "role", "scope_type", "reason"],
                "allOf": [
                    {
                        "if": {"properties": {"scope_type": {"const": "project"}}},
                        "then": {
                            "required": ["scope_project_id"],
                            "properties": {"scope_project_id": _UUID_INPUT},
                        },
                    },
                    {
                        "if": {"properties": {"scope_type": {"const": "system"}}},
                        "then": {
                            "properties": {
                                "scope_project_id": {"type": "null"},
                            }
                        },
                    },
                    {
                        "if": {
                            "properties": {"role": {"enum": ["access_administrator", "operator"]}}
                        },
                        "then": {"properties": {"scope_type": {"const": "system"}}},
                    },
                ],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["body", "idempotency_key"],
        "additionalProperties": False,
    },
    "admin_grants_revoke": {
        "type": "object",
        "properties": {
            "grant_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {"reason": _REASON_INPUT},
                "required": ["reason"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["grant_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
}

_LIFECYCLE_BODY = {
    "type": "object",
    "properties": {"reason": _REASON_INPUT},
    "required": ["reason"],
    "additionalProperties": False,
}


def _lifecycle_input(resource_key: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            resource_key: _UUID_INPUT,
            "body": _LIFECYCLE_BODY,
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": [resource_key, "body", "idempotency_key"],
        "additionalProperties": False,
    }


ACTOR_LIFECYCLE_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "actor_suspend": _lifecycle_input("actor_profile_id"),
    "actor_reactivate": _lifecycle_input("actor_profile_id"),
    "actor_deactivate": _lifecycle_input("actor_profile_id"),
    "identity_link_revoke": _lifecycle_input("identity_link_id"),
    "identity_link_reactivate": _lifecycle_input("identity_link_id"),
}

PROJECT_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "projects_create": {
        "type": "object",
        "properties": {
            "body": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "maxLength": 200,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "slug": {
                        "type": "string",
                        "maxLength": 120,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "description": {
                        "type": ["string", "null"],
                        "pattern": r"^[^\u0000]*$",
                    },
                },
                "required": ["name", "slug"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["body", "idempotency_key"],
        "additionalProperties": False,
    },
    "projects_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT},
        "required": ["project_id"],
        "additionalProperties": False,
    },
}

_REFERENCE_TOKEN_INPUT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 120,
    "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$",
    "not": {"pattern": r"://"},
}
_QUALIFICATION_AVAILABILITY_INPUT = {
    "type": "object",
    "properties": {
        "availability": {"type": "string", "enum": ["available", "unavailable"]},
        "reference_ids": {
            "type": "array",
            "items": _REFERENCE_TOKEN_INPUT,
            "maxItems": 20,
        },
        "unavailable_reason": {
            "type": ["string", "null"],
            "enum": ["not_collected", "source_unavailable", "no_record", None],
        },
    },
    "required": ["availability", "reference_ids", "unavailable_reason"],
    "allOf": [
        {
            "if": {"properties": {"availability": {"const": "available"}}},
            "then": {
                "properties": {
                    "reference_ids": {"minItems": 1},
                    "unavailable_reason": {"type": "null"},
                }
            },
        },
        {
            "if": {"properties": {"availability": {"const": "unavailable"}}},
            "then": {
                "properties": {
                    "reference_ids": {"maxItems": 0},
                    "unavailable_reason": {
                        "type": "string",
                        "enum": ["not_collected", "source_unavailable", "no_record"],
                    },
                }
            },
        },
    ],
    "additionalProperties": False,
}
_PROJECT_ROLE_QUALIFICATION_INPUT = {
    "type": "object",
    "properties": {
        "skills_snapshot": _QUALIFICATION_AVAILABILITY_INPUT,
        "reputation_snapshot": _QUALIFICATION_AVAILABILITY_INPUT,
        "prior_project_work_refs": {
            "type": "array",
            "items": _UUID_INPUT,
            "maxItems": 20,
        },
        "external_expertise_refs": {
            "type": "array",
            "items": _REFERENCE_TOKEN_INPUT,
            "maxItems": 20,
        },
    },
    "required": [
        "skills_snapshot",
        "reputation_snapshot",
        "prior_project_work_refs",
        "external_expertise_refs",
    ],
    "additionalProperties": False,
}
_PROJECT_ROLE_PAGE_PROPERTIES = {
    "project_id": _UUID_INPUT,
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "cursor": {"type": "string", "maxLength": 512},
}
PROJECT_GRANT_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "contributor_candidates_list": {
        "type": "object",
        "properties": _PROJECT_ROLE_PAGE_PROPERTIES,
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_grants_issue": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "target_actor_profile_id": _UUID_INPUT,
                    "role": {"type": "string", "enum": ["submitter", "reviewer"]},
                    "qualification": _PROJECT_ROLE_QUALIFICATION_INPUT,
                    "reason": _REASON_INPUT,
                },
                "required": [
                    "target_actor_profile_id",
                    "role",
                    "qualification",
                    "reason",
                ],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
    "project_grants_list": {
        "type": "object",
        "properties": {
            **_PROJECT_ROLE_PAGE_PROPERTIES,
            "status": {"type": "string", "enum": ["active", "revoked"]},
            "role": {"type": "string", "enum": ["submitter", "reviewer"]},
        },
        "required": ["project_id"],
        "additionalProperties": False,
    },
    "project_grants_get": {
        "type": "object",
        "properties": {"project_id": _UUID_INPUT, "grant_id": _UUID_INPUT},
        "required": ["project_id", "grant_id"],
        "additionalProperties": False,
    },
    "project_grants_revoke": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "grant_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {"reason": _REASON_INPUT},
                "required": ["reason"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "grant_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
}

_GUIDE_TASK_EXAMPLE_INPUT = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "minLength": 1,
            "maxLength": 65_536,
            "pattern": r"^[^\u0000]*$",
        },
        "title": {
            "type": ["string", "null"],
            "maxLength": 500,
            "pattern": r"^[^\u0000]*$",
        },
        "labels": {
            "type": "array",
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 100,
                "pattern": r"^[^\u0000]*$",
            },
            "maxItems": 20,
        },
    },
    "required": ["content"],
    "additionalProperties": False,
}
_GUIDE_DOCUMENT_INPUT = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "minLength": 1, "maxLength": 500},
        "media_type": {
            "type": "string",
            "enum": [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "text/markdown",
            ],
        },
    },
    "required": ["label", "media_type"],
    "additionalProperties": False,
}
GUIDE_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "guides_create": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "version": {
                        "type": "string",
                        "maxLength": 50,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "change_summary": {
                        "type": ["string", "null"],
                        "maxLength": 1000,
                        "pattern": r"^[^\u0000]*$",
                    },
                    "task_examples": {
                        "type": "array",
                        "items": _GUIDE_TASK_EXAMPLE_INPUT,
                        "minItems": 1,
                        "maxItems": 100,
                    },
                    "documents": {
                        "type": "array",
                        "items": _GUIDE_DOCUMENT_INPUT,
                        "minItems": 1,
                        "maxItems": 100,
                    },
                },
                "required": ["version", "task_examples", "documents"],
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
    "guides_update": {
        "type": "object",
        "properties": {
            "project_id": _UUID_INPUT,
            "guide_id": _UUID_INPUT,
            "body": {
                "type": "object",
                "properties": {
                    "change_summary": {
                        "type": ["string", "null"],
                        "maxLength": 1000,
                        "pattern": r"^[^\u0000]*$",
                    }
                },
                "additionalProperties": False,
            },
            "idempotency_key": _IDEMPOTENCY_KEY_INPUT,
        },
        "required": ["project_id", "guide_id", "body", "idempotency_key"],
        "additionalProperties": False,
    },
}


class ContractError(RuntimeError):
    """The reviewed packaged contract is absent or invalid."""


_OUTPUT_FORMAT_CHECKER = FormatChecker()


def _resolve_schema_refs(value: Any, schemas: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_resolve_schema_refs(item, schemas) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    prefix = "#/components/schemas/"
    if isinstance(reference, str) and reference.startswith(prefix):
        target = schemas.get(reference.removeprefix(prefix))
        if not isinstance(target, dict):
            raise ContractError("contract contains an unresolved schema reference")
        return _resolve_schema_refs(target, schemas)
    return {key: _resolve_schema_refs(item, schemas) for key, item in value.items()}


def _selected_schema(document: dict[str, Any]) -> dict[str, Any]:
    for key in ("output_schema", "outputSchema", "schema"):
        candidate = document.get(key)
        if isinstance(candidate, dict):
            return candidate
    if document.get("type") == "object":
        return document
    operation = document.get("operation")
    components = document.get("components")
    if isinstance(operation, dict) and isinstance(components, dict):
        schemas = components.get("schemas")
        responses = operation.get("responses")
        if isinstance(schemas, dict) and isinstance(responses, dict):
            success = responses.get("200") or responses.get("201")
            content = success.get("content") if isinstance(success, dict) else None
            media = content.get("application/json") if isinstance(content, dict) else None
            selected = media.get("schema") if isinstance(media, dict) else None
            if isinstance(selected, dict):
                return cast(dict[str, Any], _resolve_schema_refs(selected, schemas))
    raise ContractError("contract does not contain an output schema")


@lru_cache(maxsize=32)
def _contract_output_schema(name: str) -> dict[str, Any]:
    filename = f"{name}.json"
    resource = files("workstream_mcp").joinpath(f"contracts/{filename}")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError:
        source_contract = Path(__file__).resolve().parents[1] / "contracts" / filename
        try:
            document = json.loads(source_contract.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ContractError(f"packaged {name} contract is missing or invalid") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"packaged {name} contract is missing or invalid") from exc
    if not isinstance(document, dict):
        raise ContractError(f"{name} contract must be a JSON object")
    schema = _selected_schema(document)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ContractError(f"{name} output schema is invalid") from exc
    return schema


def profile_output_schema() -> dict[str, Any]:
    return _contract_output_schema("profile_get")


def profile_update_output_schema() -> dict[str, Any]:
    return _contract_output_schema("profile_update")


def authorization_context_output_schema() -> dict[str, Any]:
    return _contract_output_schema("authorization_context_get")


@lru_cache(maxsize=32)
def _contract_output_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        _contract_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )


def profile_output_validator() -> Draft202012Validator:
    return _contract_output_validator("profile_get")


def profile_update_output_validator() -> Draft202012Validator:
    return _contract_output_validator("profile_update")


def authorization_context_output_validator() -> Draft202012Validator:
    return _contract_output_validator("authorization_context_get")


def access_read_output_schema(name: str) -> dict[str, Any]:
    """Load one of the six reviewed administrative read projections."""
    if name not in ACCESS_READ_INPUT_SCHEMAS:
        raise ContractError("unknown administrative read contract")
    return _contract_output_schema(name)


def access_read_output_validator(name: str) -> Draft202012Validator:
    """Validate a bounded administrative projection, including formats."""
    access_read_output_schema(name)
    return _contract_output_validator(name)


def admin_grant_output_schema(name: str) -> dict[str, Any]:
    """Load one of the reviewed administrative mutation receipts."""
    if name not in ADMIN_GRANT_INPUT_SCHEMAS:
        raise ContractError("unknown administrative grant contract")
    return _contract_output_schema(name)


def admin_grant_output_validator(name: str) -> Draft202012Validator:
    """Validate one administrative mutation receipt, including formats."""
    admin_grant_output_schema(name)
    return _contract_output_validator(name)


def actor_lifecycle_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed actor or identity-link lifecycle receipt."""
    if name not in ACTOR_LIFECYCLE_INPUT_SCHEMAS:
        raise ContractError("unknown actor lifecycle contract")
    return _contract_output_schema(name)


def actor_lifecycle_output_validator(name: str) -> Draft202012Validator:
    """Validate one actor or identity-link lifecycle receipt."""
    actor_lifecycle_output_schema(name)
    return _contract_output_validator(name)


def project_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed project-shell response contract."""
    if name not in PROJECT_INPUT_SCHEMAS:
        raise ContractError("unknown project contract")
    schema = _contract_output_schema(name)
    if name == "projects_get" and "type" not in schema:
        # MCP requires object-rooted tool outputs; retain FastAPI's exact union.
        return {"type": "object", **schema}
    return schema


def project_output_validator(name: str) -> Draft202012Validator:
    """Validate one project-shell response projection."""
    return Draft202012Validator(
        project_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )


def project_grant_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed project-participation response contract."""
    if name not in PROJECT_GRANT_INPUT_SCHEMAS:
        raise ContractError("unknown project participation contract")
    return _contract_output_schema(name)


def project_grant_output_validator(name: str) -> Draft202012Validator:
    """Validate one project-participation response projection."""
    return _contract_output_validator(name)


def guide_output_schema(name: str) -> dict[str, Any]:
    """Load one reviewed guide-mutation response contract."""
    if name not in GUIDE_INPUT_SCHEMAS:
        raise ContractError("unknown guide contract")
    return _contract_output_schema(name)


def guide_output_validator(name: str) -> Draft202012Validator:
    """Validate one guide-mutation response projection."""
    return _contract_output_validator(name)
