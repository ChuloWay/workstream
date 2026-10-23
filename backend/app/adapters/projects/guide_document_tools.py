"""Trusted composition of ART originals, fixed parsing, and PROJECTS receipts."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from app.adapters.guide_document_tools.contracts import (
    GuideDocumentParserAdapter,
    GuideDocumentParserRequest,
    MAXIMUM_RESULT_CHARACTERS,
    MAXIMUM_SOURCE_BYTES,
)
from app.interfaces.guide_document_tools import GuideDocumentToolPort, GuideDocumentToolResult
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import (
    GuideDocumentAccessCustody,
    GuideDocumentAccessFactory,
    GuideDocumentAccessReceipt,
    GuideDocumentManifest,
)


class TrustedGuideDocumentTools(GuideDocumentToolPort):
    """Expose text only after exact grant, parser binding, and receipt commit."""

    def __init__(
        self,
        *,
        grant,
        parser: GuideDocumentParserAdapter,
        custody: GuideDocumentAccessCustody,
        manifest: GuideDocumentManifest,
        configuration: ProjectGuideRuntimeConfiguration,
    ) -> None:
        if (
            len(manifest.documents) > configuration.maximum_documents
            or sum(item.byte_count for item in manifest.documents)
            > configuration.maximum_total_document_bytes
            or any(
                item.byte_count > min(configuration.maximum_document_bytes, MAXIMUM_SOURCE_BYTES)
                for item in manifest.documents
            )
        ):
            raise ValueError("guide document manifest exceeds runtime bounds")
        self._grant = grant
        self._parser = parser
        self._custody = custody
        self._manifest = manifest
        self._documents = {manifest.handle_for(item): item for item in manifest.documents}
        self._configuration = configuration
        self._budget_lock = asyncio.Lock()
        self._tool_calls = 0
        self._tool_output_characters = 0

    async def read_document(
        self, handle: str, *, offset: int = 0, limit: int = 16_000
    ) -> GuideDocumentToolResult:
        """Return one bounded source-character slice from an authorized original."""
        return await self._execute(
            handle=handle,
            operation="read",
            offset=offset,
            limit=limit,
            query=None,
        )

    async def search_document(
        self,
        handle: str,
        query: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> GuideDocumentToolResult:
        """Return bounded literal-search excerpts from an authorized original."""
        return await self._execute(
            handle=handle,
            operation="search",
            offset=offset,
            limit=limit,
            query=query,
        )

    async def opened_handles(self) -> frozenset[str]:
        """Read committed exact-access evidence, never adapter-local claims."""
        return await self._custody.opened_handles()

    async def _execute(self, *, handle, operation, offset, limit, query):
        document = self._documents.get(handle)
        if document is None:
            raise ValueError("guide document handle is not granted")
        request = GuideDocumentParserRequest(
            request_id=uuid4(),
            source_sha256=document.sha256,
            source_byte_count=document.byte_count,
            media_type=document.media_type,
            operation=operation,
            offset=offset,
            limit=limit,
            query=query,
        )
        await self._consume_call_budget()
        source = b""
        async with self._grant.open(handle) as opened:
            if opened.document != document:
                raise RuntimeError("guide document grant returned another source")
            source = opened.reader.read(self._configuration.maximum_document_bytes + 1)
        if len(source) != document.byte_count:
            source = b""
            raise RuntimeError("guide document grant returned inconsistent bytes")
        try:
            response = await self._parser.parse(request, source)
        finally:
            source = b""
        response.validate_against(request)
        result = GuideDocumentToolResult(
            handle=handle,
            source_item_id=document.source_item_id,
            document_version_id=document.ingest_id,
            sha256=document.sha256,
            operation=operation,
            text=response.text,
            locators=response.locators,
            next_offset=response.next_offset,
            total_characters=response.total_characters,
        )
        await self._reserve_output(result)
        await self._custody.record_success(_receipt(handle, document, response))
        return result

    async def _consume_call_budget(self) -> None:
        async with self._budget_lock:
            if self._tool_calls >= self._configuration.maximum_tool_calls:
                raise ValueError("guide document tool call budget exceeded")
            self._tool_calls += 1

    async def _reserve_output(self, result: GuideDocumentToolResult) -> None:
        if len(result.text) > MAXIMUM_RESULT_CHARACTERS:
            raise ValueError("guide document tool result exceeds per-call bound")
        serialized_characters = len(result.model_dump_json())
        async with self._budget_lock:
            total = self._tool_output_characters + serialized_characters
            if total > self._configuration.maximum_tool_output_characters:
                raise ValueError("guide document tool output budget exceeded")
            self._tool_output_characters = total


def _receipt(handle, document, response) -> GuideDocumentAccessReceipt:
    return GuideDocumentAccessReceipt(
        handle=handle,
        source_item_id=document.source_item_id,
        document_version_id=document.ingest_id,
        sha256=document.sha256,
        operation=response.operation,
        parser_request_hash=response.request_hash,
        parser_response_hash=response.response_hash,
        parser_build_digest=response.parser_build_digest,
    )


def trusted_guide_document_tools_factory(
    *,
    grant_factory: GuideDocumentAccessFactory,
    parser_factory: Callable[[], GuideDocumentParserAdapter],
    custody_factory: Callable[
        [UUID, GuideDocumentManifest, ProjectGuideRuntimeConfiguration],
        GuideDocumentAccessCustody,
    ],
):
    """Bind privileged dependencies once and return the narrow tool factory."""

    @asynccontextmanager
    async def factory(attempt_id, manifest, configuration):
        async with grant_factory(attempt_id, manifest, configuration) as grant:
            yield TrustedGuideDocumentTools(
                grant=grant,
                parser=parser_factory(),
                custody=custody_factory(attempt_id, manifest, configuration),
                manifest=manifest,
                configuration=configuration,
            )

    return factory


__all__ = ("TrustedGuideDocumentTools", "trusted_guide_document_tools_factory")
