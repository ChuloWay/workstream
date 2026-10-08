"""ART implementation of TASK's exact-original consumer capability."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifacts import ArtifactStore, ArtifactStoreError
from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest
from app.modules.artifacts.models import ArtifactReplica, ArtifactStorageNamespace
from app.modules.artifacts.service import (
    ArtifactStorageNamespaceError,
    ArtifactStorageNamespaceSpec,
    validate_artifact_replica_execution_namespace,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.projects.api.guide_documents import (
    GuideDocumentUnavailable,
    LockedGuideOriginalsRequest,
    ProjectGuideDocumentScopePort,
    GuideDocumentVersion,
)
from app.modules.tasks.api.guide_documents import (
    ContributorGuideDocument,
    TaskGuideDocumentNotFound,
    TaskGuideUnavailable,
    VerifiedTaskGuideRead,
    TaskGuideSelection,
)


class ArtifactTaskGuideDocuments:
    """Require caller-owned TASK/AUTH transaction, then prepare immutable originals."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        scope: ProjectGuideDocumentScopePort,
        manifest: SqlAlchemyGuideDocumentManifest,
        runtime: Callable[
            [],
            AbstractAsyncContextManager[
                tuple[ArtifactStore, ArtifactStorageNamespaceSpec, ArtifactPreparationService]
            ],
        ],
    ) -> None:
        self._session, self._scope, self._manifest, self._runtime = (
            session,
            scope,
            manifest,
            runtime,
        )

    async def _resolve(
        self, task_id: UUID, request: TaskGuideSelection
    ) -> tuple[tuple[ContributorGuideDocument, GuideDocumentVersion], ...]:
        if not self._session.in_transaction():
            raise TaskGuideUnavailable("guide document transaction is unavailable")
        originals = await self._scope.lock_task_originals(
            LockedGuideOriginalsRequest(
                project_id=request.project_id,
                guide_id=request.guide_id,
                guide_version=request.guide_version,
                source_snapshot_id=request.source_snapshot_id,
                source_snapshot_hash=request.source_snapshot_hash,
            )
        )
        versions = await self._manifest.versions(
            request.project_id, tuple(item.source for item in originals)
        )
        return tuple(
            (
                ContributorGuideDocument(
                    document_id=version.source_item_id,
                    order=version.item_order,
                    label=original.label,
                    media_type=version.media_type,
                    byte_count=version.byte_count,
                    sha256=version.sha256,
                    read_reference=f"/api/v1/tasks/{task_id}/guide/documents/{version.source_item_id}/content",
                ),
                version,
            )
            for original, version in zip(originals, versions, strict=True)
        )

    async def list(
        self, task_id: UUID, request: TaskGuideSelection
    ) -> tuple[ContributorGuideDocument, ...]:
        try:
            return tuple(document for document, _ in await self._resolve(task_id, request))
        except (GuideDocumentUnavailable, ValueError) as exc:
            raise TaskGuideUnavailable("guide document integrity unavailable") from exc

    @asynccontextmanager
    async def open(
        self, task_id: UUID, document_id: UUID, request: TaskGuideSelection
    ) -> AsyncIterator[VerifiedTaskGuideRead]:
        try:
            async with self._runtime() as (store, namespace, preparation):
                prepared = None
                stream = None
                try:
                    resolved = await self._resolve(task_id, request)
                    member = next(
                        (pair for pair in resolved if pair[0].document_id == document_id), None
                    )
                    if member is None:
                        raise TaskGuideDocumentNotFound("task guide document not found")
                    document, version = member
                    replica = await self._session.get(
                        ArtifactReplica, str(version.replica_id),
                        with_for_update={"read": True}, populate_existing=True,
                    )
                    persisted = await self._session.get(
                        ArtifactStorageNamespace, version.storage_namespace_id
                    )
                    if (replica is None or persisted is None
                        or replica.integrity_state == "invalid"
                        or replica.availability_state not in ("unknown", "available")):
                        raise TaskGuideUnavailable("guide document integrity unavailable")
                    validate_artifact_replica_execution_namespace(
                        replica=replica,
                        persisted=persisted,
                        namespace=namespace,
                        store=store,
                    )
                    prepared = await preparation.prepare(
                        store.open(replica.provider_object_ref),
                        media_type=version.media_type,
                        expected_sha256=version.sha256,
                        expected_size=version.byte_count,
                        maximum_bytes=version.byte_count,
                    )
                    stream = prepared.committed_source.stream()
                    # Opening the sealed second pass re-verifies scratch before headers.
                    first = await anext(stream)

                    async def content() -> AsyncIterator[bytes]:
                        yield first
                        async for chunk in stream:
                            yield chunk

                    yield VerifiedTaskGuideRead(document, content())
                finally:
                    try:
                        if stream is not None:
                            await stream.aclose()
                    finally:
                        if prepared is not None:
                            await prepared.close()
        except (
            GuideDocumentUnavailable,
            ArtifactStoreError,
            ArtifactStorageNamespaceError,
            ValueError,
            StopAsyncIteration,
        ) as exc:
            raise TaskGuideUnavailable("guide document integrity unavailable") from exc
