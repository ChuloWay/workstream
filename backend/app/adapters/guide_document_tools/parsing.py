"""Deterministic, bounded parsing for the four supported guide formats."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import re
import stat
from typing import NoReturn
import zipfile

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.interfaces.guide_document_tools import GuideTextLocator
from app.modules.artifacts.zip_safety import zip_directory_facts

from .contracts import (
    GuideDocumentParserRejectionReason,
    GuideDocumentParserRequest,
    GuideDocumentParserResponse,
    MAXIMUM_EXTRACTED_CHARACTERS,
    MAXIMUM_LOCATORS,
    MAXIMUM_RESULT_CHARACTERS,
)


_MAXIMUM_ARCHIVE_ENTRIES = 2_000
_MAXIMUM_CENTRAL_DIRECTORY_BYTES = 8 * 1024 * 1024
_MAXIMUM_DECOMPRESSED_BYTES = 128 * 1024 * 1024
_MAXIMUM_COMPRESSION_RATIO = 100
_MAXIMUM_XML_BYTES = 16 * 1024 * 1024
_MAXIMUM_PDF_PAGES = 500
_STREAM_BYTES = 64 * 1024
_SEARCH_CONTEXT_CHARACTERS = 240

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class ParserDocumentRejected(Exception):
    """Internal closed rejection propagated through the parser wire protocol."""

    def __init__(self, reason: GuideDocumentParserRejectionReason) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class _SourceLocator:
    label: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _ExtractedDocument:
    text: str
    locators: tuple[_SourceLocator, ...]


def parse_document(
    request: GuideDocumentParserRequest,
    source: bytes,
) -> GuideDocumentParserResponse:
    """Validate exact source identity, extract once, and apply one bounded operation."""
    if type(source) is not bytes:
        _reject("document_malformed")
    if len(source) != request.source_byte_count:
        _reject("document_malformed")
    if f"sha256:{sha256(source).hexdigest()}" != request.source_sha256:
        _reject("document_malformed")

    if request.media_type == "text/markdown":
        document = _parse_markdown(source)
    elif request.media_type == _DOCX_MEDIA_TYPE:
        document = _parse_docx(source)
    elif request.media_type == _PPTX_MEDIA_TYPE:
        document = _parse_pptx(source)
    elif request.media_type == "application/pdf":
        document = _parse_pdf(source)
    else:  # pragma: no cover - the strict request model owns this boundary
        _reject("document_unsupported")

    if len(document.text) > MAXIMUM_EXTRACTED_CHARACTERS:
        _reject("document_limit_exceeded")
    if request.operation == "read":
        text, locators, next_offset = _read(document, request.offset, request.limit)
    else:
        assert request.query is not None
        text, locators, next_offset = _search(
            document,
            query=request.query,
            offset=request.offset,
            limit=request.limit,
        )
    return GuideDocumentParserResponse.create(
        request=request,
        text=text,
        locators=locators,
        next_offset=next_offset,
        total_characters=len(document.text),
    )


def _parse_markdown(source: bytes) -> _ExtractedDocument:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        _reject("document_malformed")
    if "\x00" in text:
        _reject("document_malformed")
    locators: list[_SourceLocator] = []
    position = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        end = position + len(line)
        locators.append(_SourceLocator(f"line {line_number}", position, end))
        position = end
    if position < len(text) or not locators:
        locators.append(_SourceLocator(f"line {len(locators) + 1}", position, len(text)))
    return _ExtractedDocument(text, tuple(locators))


def _parse_docx(source: bytes) -> _ExtractedDocument:
    xml = _validated_ooxml(source, expected="docx")["word/document.xml"]
    root = _parse_xml(xml)
    blocks: list[tuple[str, str]] = []
    paragraph_tag = f"{{{_WORD_NS}}}p"
    text_tag = f"{{{_WORD_NS}}}t"
    tab_tag = f"{{{_WORD_NS}}}tab"
    break_tags = {f"{{{_WORD_NS}}}br", f"{{{_WORD_NS}}}cr"}
    for block_number, paragraph in enumerate(root.iter(paragraph_tag), start=1):
        value: list[str] = []
        for node in paragraph.iter():
            if node.tag == text_tag and node.text:
                value.append(node.text)
            elif node.tag == tab_tag:
                value.append("\t")
            elif node.tag in break_tags:
                value.append("\n")
        text = "".join(value)
        if text:
            blocks.append((f"block {block_number}", text))
    return _join_parts(blocks)


def _parse_pptx(source: bytes) -> _ExtractedDocument:
    files = _validated_ooxml(source, expected="pptx")
    presentation = _parse_xml(files["ppt/presentation.xml"])
    relationships = _parse_xml(files["ppt/_rels/presentation.xml.rels"])
    targets: dict[str, str] = {}
    for relationship in relationships.iter(f"{{{_PACKAGE_RELATIONSHIP_NS}}}Relationship"):
        relation_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if relation_id and target:
            targets[relation_id] = _resolve_package_target("ppt/presentation.xml", target)

    slides: list[tuple[str, str]] = []
    slide_id_tag = f"{{{_PRESENTATION_NS}}}sldId"
    relationship_id = f"{{{_RELATIONSHIP_NS}}}id"
    text_tag = f"{{{_DRAWING_NS}}}t"
    for slide_number, slide_id in enumerate(presentation.iter(slide_id_tag), start=1):
        relation = slide_id.attrib.get(relationship_id)
        target = targets.get(relation or "")
        if target is None or target not in files or not target.startswith("ppt/slides/"):
            _reject("document_malformed")
        slide = _parse_xml(files[target])
        values = [node.text or "" for node in slide.iter(text_tag)]
        slides.append((f"slide {slide_number}", "\n".join(value for value in values if value)))
    if not slides:
        _reject("document_malformed")
    return _join_parts(slides)


def _parse_pdf(source: bytes) -> _ExtractedDocument:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        _reject("document_unsupported")
    try:
        reader = PdfReader(BytesIO(source), strict=True)
        if reader.is_encrypted:
            _reject("document_encrypted")
        page_count = len(reader.pages)
        if page_count > _MAXIMUM_PDF_PAGES:
            _reject("document_limit_exceeded")
        pages: list[tuple[str, str]] = []
        total = 0
        for page_number, page in enumerate(reader.pages, start=1):
            value = page.extract_text() or ""
            if not isinstance(value, str) or "\x00" in value:
                _reject("document_malformed")
            total += len(value)
            if total > MAXIMUM_EXTRACTED_CHARACTERS:
                _reject("document_limit_exceeded")
            pages.append((f"page {page_number}", value))
    except ParserDocumentRejected:
        raise
    except (PdfReadError, OSError, TypeError, ValueError, KeyError, IndexError, RecursionError):
        _reject("document_malformed")
    return _join_parts(pages)


def _validated_ooxml(source: bytes, *, expected: str) -> dict[str, bytes]:
    reader = BytesIO(source)
    try:
        entries, directory_bytes = zip_directory_facts(reader)
        if entries > _MAXIMUM_ARCHIVE_ENTRIES or directory_bytes > _MAXIMUM_CENTRAL_DIRECTORY_BYTES:
            _reject("document_limit_exceeded")
        reader.seek(0)
        with zipfile.ZipFile(reader) as archive:
            seen: set[str] = set()
            total = 0
            xml_files: dict[str, bytes] = {}
            names: set[str] = set()
            for info in archive.infolist():
                normalized = info.filename.replace("\\", "/")
                path = PurePosixPath(normalized)
                folded = normalized.casefold()
                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if (
                    not normalized
                    or normalized.startswith("/")
                    or (path.parts and ":" in path.parts[0])
                    or ".." in path.parts
                    or folded in seen
                    or info.flag_bits & 0x1
                    or kind not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                ):
                    _reject("document_malformed")
                seen.add(folded)
                names.add(normalized)
                if info.is_dir():
                    continue
                total += info.file_size
                if (
                    total > _MAXIMUM_DECOMPRESSED_BYTES
                    or (
                        info.file_size > 0
                        and (
                            info.compress_size == 0
                            or info.file_size > info.compress_size * _MAXIMUM_COMPRESSION_RATIO
                        )
                    )
                ):
                    _reject("document_limit_exceeded")
                lower = normalized.casefold()
                if (
                    lower.endswith("vbaproject.bin")
                    or "/embeddings/" in f"/{lower}"
                    or lower.endswith(".zip")
                ):
                    _reject("document_malformed")
                capture_xml = lower.endswith((".xml", ".rels"))
                if capture_xml and info.file_size > _MAXIMUM_XML_BYTES:
                    _reject("document_limit_exceeded")
                captured = bytearray()
                with archive.open(info) as member:
                    actual = 0
                    while chunk := member.read(_STREAM_BYTES):
                        actual += len(chunk)
                        if actual > info.file_size:
                            _reject("document_malformed")
                        if capture_xml:
                            captured.extend(chunk)
                    if actual != info.file_size:
                        _reject("document_malformed")
                if capture_xml:
                    value = bytes(captured)
                    root = _parse_xml(value)
                    if lower.endswith(".rels") and any(
                        str(element.attrib.get("TargetMode", "")).strip().casefold()
                        == "external"
                        for element in root.iter()
                    ):
                        _reject("document_malformed")
                    xml_files[normalized] = value
    except ParserDocumentRejected:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError):
        _reject("document_malformed")

    common = {"[Content_Types].xml", "_rels/.rels"}
    docx = common | {"word/document.xml"}
    pptx = common | {"ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"}
    matches = {kind for kind, required in (("docx", docx), ("pptx", pptx)) if required <= names}
    if matches != {expected}:
        _reject("document_malformed" if matches else "document_unsupported")
    return xml_files


def _parse_xml(value: bytes):
    try:
        return ElementTree.fromstring(
            value,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (ElementTree.ParseError, DefusedXmlException, ValueError, UnicodeError):
        _reject("document_malformed")


def _resolve_package_target(owner: str, target: str) -> str:
    if not target or target.startswith(("/", "\\")):
        _reject("document_malformed")
    owner_parent = PurePosixPath(owner).parent
    parts: list[str] = []
    for part in (owner_parent / target.replace("\\", "/")).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                _reject("document_malformed")
            parts.pop()
        elif ":" in part:
            _reject("document_malformed")
        else:
            parts.append(part)
    return "/".join(parts)


def _join_parts(parts: list[tuple[str, str]]) -> _ExtractedDocument:
    text_parts: list[str] = []
    locators: list[_SourceLocator] = []
    position = 0
    for label, value in parts:
        if text_parts:
            text_parts.append("\n\n")
            position += 2
        start = position
        text_parts.append(value)
        position += len(value)
        locators.append(_SourceLocator(label, start, position))
        if position > MAXIMUM_EXTRACTED_CHARACTERS:
            _reject("document_limit_exceeded")
    return _ExtractedDocument("".join(text_parts), tuple(locators))


def _read(
    document: _ExtractedDocument,
    offset: int,
    limit: int,
) -> tuple[str, tuple[GuideTextLocator, ...], int | None]:
    total = len(document.text)
    if offset >= total:
        return "", (), None
    end = min(total, offset + limit)
    intersections = [
        locator
        for locator in document.locators
        if locator.end > offset and locator.start < end
    ]
    if len(intersections) > MAXIMUM_LOCATORS:
        end = max(offset, intersections[MAXIMUM_LOCATORS].start)
        intersections = intersections[:MAXIMUM_LOCATORS]
    text = document.text[offset:end]
    locators = tuple(
        GuideTextLocator(
            label=locator.label,
            start=max(locator.start, offset) - offset,
            end=min(locator.end, end) - offset,
        )
        for locator in intersections
        if min(locator.end, end) > max(locator.start, offset)
    )
    return text, locators, end if end < total else None


def _search(
    document: _ExtractedDocument,
    *,
    query: str,
    offset: int,
    limit: int,
) -> tuple[str, tuple[GuideTextLocator, ...], int | None]:
    if offset >= len(document.text):
        return "", (), None
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = pattern.finditer(document.text, offset)
    output: list[str] = []
    locators: list[GuideTextLocator] = []
    output_length = 0
    next_offset: int | None = None
    returned = 0
    for match in matches:
        if returned >= limit:
            next_offset = match.start()
            break
        source_locator = _locator_for(document.locators, match.start(), match.end())
        excerpt_start = max(source_locator.start, match.start() - _SEARCH_CONTEXT_CHARACTERS)
        excerpt_end = min(source_locator.end, match.end() + _SEARCH_CONTEXT_CHARACTERS)
        excerpt = document.text[excerpt_start:excerpt_end]
        separator = "\n\n" if output else ""
        if output_length + len(separator) + len(excerpt) > MAXIMUM_RESULT_CHARACTERS:
            next_offset = match.start()
            break
        output.append(separator)
        output.append(excerpt)
        start = output_length + len(separator)
        output_length = start + len(excerpt)
        locators.append(
            GuideTextLocator(label=source_locator.label, start=start, end=output_length)
        )
        returned += 1
        next_offset = match.end()
    else:
        next_offset = None
    return "".join(output), tuple(locators), next_offset


def _locator_for(
    locators: tuple[_SourceLocator, ...],
    start: int,
    end: int,
) -> _SourceLocator:
    for locator in locators:
        if locator.end > start and locator.start < end:
            return locator
    return _SourceLocator("document", start, end)


def _reject(reason: GuideDocumentParserRejectionReason) -> NoReturn:
    raise ParserDocumentRejected(reason)


__all__ = ("ParserDocumentRejected", "parse_document")
