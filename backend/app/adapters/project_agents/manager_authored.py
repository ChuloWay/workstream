"""Provider-free guide compilation from a manager-authored rules document.

The manager uploads one rules document with the guide originals. This runtime
reads every granted original through the attempt's document grant, records
each read, and converts the rules document into the same untrusted
``ProjectGuideCompilationResult`` that a model runtime returns. It performs no
network call, runs no inference and allocates no provider resources. All
downstream validation, review and approval apply unchanged.

Rules document identification: exactly one granted ``text/markdown`` original
whose complete UTF-8 body is a JSON object with
``"format": "workstream.project_guide_rules.v1"``. Guide manifests deliberately
carry no source-controlled filenames, and JSON is not an admitted guide media
type, so the format marker is the identifying rule. Managers should still label
the upload ``workstream-rules.json`` so people can find it.
"""

from __future__ import annotations

import asyncio
import json

from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.project_agents import (
    MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES,
    PROJECT_GUIDE_COMPILATION_AGENT_NAME,
    PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION,
    ProjectAgentRuntimeConfigurationError,
    ProjectAgentRuntimeError,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationInvalidOutputError,
    ProjectGuideCompilationResult,
    invalid_compilation_failure_code,
    require_complete_project_guide_compilation_result,
    require_ready_result_cites_every_document,
    validate_project_guide_compilation_result,
)
from app.interfaces.project_guide_runtime import (
    MANAGER_AUTHORED_RUNTIME_KEY,
    ProjectGuideRuntimeConfiguration,
)
from app.modules.projects.api.guide_documents import (
    GuideDocumentVersion,
    GuideRuntimeCapabilities,
)

RULES_DOCUMENT_FORMAT = "workstream.project_guide_rules.v1"
MAXIMUM_RULES_DOCUMENT_BYTES = MAXIMUM_COMPILATION_RESULT_STORAGE_BYTES
_RESULT_FIELDS = frozenset({
    "status", "findings", "submission_artifact_policy", "requirements",
    "pre_submit_bindings", "post_submit_bindings", "capability_suggestions", "setup_notes",
})
_EVIDENCE_FIELDS = ("findings", "requirements", "capability_suggestions")
_AUTHOR_REF_FIELDS = frozenset({"document", "start_page", "end_page", "section"})


class ManagerAuthoredProjectGuideRuntime:
    """Compile a guide from the manager's rules document without any model call."""

    def __init__(self, configuration: ProjectGuideRuntimeConfiguration) -> None:
        """Accept only the exact provider-free configuration recorded for this runtime."""
        if (configuration.runtime_key != MANAGER_AUTHORED_RUNTIME_KEY
                or not configuration.provider_free):
            raise ProjectAgentRuntimeConfigurationError("project guide runtime is unsupported")
        self._configuration = configuration
        self._admitted = False

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Expose the immutable identity checked by the shared factory."""
        return self._configuration.adapter_identity

    def admit_execution(self) -> None:
        """Admit once; there is no provider and therefore no model circuit to consult."""
        if self._admitted:
            raise ProjectAgentRuntimeError("project guide runtime admission already acquired")
        self._admitted = True

    async def cleanup_resources(self, custody) -> bool:
        """Report clean custody; this runtime never records provider resources."""
        try:
            return not await custody.cleanup_resources()
        except Exception:
            return False

    async def aclose(self) -> None:
        """Nothing to release: no admission lease, client or workspace exists."""

    async def compile_project_guide(
        self,
        context: ProjectGuideCompilationContext,
        capabilities: GuideRuntimeCapabilities,
    ) -> ProjectGuideCompilationResult:
        """Read every granted original once and convert the single rules document."""
        if context.runtime_configuration != self._configuration:
            raise ProjectAgentRuntimeConfigurationError(
                "project guide runtime configuration mismatch"
            )
        if not self._admitted:
            raise ProjectAgentRuntimeError("project guide runtime was not admitted")
        runtime_failure = None
        rules = None
        try:
            rules = await asyncio.wait_for(
                _read_rules_documents(context, capabilities),
                timeout=self._configuration.timeout_seconds,
            )
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            runtime_failure = "project guide run cancelled"
        except TimeoutError:
            runtime_failure = "project guide run timed out"
        except Exception:
            runtime_failure = "project guide document access failed"
        # Raise outside the handlers so no traceback frame retains document bytes.
        if runtime_failure is not None:
            raise ProjectAgentRuntimeError(runtime_failure) from None
        invalid_failure = None
        try:
            return _compile_rules(context, rules)
        except (TypeError, ValueError) as error:
            invalid_failure = invalid_compilation_failure_code(error)
        rules = None
        raise ProjectGuideCompilationInvalidOutputError(invalid_failure) from None


async def _read_rules_documents(
    context: ProjectGuideCompilationContext,
    capabilities: GuideRuntimeCapabilities,
) -> list[tuple[GuideDocumentVersion, object]]:
    """Open and record every assigned original; return each rules-document candidate."""
    manifest = context.material
    candidates: list[tuple[GuideDocumentVersion, object]] = []
    for document in manifest.documents:
        handle = manifest.handle_for(document)
        # The ART grant authorizes and checksum-verifies bytes before yielding a reader.
        async with capabilities.documents.open(handle) as opened:
            if opened.document != document:
                raise RuntimeError("guide document version mismatch")
            body = (opened.reader.read(MAXIMUM_RULES_DOCUMENT_BYTES + 1)
                    if document.media_type == "text/markdown" else b"")
            await capabilities.resources.record_direct_document_open(handle)
        parsed = _rules_candidate(body)
        if parsed is not None:
            candidates.append((document, parsed))
    return candidates


def _rules_candidate(body: bytes) -> object | None:
    """Return the parsed body when it declares the rules format, else ``None``."""
    if not body or len(body) > MAXIMUM_RULES_DOCUMENT_BYTES or not body.lstrip().startswith(b"{"):
        return None
    try:
        value = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        # Undecodable, malformed or pathologically nested JSON is not a rules
        # document; with no valid candidate the attempt ends as schema_invalid.
        return None
    if isinstance(value, dict) and value.get("format") == RULES_DOCUMENT_FORMAT:
        return value
    return None


def _compile_rules(
    context: ProjectGuideCompilationContext,
    candidates: list[tuple[GuideDocumentVersion, object]] | None,
) -> ProjectGuideCompilationResult:
    """Resolve author references and apply the shared trusted validation."""
    if not candidates or len(candidates) != 1:
        raise ValueError("guide requires exactly one rules document")
    rules_document, rules = candidates[0]
    if not isinstance(rules, dict) or set(rules) != _RESULT_FIELDS | {"format"}:
        raise ValueError("rules document fields are invalid")
    body = {key: value for key, value in rules.items() if key != "format"}
    for field in _EVIDENCE_FIELDS:
        items = body[field]
        if not isinstance(items, list):
            raise ValueError("rules document item list is invalid")
        body[field] = [_with_resolved_evidence(context, rules_document, item) for item in items]
    body.update(
        agent_name=PROJECT_GUIDE_COMPILATION_AGENT_NAME,
        agent_version=context.agent_version,
        schema_version=PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION,
    )
    result = ProjectGuideCompilationResult.model_validate(body)
    require_complete_project_guide_compilation_result(result)
    validate_project_guide_compilation_result(context, result)
    require_ready_result_cites_every_document(context, result)
    return result


def _with_resolved_evidence(
    context: ProjectGuideCompilationContext,
    rules_document: GuideDocumentVersion,
    item: object,
) -> dict:
    """Replace author references and attribute the item to the rules document itself."""
    if not isinstance(item, dict):
        raise ValueError("rules document item is invalid")
    authored = item.get("evidence_refs", [])
    if not isinstance(authored, list):
        raise ValueError("rules document evidence is invalid")
    refs = [_resolved_ref(context, ref) for ref in authored]
    # Every authored item is stated in the rules document, so it is cited as evidence.
    if not any(ref["source_item_id"] == str(rules_document.source_item_id) for ref in refs):
        refs.append(_lineage(rules_document))
    return {**item, "evidence_refs": refs}


def _resolved_ref(context: ProjectGuideCompilationContext, ref: object) -> dict:
    """Resolve one SHA-256 or manifest-filename reference to exact document lineage."""
    if not isinstance(ref, dict) or not set(ref) <= _AUTHOR_REF_FIELDS:
        raise ValueError("rules document evidence reference is invalid")
    selector = ref.get("document")
    if not isinstance(selector, str):
        raise ValueError("rules document evidence reference is invalid")
    key = "sha256" if selector.startswith("sha256:") else "filename"
    matches = [item for item in context.material.documents if getattr(item, key) == selector]
    if len(matches) != 1:
        raise ValueError("rules document evidence reference does not resolve")
    return {**_lineage(matches[0]),
            **{name: value for name, value in ref.items() if name != "document"}}


def _lineage(document: GuideDocumentVersion) -> dict:
    return {
        "source_item_id": str(document.source_item_id),
        "document_version_id": str(document.ingest_id),
        "sha256": document.sha256,
    }
