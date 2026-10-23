"""Behavior proof for the fixed guide-document parsers and paging rules."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import zipfile
from uuid import uuid4

import pytest
from pypdf import PdfWriter

from app.adapters.guide_document_tools import GuideDocumentParserRequest
from app.adapters.guide_document_tools.parsing import ParserDocumentRejected, parse_document


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _request(
    source: bytes,
    *,
    media_type: str,
    operation: str = "read",
    offset: int = 0,
    limit: int = 65_536,
    query: str | None = None,
) -> GuideDocumentParserRequest:
    return GuideDocumentParserRequest(
        request_id=uuid4(),
        source_sha256=f"sha256:{sha256(source).hexdigest()}",
        source_byte_count=len(source),
        media_type=media_type,
        operation=operation,
        offset=offset,
        limit=limit,
        query=query,
    )


def _archive(entries: list[tuple[str, bytes]], *, compression: int = zipfile.ZIP_STORED) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return output.getvalue()


def _docx(*blocks: str) -> bytes:
    paragraphs = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{value}</w:t></w:r></w:p>'
        for value in blocks
    )
    return _archive(
        [
            ("[Content_Types].xml", b"<Types/>") ,
            ("_rels/.rels", b"<Relationships/>") ,
            (
                "word/document.xml",
                (
                    f'<w:document xmlns:w="http://schemas.openxmlformats.org/'
                    f'wordprocessingml/2006/main"><w:body>{paragraphs}</w:body></w:document>'
                ).encode(),
            ),
        ]
    )


def _pptx(*slides: str) -> bytes:
    slide_ids = "".join(
        f'<p:sldId id="{255 + index}" r:id="rId{index}"/>'
        for index in range(1, len(slides) + 1)
    )
    relationships = "".join(
        f'<Relationship Id="rId{index}" Target="slides/slide{index}.xml"/>'
        for index in range(1, len(slides) + 1)
    )
    entries: list[tuple[str, bytes]] = [
        ("[Content_Types].xml", b"<Types/>"),
        ("_rels/.rels", b"<Relationships/>"),
        (
            "ppt/presentation.xml",
            (
                '<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
                'presentationml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f"<p:sldIdLst>{slide_ids}</p:sldIdLst></p:presentation>"
            ).encode(),
        ),
        (
            "ppt/_rels/presentation.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f"{relationships}</Relationships>"
            ).encode(),
        ),
    ]
    for index, text in enumerate(slides, start=1):
        entries.append(
            (
                f"ppt/slides/slide{index}.xml",
                (
                    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
                    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
                    f"<p:cSld><a:t>{text}</a:t></p:cSld></p:sld>"
                ).encode(),
            )
        )
    return _archive(entries)


def _pdf() -> bytes:
    # A tiny exact PDF makes the extracted text assertion independent of a PDF
    # fixture library while pypdf still performs the production read.
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length 42 >>\nstream\nBT /F1 12 Tf 20 100 Td (PDF Guide) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


@pytest.mark.parametrize(
    ("source", "media_type", "expected_text", "expected_label"),
    [
        ("# Guide\nCafé\n".encode(), "text/markdown", "# Guide\nCafé\n", "line 1"),
        (_docx("First block", "Second block"), DOCX, "First block\n\nSecond block", "block 1"),
        (_pptx("First slide", "Second slide"), PPTX, "First slide\n\nSecond slide", "slide 1"),
        (_pdf(), "application/pdf", "PDF Guide", "page 1"),
    ],
)
def test_supported_formats_return_stable_bounded_text(
    source: bytes,
    media_type: str,
    expected_text: str,
    expected_label: str,
) -> None:
    result = parse_document(_request(source, media_type=media_type), source)

    assert expected_text in result.text
    assert result.locators[0].label == expected_label
    assert result.total_characters == len(result.text)
    assert result.next_offset is None


def test_markdown_paging_preserves_original_text_without_silent_truncation() -> None:
    source = "α first\nβ second\nγ third\n".encode()
    first_request = _request(source, media_type="text/markdown", limit=9)
    first = parse_document(first_request, source)
    assert first.text == source.decode()[:9]
    assert first.next_offset == 9

    second_request = _request(
        source,
        media_type="text/markdown",
        offset=first.next_offset,
        limit=65_536,
    )
    second = parse_document(second_request, source)
    assert first.text + second.text == source.decode()
    assert second.next_offset is None


def test_search_is_literal_case_insensitive_and_paged_by_source_offset() -> None:
    source = b"A.* needle\nregex A.* stays literal\nNEEDLE again\n"
    no_regex = parse_document(
        _request(source, media_type="text/markdown", operation="search", query="A.*", limit=20),
        source,
    )
    assert len(no_regex.locators) == 2

    first = parse_document(
        _request(source, media_type="text/markdown", operation="search", query="needle", limit=1),
        source,
    )
    assert len(first.locators) == 1
    assert first.next_offset is not None
    second = parse_document(
        _request(
            source,
            media_type="text/markdown",
            operation="search",
            query="needle",
            offset=first.next_offset,
            limit=1,
        ),
        source,
    )
    assert len(second.locators) == 1
    assert "NEEDLE" in second.text
    assert second.next_offset is None


@pytest.mark.parametrize(
    "source",
    [
        _archive(
            [
                ("[Content_Types].xml", b"<Types/>"),
                ("_rels/.rels", b"<Relationships/>"),
                ("word/document.xml", b"<w:document/>"),
                ("../escape", b"x"),
            ]
        ),
        _archive(
            [
                ("[Content_Types].xml", b"<Types/>"),
                ("_rels/.rels", b"<Relationships/>"),
                ("word/document.xml", b"<w:document/>"),
                ("WORD/document.xml", b"<w:document/>"),
            ]
        ),
        _archive(
            [
                ("[Content_Types].xml", b"<Types/>"),
                (
                    "_rels/.rels",
                    b'<Relationships><Relationship TargetMode="External"/></Relationships>',
                ),
                ("word/document.xml", b"<w:document/>"),
            ]
        ),
        _archive(
            [
                ("[Content_Types].xml", b"<Types/>"),
                ("_rels/.rels", b"<Relationships/>"),
                (
                    "word/document.xml",
                    b'<!DOCTYPE x [<!ENTITY y "boom">]><x>&y;</x>',
                ),
            ]
        ),
    ],
)
def test_ooxml_rejects_traversal_collisions_entities_and_external_references(
    source: bytes,
) -> None:
    with pytest.raises(ParserDocumentRejected) as rejected:
        parse_document(_request(source, media_type=DOCX), source)

    assert rejected.value.reason == "document_malformed"


def test_ooxml_rejects_compression_bomb_before_extraction() -> None:
    source = _archive(
        [
            ("[Content_Types].xml", b"<Types/>"),
            ("_rels/.rels", b"<Relationships/>"),
            ("word/document.xml", b"<document>" + b"x" * 100_000 + b"</document>"),
        ],
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(ParserDocumentRejected) as rejected:
        parse_document(_request(source, media_type=DOCX), source)
    assert rejected.value.reason == "document_limit_exceeded"


def test_encrypted_and_malformed_pdfs_are_rejected() -> None:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    writer.write(output)
    encrypted = output.getvalue()

    with pytest.raises(ParserDocumentRejected) as encrypted_rejection:
        parse_document(_request(encrypted, media_type="application/pdf"), encrypted)
    assert encrypted_rejection.value.reason == "document_encrypted"

    malformed = b"%PDF-1.7\ntruncated"
    with pytest.raises(ParserDocumentRejected) as malformed_rejection:
        parse_document(_request(malformed, media_type="application/pdf"), malformed)
    assert malformed_rejection.value.reason == "document_malformed"
