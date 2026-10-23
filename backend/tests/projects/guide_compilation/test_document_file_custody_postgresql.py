"""PostgreSQL proof for neutral parser receipts and removed allocation writes."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.projects.api.guide_documents import GuideDocumentAccessReceipt
from app.modules.projects.guide_compilation.models import (
    ProjectGuideDocumentAccess,
    ProjectGuideRuntimeAllocation,
)
from app.modules.projects.guide_compilation.runtime_resources import (
    SqlAlchemyGuideDocumentAccessCustody,
)
from .helpers import runtime_configuration
from .test_document_access_postgresql import grant_case as grant_case

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def access_receipt(context, **changes):
    document = context.material.documents[0]
    values = {
        "handle": context.material.handle_for(document),
        "source_item_id": document.source_item_id,
        "document_version_id": document.ingest_id,
        "sha256": document.sha256,
        "operation": "read",
        "parser_request_hash": HASH_A,
        "parser_response_hash": HASH_B,
        "parser_build_digest": "sha256:" + "c" * 64,
    }
    values.update(changes)
    return GuideDocumentAccessReceipt(**values)


def access_row(grant, context, **changes):
    receipt = access_receipt(context)
    values = {
        "id": new_record_id(),
        "attempt_id": grant._attempt_id,
        "source_item_id": str(receipt.source_item_id),
        "document_version_id": str(receipt.document_version_id),
        "attachment_allocation_id": None,
        "access_method": "trusted_parser",
        "operation": receipt.operation,
        "parser_request_hash": receipt.parser_request_hash,
        "parser_response_hash": receipt.parser_response_hash,
        "parser_build_digest": receipt.parser_build_digest,
        "manifest_sha256": context.material.sha256,
        "sha256": receipt.sha256,
        "document_handle": UUID(receipt.handle),
    }
    values.update(changes)
    return values


@pytest.mark.parametrize(
    "field,value",
    [
        ("handle", str(uuid4())),
        ("source_item_id", uuid4()),
        ("document_version_id", uuid4()),
        ("sha256", HASH_B),
        ("parser_request_hash", "sha256:bad"),
        ("parser_response_hash", "sha256:bad"),
        ("parser_build_digest", "sha256:bad"),
    ],
)
async def test_access_custody_rejects_cross_source_or_invalid_parser_receipt(
    grant_case, field, value
):
    grant, _store, _authority, _manager, context = grant_case
    custody = SqlAlchemyGuideDocumentAccessCustody(
        grant._sessions,
        grant._attempt_id,
        context.material,
        runtime_configuration().runtime_key,
    )
    with pytest.raises(ValueError, match="receipt is invalid"):
        await custody.record_success(access_receipt(context, **{field: value}))
    assert await custody.opened_handles() == set()


async def test_exact_parser_receipt_is_idempotent_and_conflicts_are_rejected(grant_case):
    grant, _store, _authority, _manager, context = grant_case
    custody = SqlAlchemyGuideDocumentAccessCustody(
        grant._sessions,
        grant._attempt_id,
        context.material,
        runtime_configuration().runtime_key,
    )
    receipt = access_receipt(context)
    await custody.record_success(receipt)
    await custody.record_success(receipt)
    assert await custody.opened_handles() == {receipt.handle}
    async with grant._sessions() as session:
        rows = list(
            await session.scalars(
                select(ProjectGuideDocumentAccess).where(
                    ProjectGuideDocumentAccess.attempt_id == grant._attempt_id
                )
            )
        )
    assert len(rows) == 1
    assert rows[0].access_method == "trusted_parser"
    assert rows[0].attachment_allocation_id is None


@pytest.mark.parametrize(
    "changes",
    [
        {
            "access_method": "direct_original",
            "operation": None,
            "parser_request_hash": None,
            "parser_response_hash": None,
            "parser_build_digest": None,
        },
        {"access_method": "provider_attachment"},
        {"source_item_id": str(uuid4())},
        {"document_version_id": str(uuid4())},
        {"sha256": HASH_B},
        {"document_handle": uuid4()},
        {"operation": None},
        {"parser_request_hash": None},
        {"parser_response_hash": None},
        {"parser_build_digest": None},
    ],
)
async def test_sql_accepts_only_exact_trusted_parser_access(grant_case, changes):
    grant, _store, _authority, _manager, context = grant_case
    async with grant._sessions() as session, session.begin():
        with pytest.raises(DBAPIError, match="access lineage is invalid") as error:
            await session.execute(
                insert(ProjectGuideDocumentAccess).values(**access_row(grant, context, **changes))
            )
        assert error.value.orig.sqlstate == "23514"


async def test_sql_accepts_complete_exact_trusted_parser_access(grant_case):
    grant, _store, _authority, _manager, context = grant_case
    row = access_row(grant, context)
    async with grant._sessions() as session, session.begin():
        await session.execute(insert(ProjectGuideDocumentAccess).values(**row))
    async with grant._sessions() as session:
        stored = await session.get(ProjectGuideDocumentAccess, row["id"])
    assert stored is not None
    assert stored.operation == "read"
    assert stored.parser_request_hash == HASH_A
    assert stored.parser_response_hash == HASH_B
    assert stored.parser_build_digest == "sha256:" + "c" * 64


async def test_new_provider_allocation_path_is_closed(grant_case):
    grant, _store, _authority, _manager, context = grant_case
    async with grant._sessions() as session, session.begin():
        with pytest.raises(DBAPIError, match="allocation path is removed") as error:
            await session.execute(
                insert(ProjectGuideRuntimeAllocation).values(
                    id=new_record_id(),
                    attempt_id=grant._attempt_id,
                    manifest_sha256=context.material.sha256,
                    runtime_key=runtime_configuration().runtime_key,
                    kind="container",
                    state="allocating",
                    expires_at=datetime.now(UTC) + timedelta(minutes=20),
                )
            )
        assert error.value.orig.sqlstate == "23514"
