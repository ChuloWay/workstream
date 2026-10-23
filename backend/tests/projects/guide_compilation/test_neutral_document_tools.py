"""Trusted document tools expose text only with exact committed receipts."""

from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.adapters.guide_document_tools import (
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
)
from app.adapters.guide_document_tools.contracts import MAXIMUM_SOURCE_BYTES
from app.adapters.projects.guide_document_tools import TrustedGuideDocumentTools
from app.interfaces.guide_document_tools import GuideTextLocator
from app.interfaces.project_guide_runtime import (
    ProjectGuideRuntimeConfiguration,
    canonical_adapter_profile,
)
from app.modules.projects.api.guide_documents import (
    GuideDocumentManifest,
    GuideDocumentVersion,
    GuideRuntimeCapabilities,
    OpenGuideDocument,
)

SOURCE = b"# Rules\nSubmit one archive.\n"
SHA = "sha256:c014b3b6b7ae3a886ee0ba5693afbccc82ec640b1a7a0636549fafc61383c0ad"


def _case():
    document = GuideDocumentVersion(
        source_item_id=uuid4(),
        ingest_id=uuid4(),
        item_order=0,
        put_attempt_id=uuid4(),
        content_id=uuid4(),
        replica_id=uuid4(),
        storage_namespace_id="primary",
        namespace_fingerprint="sha256:" + "a" * 64,
        sha256=SHA,
        byte_count=len(SOURCE),
        media_type="text/markdown",
    )
    manifest = GuideDocumentManifest(
        project_id=uuid4(),
        guide_id=uuid4(),
        guide_version="v1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash="sha256:" + "b" * 64,
        setup_run_id=uuid4(),
        setup_generation=1,
        documents=(document,),
    )
    instructions = "Inspect assigned originals."
    import hashlib

    configuration = ProjectGuideRuntimeConfiguration(
        runtime_key="test_runtime",
        model_provider="test_provider",
        model="test-model",
        model_api="test_api",
        adapter_profile=canonical_adapter_profile({"profile_key": "test_runtime.v1"}),
        instruction_version="v1",
        instructions=instructions,
        instructions_sha256="sha256:" + hashlib.sha256(instructions.encode()).hexdigest(),
        timeout_seconds=30,
        maximum_document_bytes=1024,
        maximum_total_document_bytes=1024,
        maximum_tool_calls=3,
        maximum_tool_output_characters=65_536,
    )
    return manifest, document, configuration


class Grant:
    def __init__(self, document, payload=SOURCE):
        self.document = document
        self.payload = payload
        self.calls = 0

    @asynccontextmanager
    async def open(self, _handle):
        self.calls += 1
        yield OpenGuideDocument(self.document, BytesIO(self.payload))


class Parser:
    identity = SimpleNamespace()

    def __init__(self, *, fault=None):
        self.fault = fault
        self.calls = 0

    async def parse(self, request: GuideDocumentParserRequest, source: bytes):
        self.calls += 1
        if self.fault == "raise":
            raise RuntimeError("parser unavailable")
        response = GuideDocumentParserResponse.create(
            request=request,
            text=source.decode(),
            locators=(GuideTextLocator(label="document", start=0, end=len(source.decode())),),
            next_offset=None,
            total_characters=len(source.decode()),
        )
        if self.fault == "substitute":
            return response.model_copy(update={"request_id": uuid4()})
        return response


class SizedParser:
    identity = SimpleNamespace()

    def __init__(self, *sizes: int):
        self._sizes = iter(sizes)
        self.calls = 0

    async def parse(self, request: GuideDocumentParserRequest, _source: bytes):
        self.calls += 1
        text = "x" * next(self._sizes)
        return GuideDocumentParserResponse.create(
            request=request,
            text=text,
            locators=(GuideTextLocator(label="document", start=0, end=len(text)),),
            next_offset=None,
            total_characters=len(text),
        )


class Custody:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.receipts = []

    async def record_success(self, receipt):
        if self.fail:
            raise RuntimeError("storage unavailable")
        self.receipts.append(receipt)

    async def opened_handles(self):
        return frozenset(receipt.handle for receipt in self.receipts)


def _tools(*, parser=None, custody=None, payload=SOURCE):
    manifest, document, configuration = _case()
    handle = manifest.handle_for(document)
    custody = custody or Custody()
    return (
        TrustedGuideDocumentTools(
            grant=Grant(document, payload),
            parser=parser or Parser(),
            custody=custody,
            manifest=manifest,
            configuration=configuration,
        ),
        handle,
        document,
        custody,
    )


@pytest.mark.asyncio
async def test_valid_read_commits_exact_receipt_before_returning_text():
    tools, handle, document, custody = _tools()
    result = await tools.read_document(handle)
    assert result.text == SOURCE.decode()
    assert (result.source_item_id, result.document_version_id, result.sha256) == (
        document.source_item_id,
        document.ingest_id,
        document.sha256,
    )
    assert await tools.opened_handles() == {handle}
    assert len(custody.receipts) == 1
    assert custody.receipts[0].handle == handle
    assert custody.receipts[0].operation == "read"


@pytest.mark.asyncio
async def test_tool_call_budget_allows_exact_limit_and_rejects_the_next_call():
    parser = Parser()
    tools, handle, _document, custody = _tools(parser=parser)

    for _ in range(3):
        assert (await tools.read_document(handle)).text == SOURCE.decode()

    with pytest.raises(ValueError, match="tool call budget exceeded"):
        await tools.read_document(handle)
    assert parser.calls == 3
    assert len(custody.receipts) == 3


@pytest.mark.asyncio
async def test_tool_output_budget_allows_exact_total_and_rejects_the_next_result():
    parser = SizedParser(32_768, 32_768, 1)
    tools, handle, _document, custody = _tools(parser=parser)

    assert len((await tools.read_document(handle, limit=32_768)).text) == 32_768
    assert len((await tools.read_document(handle, limit=32_768)).text) == 32_768

    with pytest.raises(ValueError, match="tool output budget exceeded"):
        await tools.read_document(handle)
    assert parser.calls == 3
    assert len(custody.receipts) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["raise", "substitute"])
async def test_parser_failure_or_source_substitution_returns_no_text_or_receipt(fault):
    custody = Custody()
    tools, handle, _document, _ = _tools(parser=Parser(fault=fault), custody=custody)
    with pytest.raises((RuntimeError, ValueError)):
        await tools.read_document(handle)
    assert custody.receipts == []
    assert await tools.opened_handles() == set()


@pytest.mark.asyncio
async def test_grant_or_custody_failure_returns_no_successful_receipt():
    custody = Custody(fail=True)
    tools, handle, _document, _ = _tools(custody=custody)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await tools.read_document(handle)
    assert custody.receipts == []

    corrupt, corrupt_handle, _document, corrupt_custody = _tools(payload=SOURCE + b"x")
    with pytest.raises(RuntimeError, match="inconsistent bytes"):
        await corrupt.read_document(corrupt_handle)
    assert corrupt_custody.receipts == []


def test_runtime_capability_exposes_only_tools():
    tools, _handle, _document, _custody = _tools()
    capabilities = GuideRuntimeCapabilities(tools=tools)
    assert tuple(capabilities.__dataclass_fields__) == ("tools",)
    assert not hasattr(capabilities, "documents")
    assert not hasattr(capabilities, "resources")


def test_parser_source_limit_rejects_manifest_before_any_tool_or_inference_call():
    manifest, document, configuration = _case()
    oversized = document.model_copy(update={"byte_count": MAXIMUM_SOURCE_BYTES + 1})
    manifest = manifest.model_copy(update={"documents": (oversized,)})
    configuration = configuration.model_copy(
        update={
            "maximum_document_bytes": MAXIMUM_SOURCE_BYTES + 1,
            "maximum_total_document_bytes": MAXIMUM_SOURCE_BYTES + 1,
        }
    )
    with pytest.raises(ValueError, match="manifest exceeds runtime bounds"):
        TrustedGuideDocumentTools(
            grant=Grant(oversized),
            parser=Parser(),
            custody=Custody(),
            manifest=manifest,
            configuration=configuration,
        )
