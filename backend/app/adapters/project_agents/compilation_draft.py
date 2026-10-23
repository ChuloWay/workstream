"""Bound an untrusted private candidate without treating it as accepted policy."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import ValidationError

from app.interfaces.project_agents import ProjectGuideCompilationResult


def _unique_object(pairs):
    """Reject duplicate JSON members instead of silently selecting one value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(_value):
    """Reject nonstandard JSON numeric constants without copying their text."""
    raise ValueError("nonstandard JSON constant")


class CompilationDraftParser:
    """Use the canonical SDK schema for structure, leaving correction to review."""

    def __init__(self, schema: dict, maximum_bytes: int) -> None:
        """Cache a trusted local-only schema and its bounded diagnostic field names."""
        pending = [schema]
        self._fields = set()
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                if "$id" in node or any(
                    key in node
                    and (not isinstance(node[key], str) or not node[key].startswith("#/"))
                    for key in ("$ref", "$dynamicRef", "$recursiveRef")
                ):
                    raise ValueError("guide draft schema must use only local references")
                self._fields.update(node.get("properties", {}))
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)
        self._validator = Draft202012Validator(schema)
        self._maximum_bytes = maximum_bytes

    def parse(self, raw: str) -> dict | None:
        """Return only bounded structural data; failed parsing exposes no error object."""
        try:
            if len(raw.encode("utf-8")) > self._maximum_bytes:
                return None
            candidate = json.loads(
                raw,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            if not isinstance(candidate, dict):
                return None
            self._validator.validate(candidate)
            # Escaped lone surrogates and non-finite numeric overflow must not
            # become serialization failures after the provider boundary.
            json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, RecursionError, UnicodeError, SchemaValidationError):
            return None
        return candidate

    def canonical_issues(self, candidate: dict) -> list[dict]:
        """Identify failing fields without forwarding rejected values or error messages."""
        try:
            ProjectGuideCompilationResult.model_validate(candidate)
        except ValidationError as error:
            return [
                {
                    "path": [
                        part if isinstance(part, int) or part in self._fields else "<field>"
                        for part in item["loc"][:16]
                    ],
                    "code": "canonical_constraint",
                }
                for item in error.errors(
                    include_input=False, include_context=False, include_url=False
                )[:20]
            ]
        return []
