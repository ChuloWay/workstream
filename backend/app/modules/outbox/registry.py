"""Explicit static feature registrations; registry membership is not authority."""

from collections.abc import Iterable
import inspect
import re
from types import MappingProxyType

from app.modules.outbox.api import OutboxHandler


class HandlerRegistry:
    """Exact immutable registration set with no default or dynamic discovery."""

    def __init__(
        self, entries: Iterable[tuple[str, int, OutboxHandler]], *,
        replay_safe: frozenset[tuple[str, int]] = frozenset(),
    ) -> None:
        """Reject duplicate and malformed registrations during composition."""
        handlers = {}
        for event_type, version, handler in entries:
            if (
                type(event_type) is not str
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]{0,127}", event_type) is None
                or type(version) is not int
                or not 1 <= version <= 32767
                or not callable(handler)
                or isinstance(handler, type)
                or not (
                    inspect.iscoroutinefunction(handler)
                    or inspect.iscoroutinefunction(getattr(handler, "__call__", None))
                )
                or (event_type, version) in handlers
            ):
                raise ValueError("outbox registration is invalid")
            handlers[event_type, version] = handler
        if (type(replay_safe) is not frozenset
                or any(type(key) is not tuple or len(key) != 2
                       or type(key[0]) is not str or type(key[1]) is not int
                       for key in replay_safe)
                or not replay_safe.issubset(handlers)):
            raise ValueError("replay-safe handlers must be explicitly registered")
        self._replay_safe = replay_safe
        self._handlers = MappingProxyType(handlers)

    @property
    def keys(self) -> tuple[tuple[str, int], ...]:
        """Return immutable exact type/version selectors for bounded observation."""
        return tuple(self._handlers)

    def get(self, event_type: str, version: int) -> OutboxHandler | None:
        """Unknown types remain unavailable, never inferred or acknowledged."""
        return self._handlers.get((event_type, version))

    def can_retry_unknown(self, event_type: str, version: int) -> bool:
        """Only explicitly receipt-idempotent handlers may repeat an unknown call."""
        return (event_type, version) in self._replay_safe
