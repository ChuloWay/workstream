"""Fixed guide metadata mutations; Workstream owns authority and replay."""

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
from workstream_mcp.schemas import GUIDE_INPUT_SCHEMAS, guide_output_schema

TOOL_NAMES = ("workstream_guides_create", "workstream_guides_update")
_CONTRACT_NAMES = {name: name.removeprefix("workstream_") for name in TOOL_NAMES}
_INPUT_VALIDATORS = {
    name: Draft202012Validator(schema, format_checker=FormatChecker())
    for name, schema in GUIDE_INPUT_SCHEMAS.items()
}
_MAXIMUM_TASK_EXAMPLE_BYTES = 128 * 1024


def definitions() -> list[Tool]:
    """Publish the two closed guide-metadata mutation contracts."""
    return [
        Tool(
            name="workstream_guides_create",
            description=(
                "Declare one draft guide, its illustrative tasks and document metadata. "
                "Document bytes are uploaded outside MCP."
            ),
            input_schema=GUIDE_INPUT_SCHEMAS["guides_create"],
            output_schema=guide_output_schema("guides_create"),
            annotations=ToolAnnotations(
                title="Declare draft guide documents",
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        ),
        Tool(
            name="workstream_guides_update",
            description="Update only the change summary of one draft guide.",
            input_schema=GUIDE_INPUT_SCHEMAS["guides_update"],
            output_schema=guide_output_schema("guides_update"),
            annotations=ToolAnnotations(
                title="Edit draft guide summary",
                read_only_hint=False,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        ),
    ]


def _valid_task_examples(arguments: dict[str, Any]) -> bool:
    body = arguments.get("body")
    if not isinstance(body, dict) or "task_examples" not in body:
        return True
    examples = body["task_examples"]
    if not isinstance(examples, list):
        return False
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("content"), str)
        or not item["content"].strip()
        for item in examples
    ):
        return False
    normalized = [
        {
            "content": item["content"],
            "title": item.get("title"),
            "labels": item.get("labels", []),
        }
        for item in examples
    ]
    try:
        encoded = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError):
        return False
    return len(encoded) <= _MAXIMUM_TASK_EXAMPLE_BYTES


async def invoke(
    gateway: WorkstreamGateway,
    tool_name: str,
    bearer: str,
    correlation_id: str | None,
    arguments: dict[str, Any],
) -> CallToolResult:
    """Validate one guide mutation before fixed-route dispatch."""
    contract_name = _CONTRACT_NAMES.get(tool_name)
    if contract_name is None:
        return adapter_failure("unknown_tool", status=404)
    try:
        _INPUT_VALIDATORS[contract_name].validate(arguments)
    except ValidationError:
        return adapter_failure("invalid_tool_input", status=400)
    if not _valid_task_examples(arguments):
        return adapter_failure("invalid_tool_input", status=400)

    outcome = await gateway.guide_mutation(
        contract_name, bearer, arguments, correlation_id
    )
    if outcome.failure is not None:
        return outcome.failure.result()
    data = outcome.data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
        structured_content=data,
    )
