"""Runtime-independent, read-only tools for a fenced guide compilation."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class GuideTextLocator(BaseModel):
    """A parser-derived location within a bounded returned text fragment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=100)
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(ge=0)


class GuideDocumentToolResult(BaseModel):
    """Verified source identity and bounded text exposed by the trusted tool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handle: str
    source_item_id: UUID
    document_version_id: UUID
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    operation: Literal["read", "search"]
    text: str = Field(max_length=65536)
    locators: tuple[GuideTextLocator, ...] = Field(max_length=512)
    next_offset: StrictInt | None = Field(default=None, ge=0)
    total_characters: StrictInt = Field(ge=0)


class GuideDocumentToolPort(Protocol):
    """Tools carry their authority; callers cannot supply storage or custody selectors."""

    async def read_document(
        self, handle: str, *, offset: int = 0, limit: int = 16000,
    ) -> GuideDocumentToolResult: ...

    async def search_document(
        self, handle: str, query: str, *, offset: int = 0, limit: int = 20,
    ) -> GuideDocumentToolResult: ...

    async def opened_handles(self) -> frozenset[str]: ...
