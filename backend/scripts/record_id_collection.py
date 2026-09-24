"""Collection-only UUIDv7 fixture stability shared by both lane collectors.

This never substitutes the runtime generator during test execution. Stable
collection identities are fixture values, not timestamps or production IDs.
"""

import hashlib
import inspect
from pathlib import Path
import sys
from collections.abc import Callable
from uuid import UUID


class RecordIdCollection:
    def __init__(self) -> None:
        self._original: Callable[[], UUID] | None = None
        self._root: Path | None = None
        self._head = ""
        self._counts: dict[tuple[str, int], int] = {}
        # Keep one callable identity so imported aliases can be restored.
        self._replacement = self._generate

    def start(self, root: Path, head: str) -> None:
        from app.core import identifiers

        self.restore()
        self._original = identifiers.new_record_id
        self._root, self._head = root.resolve(), head
        identifiers.new_record_id = self._replacement

    def _generate(self) -> UUID:
        original, root = self._original, self._root
        if original is None or root is None:
            raise RuntimeError("record collection scope is not active")
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        try:
            if caller is None:
                return original()
            try:
                path = Path(caller.f_code.co_filename).resolve().relative_to(root).as_posix()
            except (OSError, ValueError):
                return original()
            site = (path, caller.f_lineno)
            ordinal = self._counts.get(site, 0)
            self._counts[site] = ordinal + 1
            key = f"uuid7\0{self._head}\0{path}\0{site[1]}\0{ordinal}".encode()
            raw = bytearray(hashlib.sha256(key).digest()[:16])
            raw[6] = (raw[6] & 0x0F) | 0x70
            raw[8] = (raw[8] & 0x3F) | 0x80
            return UUID(bytes=bytes(raw))
        finally:
            del caller, frame

    def restore(self) -> None:
        if self._original is not None:
            from app.core import identifiers

            identifiers.new_record_id = self._original
            for module in tuple(sys.modules.values()):
                module_file = getattr(module, "__file__", None)
                if not isinstance(module_file, str) or self._root is None:
                    continue
                try:
                    Path(module_file).resolve().relative_to(self._root)
                except (OSError, ValueError):
                    continue
                for name, value in tuple(vars(module).items()):
                    if value is self._replacement:
                        setattr(module, name, self._original)
        self._original, self._root = None, None
        self._head = ""
        self._counts.clear()
