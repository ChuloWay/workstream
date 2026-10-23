"""Fixed draft-policy mutations; Workstream owns semantics and replay."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    FormatChecker,
    ValidationError,
)
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from workstream_mcp.errors import adapter_failure
from workstream_mcp.http_gateway import WorkstreamGateway
from workstream_mcp.schemas import POLICY_INPUT_SCHEMAS, policy_output_schema

TOOL_NAMES = (
    "workstream_review_policy_put",
    "workstream_revision_policy_put",
)
_CONTRACT_NAMES = {name: name.removeprefix("workstream_") for name in TOOL_NAMES}
_INPUT_VALIDATORS = {
    name: Draft202012Validator(schema, format_checker=FormatChecker())
    for name, schema in POLICY_INPUT_SCHEMAS.items()
}


def _valid_strict_fields(name: str, arguments: dict[str, Any]) -> bool:
    """Match backend strict integer fields that JSON Schema treats more broadly."""
    body = arguments.get("body")
    if name != "revision_policy_put" or not isinstance(body, dict):
        return True
    return type(body.get("max_revision_rounds")) is int


def definitions() -> list[Tool]:
    """Publish the two closed draft-policy mutation contracts."""
    return [
        Tool(
            name="workstream_review_policy_put",
            description=(
                "Append and select review rules for one draft guide using an exact "
                "caller-owned policy precondition."
            ),
            input_schema=POLICY_INPUT_SCHEMAS["review_policy_put"],
            output_schema=policy_output_schema("review_policy_put"),
            annotations=ToolAnnotations(
                title="Configure draft review policy",
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        ),
        Tool(
            name="workstream_revision_policy_put",
            description=(
                "Append and select revision-loop rules for one draft guide using an exact "
                "caller-owned policy precondition."
            ),
            input_schema=POLICY_INPUT_SCHEMAS["revision_policy_put"],
            output_schema=policy_output_schema("revision_policy_put"),
            annotations=ToolAnnotations(
                title="Configure draft revision policy",
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        ),
    ]


async def invoke(
    gateway: WorkstreamGateway,
    tool_name: str,
    bearer: str,
    correlation_id: str | None,
    arguments: dict[str, Any],
) -> CallToolResult:
    """Validate one policy mutation before fixed-route dispatch."""
    contract_name = _CONTRACT_NAMES.get(tool_name)
    if contract_name is None:
        return adapter_failure("unknown_tool", status=404)
    try:
        _INPUT_VALIDATORS[contract_name].validate(arguments)
    except ValidationError:
        return adapter_failure("invalid_tool_input", status=400)
    if not _valid_strict_fields(contract_name, arguments):
        return adapter_failure("invalid_tool_input", status=400)

    outcome = await gateway.policy_mutation(
        contract_name, bearer, arguments, correlation_id
    )
    if outcome.failure is not None:
        return outcome.failure.result()
    data = outcome.data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
        structured_content=data,
    )
