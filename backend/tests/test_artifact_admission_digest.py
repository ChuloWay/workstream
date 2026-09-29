"""Producer-scoped request-digest replay through the ART admission owner."""

from dataclasses import replace
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.models import ArtifactPutAttempt
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.artifacts.service import ArtifactAdmissionService
from tests.artifact_store_helpers import artifact_preparation_limits, minted_source
from tests.test_artifact_admission import (
    _AllowGuidePreparedAuthorization,
    _context,
    _guide_admission_request,
    _namespace,
    _seed_guide,
    _settings,
)


async def test_guide_replay_preserves_canonical_producer_digest(
    isolated_database_env: str,
    tmp_path: Path,
) -> None:
    """Guide producer digest shape stays exact through admission and replay."""
    settings = _settings(tmp_path)
    namespace = _namespace(settings)
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            context = _context()
            scratch_limits = replace(
                artifact_preparation_limits(),
                reservation_ttl_seconds=360,
                total_deadline_seconds=300,
            )
            async with minted_source(
                tmp_path / "guide-digest",
                b"retained guide bytes",
                media_type="application/pdf",
                limits=scratch_limits,
            ) as source:
                project_id, item_id = await _seed_guide(
                    session,
                    context=context,
                    content_hash="sha256:" + "f" * 64,
                    media_type=source.commitment.media_type,
                )
                lineage = await ArtifactRepository(session).get_guide_lineage(item_id)
                assert lineage is not None
                await session.rollback()
                request = _guide_admission_request(item_id, source, lineage=lineage)
                first_authority = _AllowGuidePreparedAuthorization(
                    context.actor_profile_id
                )
                first = await ArtifactAdmissionService(
                    session, settings, namespace
                ).admit(
                    request,
                    guide_prepared_authorization=first_authority,  # type: ignore[arg-type]
                    prepared_authorization=first_authority.handle,
                )
                assert first.replayed is False

                canonical_guide_digest = canonical_json_hash(
                    {
                        "operation_identity": request.operation_identity,
                        "guide_ingest_request_digest": request.request_digest,
                        "request_type": "guide",
                        "producer_type": "actor_profile",
                        "producer_ref": str(context.actor_profile_id),
                        "project_id": project_id,
                        "task_id": None,
                        "guide_source_item_id": item_id,
                        "checker_run_id": None,
                        "logical_role": None,
                        "pre_submit_evidence_set_id": None,
                        "sha256": source.commitment.sha256,
                        "byte_count": source.commitment.byte_count,
                        "media_type": source.commitment.media_type,
                        "namespace_fingerprint": namespace.namespace_fingerprint,
                        "scopes": [
                            {
                                "scope_type": "deployment",
                                "scope_id": "primary",
                                "limit_bytes": settings.artifact_admission_deployment_maximum_bytes,
                            },
                            {
                                "scope_type": "producer",
                                "scope_id": f"actor_profile:{context.actor_profile_id}",
                                "limit_bytes": settings.artifact_admission_producer_maximum_bytes,
                            },
                            {
                                "scope_type": "project",
                                "scope_id": project_id,
                                "limit_bytes": settings.artifact_admission_project_maximum_bytes,
                            },
                        ],
                    }
                )
                attempt = await session.get(ArtifactPutAttempt, str(first.attempt_id))
                assert attempt is not None
                assert first.request_digest == canonical_guide_digest
                await session.rollback()

                replay_authority = _AllowGuidePreparedAuthorization(
                    context.actor_profile_id
                )
                replay = await ArtifactAdmissionService(
                    session, settings, namespace
                ).admit(
                    request,
                    guide_prepared_authorization=replay_authority,  # type: ignore[arg-type]
                    prepared_authorization=replay_authority.handle,
                )
                assert replay.replayed is True
                assert replay.attempt_id == first.attempt_id
                assert replay.request_digest == canonical_guide_digest
                assert await session.scalar(
                    select(func.count()).select_from(ArtifactPutAttempt)
                ) == 1
    finally:
        await engine.dispose()
