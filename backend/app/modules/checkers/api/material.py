"""Detached verified material metadata shared by PRE and POST contracts."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class SubmissionMaterialEntry:
    """Expose verified archive metadata without a filesystem path."""

    normalized_path: str
    entry_type: Literal["file", "directory"]
    byte_count: int
    sha256: str | None
    executable: bool | None


__all__ = ("SubmissionMaterialEntry",)
