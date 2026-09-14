"""Real AUTH custody across the three POL-07A materialization transactions."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service_identities import ServiceIdentity
from app.modules.artifacts.authorization import PreparedPreSubmitMaterializationAuthorization
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.submission_materialization import PreSubmitMaterializationAuthorityFacts
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.models import AuthorityIdempotencyRecord
from app.modules.tasks.models import AuditEvent


def _facts() -> PreSubmitMaterializationAuthorityFacts:
    return PreSubmitMaterializationAuthorityFacts(
        task_id=uuid4(), assignment_id=uuid4(), project_id=uuid4(), guide_id=uuid4(),
        guide_version="1", source_snapshot_id=uuid4(),
        source_snapshot_hash="sha256:" + "1" * 64,
        submission_artifact_policy_id=uuid4(),
        submission_artifact_policy_hash="sha256:" + "2" * 64,
        checker_policy_id=uuid4(), checker_policy_hash="sha256:" + "3" * 64,
        prepared_generation_id=uuid4(), plan_sha256="sha256:" + "4" * 64,
        catalogue_manifest_sha256="sha256:" + "5" * 64,
        archive_sha256="sha256:" + "6" * 64, archive_byte_count=10,
        storage_scheme="s3", semantic_manifest_sha256="sha256:" + "7" * 64,
    )


async def _seed_materializer(factory: async_sessionmaker) -> str:
    actor_id, link_id = str(uuid4()), str(uuid4())
    async with factory.begin() as session:
        session.add(ActorProfile(
            id=actor_id, actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.ARTIFACT_MATERIALIZER.value,
            created_by="pre-submit-authority-test",
        ))
        session.add(ActorIdentityLink(
            id=link_id, actor_profile_id=actor_id,
            issuer="https://issuer.example.test", subject=f"materializer-{actor_id}",
            subject_kind="service", status="active", linked_by="pre-submit-authority-test",
        ))
    return link_id


async def _consume(session, authority, facts, key, *, reject_wrong_generation=False):
    async with session.begin():
        handle = await authority.prepare(facts=facts.preparation, idempotency_key=key)
        if reject_wrong_generation:
            with pytest.raises(ArtifactAuthorityDeniedError, match="invalid"):
                await authority.consume(
                    prepared_authorization=handle,
                    facts=replace(facts, prepared_generation_id=uuid4()),
                )
        await authority.consume(prepared_authorization=handle, facts=facts)
    return handle


async def _revoke(factory: async_sessionmaker, link_id: str) -> None:
    async with factory.begin() as session:
        await session.execute(
            update(ActorIdentityLink)
            .where(ActorIdentityLink.id == link_id)
            .values(status="revoked", revoked_by="pre-submit-authority-test",
                    revoked_at=datetime.now(UTC),
                    revoked_reason="authority revoked")
        )


async def test_real_materializer_consumes_inspection_execution_and_original_replay_authority(
    clean_postgres_database: str,
) -> None:
    """One ART key authorizes three fresh AUTH consumes and three distinct audit events."""
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _seed_materializer(factory)
        original = _facts()
        key, request_id = uuid4(), uuid4()

        async with factory() as session:
            authority = PreparedPreSubmitMaterializationAuthorization(
                session, request_id=request_id, correlation_id=uuid4(),
            )
            try:
                inspected_handle = await _consume(
                    session, authority, original, key, reject_wrong_generation=True,
                )
                execution_handle = await _consume(session, authority, original, key)
                retry = replace(original, prepared_generation_id=uuid4())
                assert retry.prepared_generation_id != original.prepared_generation_id
                replay_handle = await _consume(
                    session, authority,
                    replace(retry, prepared_generation_id=original.prepared_generation_id), key,
                )
            finally:
                authority.close()
        assert len({id(inspected_handle), id(execution_handle), id(replay_handle)}) == 3

        async with factory() as session:
            events = (await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action_id == ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE.value
                )
            )).all()
            assert len(events) == 3
            assert all(event.event_type == "SensitiveAuthorizationAllowed" for event in events)
            # This fixed-service read authority audits every consume; ART owns
            # durable idempotency, so AUTH has no mutation reservation for key.
            assert all(event.idempotency_reference is None for event in events)
            assert all(event.resource_id == str(original.prepared_generation_id) for event in events)
            assert len({event.id for event in events}) == 3
            assert (await session.scalars(select(AuthorityIdempotencyRecord))).all() == []
    finally:
        await engine.dispose()


@pytest.mark.parametrize("completed_consumes", (1, 2))
async def test_real_materializer_revocation_denies_next_phase_or_completed_replay(
    clean_postgres_database: str, completed_consumes: int,
) -> None:
    """A committed earlier audit never carries authority past a revoked service link."""
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        link_id = await _seed_materializer(factory)
        facts, key, request_id = _facts(), uuid4(), uuid4()
        async with factory() as session:
            authority = PreparedPreSubmitMaterializationAuthorization(
                session, request_id=request_id, correlation_id=uuid4(),
            )
            try:
                for _ in range(completed_consumes):
                    await _consume(session, authority, facts, key)
                await _revoke(factory, link_id)
                async with session.begin():
                    with pytest.raises(ArtifactAuthorityDeniedError):
                        await authority.prepare(facts=facts.preparation, idempotency_key=key)
            finally:
                authority.close()
        async with factory() as session:
            events = (await session.scalars(select(AuditEvent).where(
                AuditEvent.action_id == ActionId.ARTIFACT_PRE_SUBMIT_CHECKER_INPUT_MATERIALIZE.value
            ))).all()
            assert len([event for event in events if event.event_type == "SensitiveAuthorizationAllowed"]) == completed_consumes
    finally:
        await engine.dispose()
