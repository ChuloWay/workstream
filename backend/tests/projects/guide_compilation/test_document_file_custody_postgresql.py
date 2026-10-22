"""Direct PostgreSQL proof of original -> provider file -> attachment -> access custody."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, text, update
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.projects.api.guide_documents import guide_document_handle
from app.modules.projects.guide_compilation.models import ProjectGuideRuntimeAllocation, ProjectGuideDocumentAccess
from app.modules.projects.guide_compilation.runtime_resources import SqlAlchemyGuideRuntimeCustody
from .helpers import runtime_configuration
from .test_document_access_postgresql import grant_case as grant_case


def file_intent(grant, context):
    """Specify the persisted original independently of the service's mapping helper."""
    doc = context.material.documents[0]
    return dict(id=new_record_id(), attempt_id=grant._attempt_id, manifest_sha256=context.material.sha256,
                runtime_key=runtime_configuration().runtime_key, kind="file", state="allocating",
                document_handle=UUID(context.material.handle_for(doc)), source_item_id=str(doc.source_item_id),
                document_version_id=str(doc.ingest_id), put_attempt_id=str(doc.put_attempt_id),
                content_id=str(doc.content_id), replica_id=str(doc.replica_id),
                storage_namespace_id=doc.storage_namespace_id, namespace_fingerprint=doc.namespace_fingerprint,
                sha256=doc.sha256, byte_count=doc.byte_count, media_type=doc.media_type,
                expires_at=datetime.now(timezone.utc)+timedelta(minutes=20))


async def assert_insert_rejected_after_valid_control(session, table, valid, mutant, message):
    """The exact valid shape succeeds; omit/change only the boundary being tested."""
    control = await session.begin_nested()
    await session.execute(insert(table).values(**valid))
    await control.rollback()
    rejected = await session.begin_nested()
    with pytest.raises(DBAPIError, match=message) as error:
        await session.execute(insert(table).values(**mutant))
    assert error.value.orig.sqlstate == "23514"
    await rejected.rollback()


@pytest.mark.parametrize("field", ["document_handle", "source_item_id", "document_version_id",
    "put_attempt_id", "content_id", "replica_id", "storage_namespace_id", "namespace_fingerprint",
    "sha256", "byte_count", "media_type", "manifest_sha256", "attempt_id"])
async def test_file_intent_rejects_each_independent_original_identity(grant_case, field):
    grant, _, _, _, context = grant_case
    valid = file_intent(grant, context)
    changes = {"document_handle": uuid4(), "source_item_id": str(uuid4()),
               "document_version_id": str(uuid4()), "put_attempt_id": str(uuid4()),
               "content_id": str(uuid4()), "replica_id": str(uuid4()), "storage_namespace_id": "foreign",
               "namespace_fingerprint": "sha256:"+"b"*64, "sha256": "sha256:"+"b"*64,
               "byte_count": valid["byte_count"]+1, "media_type": "application/zip",
               "manifest_sha256": "sha256:"+"b"*64, "attempt_id": uuid4()}
    mutant = valid | {field: changes[field]}
    if field in ("source_item_id", "document_version_id"):
        mutant["document_handle"] = guide_document_handle(context.material.setup_run_id,
            UUID(mutant["source_item_id"]), UUID(mutant["document_version_id"]))
    message = ("canonical handle mismatch" if field == "document_handle" else
               "allocation scope mismatch" if field in ("manifest_sha256", "attempt_id") else
               "file source lineage mismatch")
    async with grant._sessions() as session, session.begin():
        await assert_insert_rejected_after_valid_control(session, ProjectGuideRuntimeAllocation.__table__, valid, mutant, message)


async def allocated_parents(grant, context):
    custody = SqlAlchemyGuideRuntimeCustody(grant._sessions, grant._attempt_id,
        context.material, runtime_configuration().runtime_key)
    expiry = datetime.now(timezone.utc)+timedelta(minutes=20)
    container = await custody.begin_allocation(kind="container", document_handle=None,
        parent_provider_id=None, expires_at=expiry)
    await custody.record_allocated(container, "cntr_test")
    file = await custody.begin_allocation(kind="file", document_handle=context.material.handle_for(context.material.documents[0]),
        parent_provider_id=None, expires_at=expiry)
    await custody.record_allocated(file, "file-test")
    return custody, container, file


def attachment_intent(grant, context, container, file):
    return dict(id=new_record_id(), attempt_id=grant._attempt_id, manifest_sha256=context.material.sha256,
        runtime_key=runtime_configuration().runtime_key, kind="attachment", state="allocating",
        document_handle=UUID(context.material.handle_for(context.material.documents[0])),
        parent_provider_id="cntr_test", container_allocation_id=container, source_file_allocation_id=file,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=20))


@pytest.mark.parametrize("field", ["source_file_allocation_id", "container_allocation_id", "document_handle", "parent_provider_id"])
async def test_attachment_requires_its_exact_file_and_container(grant_case, field):
    grant, _, _, _, context = grant_case
    _, container, file = await allocated_parents(grant, context)
    valid = attachment_intent(grant, context, container, file)
    value = "cntr_foreign" if field == "parent_provider_id" else uuid4()
    async with grant._sessions() as session, session.begin():
        await assert_insert_rejected_after_valid_control(session, ProjectGuideRuntimeAllocation.__table__,
            valid, valid | {field: value}, "attachment parent mismatch")


@pytest.mark.parametrize("field", ["attachment_allocation_id", "source_item_id", "document_version_id", "sha256", "document_handle"])
async def test_access_requires_the_exact_attachment_original(grant_case, field):
    grant, _, _, _, context = grant_case
    custody, container, file = await allocated_parents(grant, context)
    attachment = attachment_intent(grant, context, container, file)
    async with grant._sessions() as session, session.begin():
        await session.execute(insert(ProjectGuideRuntimeAllocation).values(**attachment))
    await custody.record_allocated(attachment["id"], "cfile_test")
    doc = context.material.documents[0]
    valid = dict(id=new_record_id(), attempt_id=grant._attempt_id, attachment_allocation_id=attachment["id"],
        source_item_id=str(doc.source_item_id), document_version_id=str(doc.ingest_id), sha256=doc.sha256,
        manifest_sha256=context.material.sha256, document_handle=attachment["document_handle"])
    value = ("sha256:"+"b"*64 if field == "sha256" else
             str(uuid4()) if field in ("source_item_id", "document_version_id") else uuid4())
    async with grant._sessions() as session, session.begin():
        await assert_insert_rejected_after_valid_control(session, ProjectGuideDocumentAccess.__table__,
            valid, valid | {field: value}, "access lineage is invalid")


async def test_canonical_handle_python_sql_parity_and_removed_guard_probe(grant_case):
    grant, _, _, _, context = grant_case
    valid = file_intent(grant, context)
    mutant = valid | {"document_handle": uuid4()}
    async with grant._sessions() as session, session.begin():
        for run, source, ingest in [(context.material.setup_run_id, UUID(valid["source_item_id"]), UUID(valid["document_version_id"])),
                                   (UUID(int=1), UUID(int=2), UUID(int=3))]:
            actual = await session.scalar(text("select canonical_guide_document_handle(:run,:source,:ingest)"),
                                          dict(run=run, source=source, ingest=ingest))
            assert actual == guide_document_handle(run, source, ingest)
        await assert_insert_rejected_after_valid_control(session, ProjectGuideRuntimeAllocation.__table__,
            valid, mutant, "canonical handle mismatch")
        savepoint = await session.begin_nested()
        definition = await session.scalar(text("select pg_get_functiondef('guard_guide_runtime_allocation()'::regprocedure)"))
        start = definition.index('            if new.document_handle is distinct from canonical_guide_document_handle(')
        end = definition.index('            end if;', start) + len('            end if;')
        await session.execute(text(definition[:start]+definition[end:]))
        await session.execute(insert(ProjectGuideRuntimeAllocation).values(**mutant))
        await savepoint.rollback()


async def test_original_file_mapping_is_immutable_after_provider_receipt(grant_case):
    grant, _, _, _, context = grant_case
    _, _, file = await allocated_parents(grant, context)
    async with grant._sessions() as session, session.begin():
        savepoint = await session.begin_nested()
        with pytest.raises(DBAPIError, match="allocation evidence is immutable"):
            await session.execute(update(ProjectGuideRuntimeAllocation).where(ProjectGuideRuntimeAllocation.id == file)
                                  .values(replica_id=str(uuid4())))
        await savepoint.rollback()
        assert (await session.get(ProjectGuideRuntimeAllocation, file)).replica_id == str(context.material.documents[0].replica_id)


@pytest.fixture
async def manager_attempt(clean_postgres_database):
    """A fenced manager-authored attempt; it records reads but owns no provider resources."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from .helpers import context, manager_runtime_configuration, seed_database
    from .test_hidden_orchestrator_postgresql import _authorized_attempt, _backend

    values = await seed_database(clean_postgres_database)
    configuration = manager_runtime_configuration()
    request = await _authorized_attempt(clean_postgres_database, values, configuration)
    engine = create_async_engine(clean_postgres_database)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    backend = _backend(sessions)
    assert (await backend.fence(await backend.load(request.attempt_id))).dispatch_permitted
    compilation = context(values, configuration=configuration)
    custody = SqlAlchemyGuideRuntimeCustody(sessions, request.attempt_id, compilation.material,
                                            configuration.runtime_key)
    try:
        yield sessions, request.attempt_id, compilation, custody
    finally:
        await engine.dispose()


def _direct_access(attempt_id, compilation):
    doc = compilation.material.documents[0]
    return dict(id=new_record_id(), attempt_id=attempt_id, attachment_allocation_id=None,
                source_item_id=str(doc.source_item_id), document_version_id=str(doc.ingest_id),
                sha256=doc.sha256, manifest_sha256=compilation.material.sha256,
                document_handle=UUID(compilation.material.handle_for(doc)))


async def test_manager_authored_read_is_recorded_without_any_provider_resource(manager_attempt):
    sessions, attempt_id, compilation, custody = manager_attempt
    handle = compilation.material.handle_for(compilation.material.documents[0])
    expiry = datetime.now(timezone.utc) + timedelta(minutes=20)
    for kind, document_handle in (("container", None), ("file", handle)):
        with pytest.raises(RuntimeError, match="custody is unavailable"):
            await custody.begin_allocation(kind=kind, document_handle=document_handle,
                                           parent_provider_id=None, expires_at=expiry)
    with pytest.raises(RuntimeError, match="custody is unavailable"):
        await custody.record_document_open(handle)
    await custody.record_direct_document_open(handle)
    assert await custody.opened_handles() == {handle}
    assert await custody.cleanup_resources() == ()
    async with sessions() as session:
        rows = (await session.execute(text(
            "select attachment_allocation_id from project_guide_document_accesses "
            "where attempt_id=:id"), {"id": attempt_id})).all()
        assert rows == [(None,)]
        assert await session.scalar(text(
            "select count(*) from project_guide_runtime_allocations where attempt_id=:id"),
            {"id": attempt_id}) == 0


async def test_manager_authored_read_is_recorded_once_across_a_retry(manager_attempt):
    """A retried provider-free run rereads documents the failed run already recorded."""
    sessions, attempt_id, compilation, custody = manager_attempt
    handle = compilation.material.handle_for(compilation.material.documents[0])
    await custody.record_direct_document_open(handle)
    await custody.record_direct_document_open(handle)
    async with sessions() as session:
        assert await session.scalar(text(
            "select count(*) from project_guide_document_accesses where attempt_id=:id"),
            {"id": attempt_id}) == 1


async def test_sql_refuses_provider_resources_for_a_manager_authored_attempt(manager_attempt):
    sessions, attempt_id, compilation, _custody = manager_attempt
    async with sessions() as session, session.begin():
        with pytest.raises(DBAPIError, match="allocates no provider resources") as error:
            await session.execute(insert(ProjectGuideRuntimeAllocation).values(
                id=new_record_id(), attempt_id=attempt_id, manifest_sha256=compilation.material.sha256,
                runtime_key="manager_authored", kind="container", state="allocating",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=20)))
        assert error.value.orig.sqlstate == "23514"


@pytest.mark.parametrize("field", ["source_item_id", "document_version_id", "sha256", "document_handle"])
async def test_sql_direct_read_requires_the_exact_assigned_original(manager_attempt, field):
    sessions, attempt_id, compilation, _custody = manager_attempt
    valid = _direct_access(attempt_id, compilation)
    value = ("sha256:" + "b" * 64 if field == "sha256" else
             str(uuid4()) if field in ("source_item_id", "document_version_id") else uuid4())
    mutant = valid | {field: value}
    if field in ("source_item_id", "document_version_id"):
        # Keep the handle canonical so only the snapshot/ingest lineage can reject.
        mutant["document_handle"] = guide_document_handle(compilation.material.setup_run_id,
            UUID(mutant["source_item_id"]), UUID(mutant["document_version_id"]))
    async with sessions() as session, session.begin():
        await assert_insert_rejected_after_valid_control(
            session, ProjectGuideDocumentAccess.__table__, valid, mutant, "access lineage is invalid")


async def test_hosted_runtime_cannot_record_a_read_without_provider_staging(grant_case):
    grant, _, _, _, context = grant_case
    custody = SqlAlchemyGuideRuntimeCustody(grant._sessions, grant._attempt_id,
        context.material, runtime_configuration().runtime_key)
    handle = context.material.handle_for(context.material.documents[0])
    with pytest.raises(RuntimeError, match="custody is unavailable"):
        await custody.record_direct_document_open(handle)
    async with grant._sessions() as session, session.begin():
        with pytest.raises(DBAPIError, match="access lineage is invalid") as error:
            await session.execute(insert(ProjectGuideDocumentAccess).values(
                **_direct_access(grant._attempt_id, context)))
        assert error.value.orig.sqlstate == "23514"
    assert await custody.opened_handles() == set()
