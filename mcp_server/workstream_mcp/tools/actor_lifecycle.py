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
from workstream_mcp.schemas import (
    ACTOR_LIFECYCLE_INPUT_SCHEMAS,
    actor_lifecycle_output_schema,
)

TOOL_NAMES = (
    "workstream_actor_suspend",
    "workstream_actor_reactivate",
    "workstream_actor_deactivate",
    "workstream_identity_link_revoke",
    "workstream_identity_link_reactivate",
)
_CONTRACT_NAMES = {
    "workstream_actor_suspend": "actor_suspend",
    "workstream_actor_reactivate": "actor_reactivate",
    "workstream_actor_deactivate": "actor_deactivate",
    "workstream_identity_link_revoke": "identity_link_revoke",
    "workstream_identity_link_reactivate": "identity_link_reactivate",
}
_DESCRIPTIONS = {
    "actor_suspend": "Suspend an actor profile through Workstream authorization.",
    "actor_reactivate": "Reactivate a suspended actor profile through Workstream authorization.",
    "actor_deactivate": "Permanently deactivate an actor profile through Workstream authorization.",
    "identity_link_revoke": "Revoke an actor identity link through Workstream authorization.",
    "identity_link_reactivate": (
        "Reactivate a revoked identity link through Workstream authorization."
    ),
}
_TITLES = {
    "actor_suspend": "Suspend actor",
    "actor_reactivate": "Reactivate actor",
    "actor_deactivate": "Deactivate actor",
    "identity_link_revoke": "Revoke identity link",
    "identity_link_reactivate": "Reactivate identity link",
}
_FORMAT_CHECKER = FormatChecker()


def definitions() -> list[Tool]:
    return [
        Tool(
            name=tool_name,
            description=_DESCRIPTIONS[contract_name],
            input_schema=ACTOR_LIFECYCLE_INPUT_SCHEMAS[contract_name],
            output_schema=actor_lifecycle_output_schema(contract_name),
            annotations=ToolAnnotations(
                title=_TITLES[contract_name],
                read_only_hint=False,
                destructive_hint=True,
                idempotent_hint=True,
                open_world_hint=False,
            ),
        )
        for tool_name, contract_name in _CONTRACT_NAMES.items()
    ]


def _valid_arguments(contract_name: str, arguments: dict[str, Any]) -> bool:
    try:
        Draft202012Validator(
            ACTOR_LIFECYCLE_INPUT_SCHEMAS[contract_name],
            format_checker=_FORMAT_CHECKER,
        ).validate(arguments)
    except ValidationError:
        return False
    reason = arguments["body"]["reason"]
    return 1 <= len(reason.encode("utf-8")) <= 500


async def invoke(
    gateway: WorkstreamGateway,
    tool_name: str,
    bearer: str,
    correlation_id: str | None,
    arguments: dict[str, Any],
) -> CallToolResult:
    contract_name = _CONTRACT_NAMES[tool_name]
    if not _valid_arguments(contract_name, arguments):
        return adapter_failure("invalid_tool_input", status=400)
    outcome = await gateway.actor_lifecycle_mutation(
        contract_name, bearer, arguments, correlation_id
    )
    if outcome.failure is not None:
        return outcome.failure.result()
    data = outcome.data or {}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
        structured_content=data,
    )
