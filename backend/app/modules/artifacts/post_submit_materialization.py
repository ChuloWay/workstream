"""Verified post-submit input through the sole bounded artifact scratch owner."""

import asyncio
from collections.abc import Callable
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cancellation import await_cancellation_resistant
from app.interfaces.artifacts import ArtifactStore
from app.modules.artifacts.api.submission_materialization import (
    PostSubmissionMaterialConsumer, PostSubmissionMaterializationResult,
    PostSubmissionMaterializationUnavailable, SubmissionMaterialEntry,
)
from app.modules.artifacts.post_submit_selection import (
    PostSubmissionMaterialSelection, select_post_submission_material,
)
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.service import ArtifactStorageNamespaceError, ArtifactStorageNamespaceSpec
from app.modules.artifacts.submission_archive import (
    SealedSubmissionTree, SubmissionArchiveInspector, SubmissionArchiveEntryType,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api import PostSubmissionEvaluationRequest, PostSubmissionEvaluationResult
from app.modules.tasks.api.submitted_bundle import SubmittedBundlePort, SubmittedBundleUnavailable


class PostSubmissionMaterializationAuthority(Protocol):
    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None:
        """Deny unavailable fixed-service access before protected reads."""

    async def authorize(
        self, request: PostSubmissionEvaluationRequest, selection: PostSubmissionMaterialSelection,
    ) -> None:
        """Authorize exact resolved facts before provider and scratch access."""


class DenyPostSubmissionMaterializationAuthority:
    """Production remains unavailable until ARCH-04D activates exact service authority."""

    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None:
        raise PostSubmissionMaterializationUnavailable("post_submit_materialization_unavailable")

    async def authorize(
        self, request: PostSubmissionEvaluationRequest, selection: PostSubmissionMaterialSelection,
    ) -> None:
        raise PostSubmissionMaterializationUnavailable("post_submit_materialization_unavailable")


class _MaterialView:
    def __init__(self, tree: SealedSubmissionTree) -> None:
        self._tree = tree
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("submission material view is closed")

    @property
    def entries(self) -> tuple[SubmissionMaterialEntry, ...]:
        self._require_open()
        return tuple(SubmissionMaterialEntry(
            item.normalized_path, item.entry_type.value, item.byte_count, item.sha256, item.executable,
        ) for item in self._tree.entries)

    def read_file(self, normalized_path: str, *, maximum_bytes: int) -> bytes:
        self._require_open()
        return self._tree.read_file(normalized_path, maximum_bytes=maximum_bytes)

    def __reduce__(self):
        raise TypeError("submission material view is process-local")


class _MaterialProcessor:
    def __init__(self, inspector, inspection, request, consumer) -> None:
        self._inspector, self._inspection = inspector, inspection
        self._request, self._consumer = request, consumer
        self._aborted = False
        self._consumer_task: asyncio.Task[PostSubmissionEvaluationResult] | None = None
        self._view: _MaterialView | None = None

    def abort(self) -> None:
        self._aborted = True
        if self._view is not None:
            self._view.close()
        if self._consumer_task is not None:
            self._consumer_task.cancel()

    async def process(self, reader, workspace) -> PostSubmissionEvaluationResult:
        projection = self._inspector._projected_tree(reader, workspace, expected=self._inspection)
        # The preparation owner shields and drains this entire operation, including
        # projection entry, before it releases the reader or workspace.
        tree = await asyncio.to_thread(projection.__enter__)
        try:
            if self._aborted:
                raise asyncio.CancelledError
            self._view = _MaterialView(tree)
            self._consumer_task = asyncio.create_task(self._consumer.evaluate(self._request, self._view))
            result = PostSubmissionEvaluationResult.model_validate(await self._consumer_task)
            result.validate_request(self._request)
            return result
        finally:
            if self._view is not None:
                self._view.close()
            await await_cancellation_resistant(asyncio.to_thread(projection.__exit__, None, None, None))


class PostSubmissionMaterializer:
    """Resolve, authorize, verify, scope, clean, and revalidate one exact input."""

    def __init__(
        self, *, sessions: async_sessionmaker[AsyncSession],
        tasks: Callable[[AsyncSession], SubmittedBundlePort], store: ArtifactStore,
        namespace: ArtifactStorageNamespaceSpec, preparation: ArtifactPreparationService,
        inspector: SubmissionArchiveInspector, authority: PostSubmissionMaterializationAuthority,
    ) -> None:
        self._sessions, self._tasks, self._store = sessions, tasks, store
        self._namespace, self._preparation = namespace, preparation
        self._inspector, self._authority = inspector, authority

    async def _select(self, request) -> PostSubmissionMaterialSelection:
        try:
            async with self._sessions() as session, session.begin():
                return await select_post_submission_material(
                    session, tasks=self._tasks(session), request=request,
                    namespace=self._namespace, store=self._store,
                )
        except (SubmittedBundleUnavailable, ArtifactStorageNamespaceError):
            raise PostSubmissionMaterializationUnavailable("post_submit_material_unavailable") from None

    async def materialize(
        self, request: PostSubmissionEvaluationRequest, consumer: PostSubmissionMaterialConsumer,
    ) -> PostSubmissionMaterializationResult:
        request = PostSubmissionEvaluationRequest.model_validate(request)
        await self._authority.preflight(request)
        selected = await self._select(request)
        await self._authority.authorize(request, selected)
        prepared = await self._preparation.prepare(
            self._store.open(selected.provider_object_ref), media_type=selected.media_type,
            expected_sha256=selected.sha256, expected_size=selected.byte_count,
        )
        try:
            inspection = await prepared.inspect(self._inspector)
            manifest = build_submission_manifest(inspection)
            expected_files = tuple((entry.normalized_path, entry.sha256, entry.byte_count)
                                   for entry in manifest.entries
                                   if entry.entry_type is SubmissionArchiveEntryType.FILE)
            supplied_files = tuple(sorted((entry.artifact, entry.hash, entry.size_bytes)
                                          for entry in request.structural_input.manifest))
            if manifest.sha256 != selected.semantic_manifest_sha256 or supplied_files != expected_files:
                raise PostSubmissionMaterializationUnavailable("post_submit_material_manifest_mismatch")
            evaluation = await self._preparation._process_prepared_submission(
                prepared, _MaterialProcessor(self._inspector, inspection, request, consumer),
                reserved_bytes=manifest.total_expanded_bytes, maximum_entries=manifest.entry_count,
            )
        finally:
            await prepared.close()
        if await self._select(request) != selected:
            raise PostSubmissionMaterializationUnavailable("post_submit_material_changed")
        facts = selected.submission
        return PostSubmissionMaterializationResult(
            submission_id=facts.submission_id, submission_version=facts.submission_version,
            admission_id=facts.admission_id, binding_id=facts.binding_id, content_id=facts.content_id,
            replica_id=selected.replica_id, content_sha256=selected.sha256,
            byte_count=selected.byte_count, semantic_manifest_sha256=selected.semantic_manifest_sha256,
            evaluation=evaluation,
        )
