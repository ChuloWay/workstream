"""Canonical machine-field syntax shared by policy proposal and execution owners."""

from pathlib import PurePosixPath
import unicodedata


def _canonical_relative(value: str, *, pattern: bool) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value != unicodedata.normalize("NFC", value):
        return False
    if value.startswith(("~", "/")) or any(
        character in value
        for character in ("\\", ":", "%", "#", "\x00", "`", "$", ";", "|", "<", ">")
    ):
        return False
    if any(unicodedata.category(character) in {"Cc", "Cs", "Cf"} for character in value):
        return False
    if not pattern and any(character in value for character in "*?[]"):
        return False
    path = PurePosixPath(value)
    return value == path.as_posix() and all(
        part not in {"", ".", ".."} for part in value.split("/")
    )


def is_canonical_relative_path(value: str) -> bool:
    """Accept one exact portable relative artifact path, without glob semantics."""
    return _canonical_relative(value, pattern=False)


def is_canonical_relative_pattern(value: str) -> bool:
    """Accept one relative fnmatch pattern; prohibited secret names remain expressible."""
    return _canonical_relative(value, pattern=True)


def required_evidence_path(key: object) -> str:
    """Project an evidence identity into Workstream's closed evidence namespace."""
    if (
        not isinstance(key, str)
        or not key
        or any(
            not (character.isascii() and (character.isalnum() or character in "._-"))
            for character in key
        )
    ):
        raise ValueError(
            "effective project submission evidence key is unmappable"
        )
    path = f"evidence/{key}"
    if not is_canonical_relative_path(path):
        raise ValueError(
            "effective project submission evidence key is unmappable"
        )
    return path
