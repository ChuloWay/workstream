"""Retained provider cleanup remains exact-ID only after inference cutover."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert, select, text, update

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.projects.guide_compilation.models import (
    ProjectGuideCompilationAttempt,
    ProjectGuideRuntimeAllocation,
)
from app.modules.projects.guide_compilation.runtime_resources import (
    RetainedGuideRuntimeCleanupCandidate,
    SqlAlchemyGuideRuntimeCleanupCustody,
    pending_runtime_resource_cleanup,
)
from .helpers import runtime_configuration
from .test_document_access_postgresql import grant_case as grant_case

RETAINED_RUNTIME = "openai_agents_sdk"


def _historical_configuration():
    current = runtime_configuration()
    return {
        "capability_key": current.capability_key,
        "runtime_key": RETAINED_RUNTIME,
        "model_provider": "openai",
        "model": "gpt-5.6-terra",
        "model_api": "responses",
        "instruction_id": current.instruction_id,
        "instruction_version": current.instruction_version,
        "instructions": current.instructions,
        "instructions_sha256": current.instructions_sha256,
        "timeout_seconds": 30,
        "request_timeout_seconds": 30,
        "maximum_retries": 2,
        "retry_backoff_multiplier": 2,
        "retry_jitter": True,
        "retry_initial_delay_seconds": 1,
        "retry_max_delay_seconds": 30,
        "circuit_failure_threshold": 3,
        "circuit_cooldown_seconds": 60,
        "maximum_manifest_bytes": current.maximum_manifest_bytes,
        "maximum_documents": current.maximum_documents,
        "maximum_document_bytes": current.maximum_document_bytes,
        "maximum_total_document_bytes": current.maximum_total_document_bytes,
        "maximum_turns": current.maximum_turns,
        "maximum_hosted_tool_calls": 80,
        "compaction_threshold_tokens": 32_000,
        "container_expiry_minutes": 20,
        "file_expiry_seconds": 3600,
        "cleanup_timeout_seconds": 30,
    }


async def seed_retained_allocation_history(grant, context, *, include_unknown=False):
    """Insert predecessor facts with triggers bypassed only in this isolated fixture."""
    document = context.material.documents[0]
    handle = UUID(context.material.handle_for(document))
    container_id, file_id, attachment_id = new_record_id(), new_record_id(), new_record_id()
    old = datetime.now(UTC) - timedelta(minutes=5)
    expiry = old + timedelta(minutes=20)
    base = {
        "attempt_id": grant._attempt_id,
        "manifest_sha256": context.material.sha256,
        "runtime_key": RETAINED_RUNTIME,
        "state": "allocated",
        "created_at": old,
        "expires_at": expiry,
    }
    rows = [
        base
        | {
            "id": container_id,
            "kind": "container",
            "provider_id": "cntr_retained",
        },
        base
        | {
            "id": file_id,
            "kind": "file",
            "provider_id": "file-retained",
            "document_handle": handle,
            "source_item_id": str(document.source_item_id),
            "document_version_id": str(document.ingest_id),
            "put_attempt_id": str(document.put_attempt_id),
            "content_id": str(document.content_id),
            "replica_id": str(document.replica_id),
            "storage_namespace_id": document.storage_namespace_id,
            "namespace_fingerprint": document.namespace_fingerprint,
            "sha256": document.sha256,
            "byte_count": document.byte_count,
            "media_type": document.media_type,
        },
        base
        | {
            "id": attachment_id,
            "kind": "attachment",
            "provider_id": "cfile_retained",
            "document_handle": handle,
            "parent_provider_id": "cntr_retained",
            "container_allocation_id": container_id,
            "source_file_allocation_id": file_id,
        },
    ]
    unknown_id = None
    if include_unknown:
        unknown_id = new_record_id()
        rows.append(
            base
            | {
                "id": unknown_id,
                "kind": "container",
                "state": "uncertain",
                "provider_id": "cntr_unconfirmed",
            }
        )
    historical = _historical_configuration()
    async with grant._sessions() as session, session.begin():
        await session.execute(text("SET LOCAL session_replication_role=replica"))
        await session.execute(
            update(ProjectGuideCompilationAttempt)
            .where(ProjectGuideCompilationAttempt.id == grant._attempt_id)
            .values(
                runtime_configuration=historical,
                runtime_configuration_hash=canonical_json_hash(historical),
            )
        )
        await session.execute(insert(ProjectGuideRuntimeAllocation), rows)
    return {container_id, file_id, attachment_id}, unknown_id


async def persisted_states(grant):
    async with grant._sessions() as session:
        rows = (
            await session.execute(
                select(
                    ProjectGuideRuntimeAllocation.id,
                    ProjectGuideRuntimeAllocation.state,
                    ProjectGuideRuntimeAllocation.deleted_at,
                ).where(ProjectGuideRuntimeAllocation.attempt_id == grant._attempt_id)
            )
        ).all()
    return {row.id: (row.state, row.deleted_at) for row in rows}


async def test_retained_cleanup_selection_preserves_old_config_and_exact_ids(grant_case):
    grant, _store, _authority, _manager, context = grant_case
    identifiers, _ = await seed_retained_allocation_history(grant, context)
    async with grant._sessions() as session:
        selected = await pending_runtime_resource_cleanup(
            session, retained_runtime_key=RETAINED_RUNTIME
        )
    assert selected == (
        RetainedGuideRuntimeCleanupCandidate(
            grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
        ),
    )
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions, grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
    )
    resources = await custody.cleanup_resources()
    assert {item.allocation_id for item in resources} == identifiers
    assert {item.provider_id for item in resources} == {
        "cntr_retained",
        "file-retained",
        "cfile_retained",
    }


async def test_cleanup_failure_replay_and_deletion_are_monotonic(grant_case):
    grant, _store, _authority, _manager, context = grant_case
    identifiers, _ = await seed_retained_allocation_history(grant, context)
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions, grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
    )
    for identifier in identifiers:
        await custody.record_cleanup_failed(identifier)
    assert {state for state, _ in (await persisted_states(grant)).values()} == {"cleanup_failed"}
    for identifier in identifiers:
        await custody.record_deleted(identifier)
    before = await persisted_states(grant)
    assert all(state == "deleted" and timestamp is not None for state, timestamp in before.values())
    for identifier in identifiers:
        await custody.record_deleted(identifier)
        await custody.record_cleanup_failed(identifier)
    assert await persisted_states(grant) == before
    assert await custody.cleanup_resources() == ()


@pytest.mark.parametrize("field", ["attempt", "manifest", "runtime"])
async def test_cleanup_rejects_cross_scope_substitution(grant_case, field):
    grant, _store, _authority, _manager, context = grant_case
    identifiers, _ = await seed_retained_allocation_history(grant, context)
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions,
        uuid4() if field == "attempt" else grant._attempt_id,
        "sha256:" + "f" * 64 if field == "manifest" else context.material.sha256,
        "foreign_runtime" if field == "runtime" else RETAINED_RUNTIME,
    )
    before = await persisted_states(grant)
    with pytest.raises(RuntimeError, match="cleanup scope is unavailable"):
        await custody.cleanup_resources()
    with pytest.raises(RuntimeError, match="cleanup scope is unavailable"):
        await custody.record_deleted(next(iter(identifiers)))
    assert await persisted_states(grant) == before


async def test_unknown_allocation_cannot_be_confirmed_or_selected(grant_case):
    grant, _store, _authority, _manager, context = grant_case
    identifiers, unknown = await seed_retained_allocation_history(
        grant, context, include_unknown=True
    )
    custody = SqlAlchemyGuideRuntimeCleanupCustody(
        grant._sessions, grant._attempt_id, context.material.sha256, RETAINED_RUNTIME
    )
    assert {item.allocation_id for item in await custody.cleanup_resources()} == identifiers
    with pytest.raises(ValueError, match="unknown resource deletion cannot be confirmed"):
        await custody.record_deleted(unknown)
    await custody.record_cleanup_failed(unknown)
    assert (await persisted_states(grant))[unknown] == ("uncertain", None)


async def test_current_provider_selection_cannot_redirect_retained_cleanup(grant_case):
    grant, _store, _authority, _manager, context = grant_case
    await seed_retained_allocation_history(grant, context)
    async with grant._sessions() as session:
        assert (
            await pending_runtime_resource_cleanup(session, retained_runtime_key="another_runtime")
            == ()
        )
        assert (
            len(
                await pending_runtime_resource_cleanup(
                    session, retained_runtime_key=RETAINED_RUNTIME
                )
            )
            == 1
        )


@pytest.mark.parametrize("fail", [False, True])
async def test_cleanup_composition_uses_only_fixed_cleanup_callable(grant_case, fail):
    from app.adapters.projects import cleanup_project_guide_runtime_resources

    grant, _store, _authority, _manager, context = grant_case
    identifiers, _ = await seed_retained_allocation_history(grant, context)
    calls = []

    async def cleanup(custody):
        rows = await custody.cleanup_resources()
        calls.append({row.allocation_id for row in rows})
        if fail:
            raise RuntimeError("provider unavailable")
        for row in rows:
            await custody.record_deleted(row.allocation_id)
        return True

    result = await cleanup_project_guide_runtime_resources(
        grant._sessions,
        retained_runtime_key=RETAINED_RUNTIME,
        cleanup_resources=cleanup,
    )
    assert result == {"selected": 1, "completed": int(not fail)}
    assert calls == [identifiers]
    if fail:
        assert {state for state, _ in (await persisted_states(grant)).values()} == {"allocated"}
