"""Scripted document tools for PostgreSQL orchestration proofs.

These tests exercise real parser-bound access custody. ART byte authorization
and parser transport are proved separately, not simulated as live.
"""

from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

from app.adapters.guide_document_tools import (
    GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
    GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    GuideDocumentParserAdapter,
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
)
from app.adapters.projects import project_guide_document_tools_factory
from app.core.config import Settings
from app.interfaces.external_services import (
    ExternalServiceAdapterFactory,
    ExternalServiceAdapterIdentity,
)
from app.interfaces.guide_document_tools import GuideTextLocator
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import OpenGuideDocument
from .helpers import SOURCE_BYTES, SOURCE_SHA256, generated_result, runtime_configuration
from app.interfaces.project_agents import GuideEvidenceRef


@asynccontextmanager
async def document_access(_attempt_id, manifest, _configuration):
    class Documents:
        @asynccontextmanager
        async def open(self, handle):
            item = next(item for item in manifest.documents if manifest.handle_for(item) == handle)
            with BytesIO(SOURCE_BYTES) as stream:
                yield OpenGuideDocument(item, stream)

        async def close(self):
            pass

    yield Documents()


class ScriptedParser:
    """Return one exact response while retaining the production source bindings."""

    identity = ExternalServiceAdapterIdentity(
        GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY,
        GUIDE_DOCUMENT_PARSER_PROVIDER_KEY,
    )

    async def parse(self, request: GuideDocumentParserRequest, source: bytes):
        text = source.decode()
        return GuideDocumentParserResponse.create(
            request=request,
            text=text,
            locators=(GuideTextLocator(label="document", start=0, end=len(text)),),
            next_offset=None,
            total_characters=len(text),
        )


def scripted_guide_document_parser_factory(
    *, socket_path: Path, timeout_seconds: float
) -> ExternalServiceAdapterFactory[GuideDocumentParserAdapter]:
    """Inject the scripted parser through the worker's typed parser factory."""
    assert socket_path.is_absolute()
    assert timeout_seconds == 30.0
    factory = ExternalServiceAdapterFactory[GuideDocumentParserAdapter](
        GUIDE_DOCUMENT_PARSER_CAPABILITY_KEY
    )
    factory.register(GUIDE_DOCUMENT_PARSER_PROVIDER_KEY, ScriptedParser)
    return factory


def scripted_runtime_configuration(
    _settings: Settings,
    *,
    adapter_profile_builder: Callable[[Mapping[str, object]], Mapping[str, object]],
) -> ProjectGuideRuntimeConfiguration:
    """Accept the current composition signature and return fixed test settings."""
    assert callable(adapter_profile_builder)
    return runtime_configuration()


def scripted_document_access_runtime(
    _session_factory, attempt_id, manifest, configuration
):
    """Preserve the production access-runtime call shape around scripted bytes."""
    return document_access(attempt_id, manifest, configuration)


def document_tools(session_factory, *, document_access_factory=None):
    """Bind the test grant/parser to the production PROJECTS receipt owner."""
    return project_guide_document_tools_factory(
        session_factory,
        document_access_factory=document_access_factory or document_access,
        parser_factory=ScriptedParser,
    )


async def record_scripted_document_access(context, capabilities):
    for document in context.material.documents:
        handle = context.material.handle_for(document)
        result = await capabilities.tools.read_document(handle)
        assert result.source_item_id == document.source_item_id
        assert result.document_version_id == document.ingest_id
        assert result.sha256 == document.sha256
        assert result.text
        if document.sha256 == SOURCE_SHA256:
            assert result.text.encode() == SOURCE_BYTES


async def record_attempt_document_access(sessions, attempt_id, context):
    """Arrange real parser-bound access custody after a committed fence."""
    from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities

    async with document_tools(sessions)(
        attempt_id, context.material, context.runtime_configuration
    ) as tools:
        await record_scripted_document_access(context, GuideRuntimeCapabilities(tools=tools))


class ScriptedGuideRuntime:
    outcome = generated_result()
    identity = runtime_configuration().adapter_identity
    calls = 0

    def admit_execution(self):
        pass

    async def aclose(self):
        pass

    async def compile_project_guide(self, context, capabilities):
        self.calls += 1
        await record_scripted_document_access(context, capabilities)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        refs = tuple(
            GuideEvidenceRef(
                source_item_id=item.source_item_id,
                document_version_id=item.ingest_id,
                sha256=item.sha256,
            )
            for item in context.material.documents
        )
        return self.outcome.model_copy(
            update={
                field: tuple(
                    item.model_copy(update={"evidence_refs": refs})
                    for item in getattr(self.outcome, field)
                )
                for field in ("findings", "requirements", "capability_suggestions")
            }
        )
