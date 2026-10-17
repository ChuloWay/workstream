"""Persisted checker policy custody shared by selected policy owners."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompiledPreSubmitCheckerPolicy:
    """Compiled bundle plus index projections persisted on policy rows."""

    compiler_version: str
    compiled_bundle: dict[str, Any]
    compiled_bundle_hash: str
    checker_names: list[str]
    checker_configs: dict[str, Any]
