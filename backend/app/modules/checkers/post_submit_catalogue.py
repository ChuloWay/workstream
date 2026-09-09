"""Validate installed handlers against the one current public catalogue."""

from __future__ import annotations
from typing import TYPE_CHECKING
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitCatalogue,
    current_post_submit_catalogue,
)

if TYPE_CHECKING:
    from app.modules.checkers.runner import CheckerRegistry


def build_post_submit_catalogue(registry: CheckerRegistry) -> PostSubmitCatalogue:
    """Require exact metadata and callable installation parity."""
    catalogue = current_post_submit_catalogue()
    if registry.names() != {item.capability_id for item in catalogue.definitions}:
        raise ValueError("post-submit registered catalogue is incomplete")
    for definition in catalogue.definitions:
        entry = registry.resolve(definition.capability_id)
        if entry.definition != definition or entry.checker.name != definition.capability_id:
            raise ValueError("post-submit registered implementation mismatch")
    return catalogue
