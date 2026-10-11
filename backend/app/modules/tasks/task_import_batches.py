"""One caller-root JSON import using canonical Task creation and ART byte custody."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.tasks.api.task_import import (
    ParsedTaskImport, TASK_IMPORT_MAPPING_VERSION, TASK_IMPORT_MAXIMUM_BYTES,
    TaskImportSourceCommitment, TaskImportSourceConsumerPort, VerifiedTaskImportSourceBinding,
    TaskImportBatchAction, TaskImportBatchAuthorityFacts, TaskImportBatchAuthorizationPort,
    TaskImportRow, parse_task_import,
)
from app.modules.tasks.api.task_import_membership import TaskImportBatchError
from app.modules.tasks.task_import_membership import TaskImportMembership
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands, TaskCreationPreparation
from app.modules.tasks.command_replay import TaskReplayConflict
from app.modules.tasks.models import (
    TaskImportBatch, TaskImportBatchCommandReceipt, TaskImportBatchMember, WorkstreamTask,
)
from app.modules.tasks.schemas import (
    ImportedTaskCreate, TaskImportBatchResponse, TaskImportBatchCurrentTask, TaskImportBatchStatus,
)


def imported_task_payload(row: TaskImportRow, source: TaskImportSourceCommitment, batch_id: UUID) -> ImportedTaskCreate:
    """Map instructions directly and stamp provenance solely from actual native custody."""
    return ImportedTaskCreate(
        **row.model_dump(), source_type="json_import", source_ref=f"task-import-source:{source.source_id}",
        source_payload_hash=source.sha256, import_batch_id=str(batch_id),
    )


def _binding(row: TaskImportBatch | TaskImportBatchCommandReceipt) -> VerifiedTaskImportSourceBinding:
    """Recover a closed native ancestry tuple without operational provider fields."""
    return VerifiedTaskImportSourceBinding(
        source_id=UUID(row.source_id), project_id=UUID(row.project_id), sha256=row.sha256, byte_count=row.byte_count,
        operation_identity=row.source_operation_identity, put_attempt_id=UUID(row.put_attempt_id),
        content_id=UUID(row.content_id), replica_id=UUID(row.replica_id), verification_job_id=UUID(row.verification_job_id),
        verification_generation=row.verification_generation, verification_receipt_id=UUID(row.verification_receipt_id),
        operation_receipt_id=UUID(row.operation_receipt_id) if row.operation_receipt_id is not None else None,
        observation_receipt_id=UUID(row.observation_receipt_id) if row.observation_receipt_id is not None else None,
    )


def _stage_binding(row: TaskImportBatch | TaskImportBatchCommandReceipt, binding: VerifiedTaskImportSourceBinding) -> None:
    """Stage only the concrete native ancestry columns validated by the ART owner."""
    row.source_operation_identity = binding.operation_identity
    row.verification_generation = binding.verification_generation
    for field in ("put_attempt_id", "content_id", "replica_id", "verification_job_id",
                  "verification_receipt_id", "operation_receipt_id", "observation_receipt_id"):
        value = getattr(binding, field)
        setattr(row, field, str(value) if value is not None else None)


class TaskImportBatchCommands:
    """Own the batch transaction; its Task and ART participants never commit it."""

    def __init__(
        self, session: AsyncSession, *, actor_profile_id: UUID, identity_link_id: UUID,
        authorization: TaskImportBatchAuthorizationPort, tasks: AuthorizedTaskCommands,
        source: TaskImportSourceConsumerPort,
    ) -> None:
        self._session, self._actor_id, self._link_id = session, actor_profile_id, identity_link_id
        self._authorization, self._tasks = authorization, tasks
        self._source = source

    @staticmethod
    def _request_digest(project_id: UUID, source_id: UUID) -> str:
        return canonical_json_hash({"project_id": str(project_id), "source_id": str(source_id)})

    async def _command(self, key: UUID, *, lock: bool = False) -> TaskImportBatchCommandReceipt | None:
        query = select(TaskImportBatchCommandReceipt).where(
            TaskImportBatchCommandReceipt.actor_profile_id == str(self._actor_id),
            TaskImportBatchCommandReceipt.action_id == TaskImportBatchAction.IMPORT.value,
            TaskImportBatchCommandReceipt.idempotency_key == key,
        ).execution_options(populate_existing=True)
        return await self._session.scalar(query.with_for_update() if lock else query)

    async def _file_batch(self, facts: TaskImportSourceCommitment, *, lock: bool = False) -> TaskImportBatch | None:
        query = select(TaskImportBatch).where(
            TaskImportBatch.project_id == str(facts.project_id), TaskImportBatch.sha256 == facts.sha256,
            TaskImportBatch.byte_count == facts.byte_count,
        ).execution_options(populate_existing=True)
        return await self._session.scalar(query.with_for_update() if lock else query)

    async def _preflight(self, project_id: UUID, source_id: UUID, key: UUID) -> tuple[TaskImportSourceCommitment, bool]:
        """Determine whether immutable recovery exists without reading provider bytes."""
        async with self._session.begin():
            command = await self._command(key)
            if command is not None:
                facts = await self._source.source_commitment(UUID(command.project_id), UUID(command.source_id))
                await self._source.authorize_commitment(facts)
                return facts, True
            facts = await self._source.source_commitment(project_id, source_id)
            await self._source.authorize_commitment(facts)
            batch = await self._file_batch(facts)
            return facts, batch is not None

    async def _read_first_import(self, facts: TaskImportSourceCommitment) -> ParsedTaskImport:
        """Finish bounded actual provider verification and parsing before TASK locks."""
        raw = bytearray()
        async with self._source.open(facts.project_id, facts.source_id) as opened:
            async for chunk in opened.stream:
                raw.extend(chunk)
                if len(raw) > TASK_IMPORT_MAXIMUM_BYTES:
                    raise TaskImportBatchError("task_import_source_limit_exceeded", 413)
        parsed = parse_task_import(bytes(raw))
        if (parsed.sha256, parsed.byte_count) != (facts.sha256, facts.byte_count):
            raise TaskImportBatchError("task_import_source_custody_invalid", 409)
        return parsed

    async def _reserve_command(
        self, facts: TaskImportSourceCommitment, key: UUID, request_digest: str,
    ) -> TaskImportBatchCommandReceipt:
        """Reserve the exact actor/action/key before batch, ART or AUTH locks."""
        await self._session.execute(insert(TaskImportBatchCommandReceipt).values(
            id=str(new_record_id()), actor_profile_id=str(self._actor_id), identity_link_id=str(self._link_id),
            action_id=TaskImportBatchAction.IMPORT.value,
            idempotency_key=key, request_digest=request_digest, project_id=str(facts.project_id),
            source_id=str(facts.source_id), sha256=facts.sha256, byte_count=facts.byte_count,
            media_type="application/json", source_operation_identity=facts.operation_identity, status="pending",
        ).on_conflict_do_nothing(constraint="uq_task_import_command_namespace"))
        return await self._command(key, lock=True)

    async def _reserve_batch(
        self, facts: TaskImportSourceCommitment, parsed: ParsedTaskImport | None,
        command: TaskImportBatchCommandReceipt,
    ) -> TaskImportBatch:
        """Serialize only the exact project/file identity; native FKs remain deferred."""
        if parsed is not None:
            await self._session.execute(insert(TaskImportBatch).values(
                id=str(new_record_id()), project_id=str(facts.project_id), source_id=str(facts.source_id),
                creation_command_receipt_id=command.id,
                sha256=facts.sha256, byte_count=facts.byte_count, media_type="application/json",
                schema_version=parsed.document.schema_version, mapping_version=TASK_IMPORT_MAPPING_VERSION,
                manifest_digest=canonical_json_hash(parsed.document.model_dump(mode="json")),
                row_count=len(parsed.document.tasks), actor_profile_id=str(self._actor_id), identity_link_id=str(self._link_id),
                metadata_label=parsed.document.metadata.label,
                source_operation_identity=facts.operation_identity, status="pending",
            ).on_conflict_do_nothing(constraint="uq_task_import_batch_file"))
        batch = await self._file_batch(facts, lock=True)
        if batch is None:
            raise TaskImportBatchError("task_import_batch_custody_invalid", 409)
        return batch

    def _facts(
        self, batch: TaskImportBatch, selected: VerifiedTaskImportSourceBinding, key: UUID, request_digest: str,
    ) -> TaskImportBatchAuthorityFacts:
        return TaskImportBatchAuthorityFacts(
            UUID(batch.id), UUID(batch.project_id), selected.source_id, self._actor_id, batch.sha256,
            batch.byte_count, batch.row_count, batch.manifest_digest,
            canonical_json_hash(selected.model_dump(mode="json")), key, request_digest,
        )

    async def _prepare_rows(
        self, batch: TaskImportBatch, facts: TaskImportSourceCommitment, parsed: ParsedTaskImport,
    ) -> list[tuple[int, TaskCreationPreparation]]:
        """Prepare every canonical Task retry identity before any ART/AUTH lock."""
        prepared = []
        rows = sorted(enumerate(parsed.document.tasks), key=lambda item: item[1].external_task_id.encode("utf-8"))
        for index, row in rows:
            values = imported_task_payload(row, facts, UUID(batch.id))
            prepared.append((index, await self._tasks.prepare_creation(
                UUID(batch.project_id), values, idempotency_key=uuid4(),
            )))
        return prepared

    async def _prepare_sources(
        self, batch: TaskImportBatch, command: TaskImportBatchCommandReceipt,
    ) -> VerifiedTaskImportSourceBinding:
        """Acquire all selected/original SOURCE custody before current AUTH."""
        expected = {}
        if batch.status == "committed":
            expected[batch.source_id] = _binding(batch)
        if command.status == "committed":
            expected[command.source_id] = _binding(command)
        expected.setdefault(command.source_id, None)
        prepared = {}
        for source_id in sorted(expected):
            prepared[source_id] = await self._source.prepare_binding(
                UUID(batch.project_id), UUID(source_id), expected[source_id],
            )
        selected = prepared[command.source_id]
        if (selected.sha256, selected.byte_count) != (batch.sha256, batch.byte_count):
            raise TaskImportBatchError("task_import_source_custody_invalid", 409)
        return selected

    async def _original_response(self, batch: TaskImportBatch) -> TaskImportBatchResponse:
        """Recover immutable creation facts through the one native membership owner."""
        return (await TaskImportMembership(self._session).validate(batch)).creation

    async def _stage_rows(
        self, batch: TaskImportBatch, parsed: ParsedTaskImport,
        prepared: list[tuple[int, TaskCreationPreparation]],
    ) -> TaskImportBatchResponse:
        """Authorize every CREATE then stage sorted writes in the same caller root."""
        decisions = [(index, creation, await self._tasks.authorize_creation(creation)) for index, creation in prepared]
        existing = set(await self._session.scalars(select(WorkstreamTask.external_task_id).where(
            WorkstreamTask.project_id == batch.project_id,
            WorkstreamTask.external_task_id.in_([row.external_task_id for row in parsed.document.tasks]),
        )))
        conflicts = tuple(index for index, row in enumerate(parsed.document.tasks) if row.external_task_id in existing)
        if conflicts:
            raise TaskImportBatchError("task_import_external_id_conflict", 409, conflicts)
        originals = {}
        for index, creation, decision in decisions:
            try:
                original = await self._tasks.stage_creation(creation, decision)
            except TaskReplayConflict as exc:
                if exc.code == "external_task_id_conflict":
                    raise TaskImportBatchError("task_import_external_id_conflict", 409, (index,)) from exc
                raise
            originals[index] = original
            self._session.add(TaskImportBatchMember(
                id=str(new_record_id()), batch_id=batch.id, project_id=batch.project_id, task_id=original.id,
                row_index=index, external_task_id=original.external_task_id,
                row_digest=canonical_json_hash(parsed.document.tasks[index].model_dump(mode="json")),
                create_idempotency_key=creation.facts.idempotency_key, task_command_receipt_id=creation.receipt.id,
                authorization_decision_id=str(decision.decision_id), response=original.model_dump(mode="json"),
            ))
        return TaskImportBatchResponse(
            batch_id=UUID(batch.id), project_id=UUID(batch.project_id), source_id=UUID(batch.source_id),
            sha256=batch.sha256, byte_count=batch.byte_count, schema_version=batch.schema_version,
            mapping_version=batch.mapping_version, row_count=batch.row_count, created_at=batch.created_at,
            label=batch.metadata_label,
            tasks=tuple(originals[index] for index in range(batch.row_count)),
        )

    async def import_source(self, project_id: UUID, source_id: UUID, *, idempotency_key: UUID) -> TaskImportBatchResponse:
        """Create all rows atomically or freshly authorize immutable exact-file recovery."""
        facts, recoverable = await self._preflight(project_id, source_id, idempotency_key)
        parsed = None if recoverable else await self._read_first_import(facts)
        digest = self._request_digest(project_id, source_id)
        async with self._session.begin():
            command = await self._reserve_command(facts, idempotency_key, digest)
            # Namespace custody may now point at the original selector from a competing commit.
            facts = await self._source.source_commitment(UUID(command.project_id), UUID(command.source_id))
            batch = await self._reserve_batch(facts, parsed, command)
            prepared = (await self._prepare_rows(batch, facts, parsed)) if batch.status == "pending" else []
            selected = await self._prepare_sources(batch, command)
            await self._source.authorize_binding(selected)
            decision_id = await self._authorization.authorize(
                TaskImportBatchAction.IMPORT, self._facts(batch, selected, idempotency_key, digest),
            )
            if command.request_digest != digest:
                raise TaskImportBatchError("task_import_idempotency_mismatch", 409)
            if command.status == "committed":
                original = await self._original_response(batch)
                if command.batch_id != batch.id or command.response != original.model_dump(mode="json"):
                    raise TaskImportBatchError("task_import_batch_custody_invalid", 409)
                return original
            if batch.status == "committed":
                original = await self._original_response(batch)
            else:
                original = await self._stage_rows(batch, parsed, prepared)
                _stage_binding(batch, selected)
                batch.authorization_decision_id, batch.status = str(decision_id), "committed"
                batch.response, batch.committed_at = original.model_dump(mode="json"), datetime.now(UTC)
            _stage_binding(command, selected)
            command.batch_id, command.authorization_decision_id, command.status = batch.id, str(decision_id), "committed"
            command.response, command.committed_at = original.model_dump(mode="json"), datetime.now(UTC)
            await self._session.flush()
            return original

    async def status(self, project_id: UUID, batch_id: UUID, *, request_id: UUID) -> TaskImportBatchStatus:
        """Read only native ordered members, preserving original and current states separately."""
        async with self._session.begin():
            batch = await self._session.scalar(select(TaskImportBatch).where(
                TaskImportBatch.id == str(batch_id), TaskImportBatch.project_id == str(project_id),
                TaskImportBatch.status == "committed",
            ).execution_options(populate_existing=True))
            if batch is None:
                raise TaskImportBatchError("task_import_batch_not_found", 404)
            binding = await self._source.prepare_binding(project_id, UUID(batch.source_id), _binding(batch))
            await self._source.authorize_binding(binding)
            await self._authorization.authorize(TaskImportBatchAction.READ, self._facts(
                batch, binding, request_id, canonical_json_hash({"project_id": str(project_id), "batch_id": str(batch_id)}),
            ))
            original = await self._original_response(batch)
            rows = (await self._session.execute(select(TaskImportBatchMember.row_index, WorkstreamTask.id, WorkstreamTask.status)
                    .join(WorkstreamTask, (WorkstreamTask.id == TaskImportBatchMember.task_id)
                          & (WorkstreamTask.project_id == TaskImportBatchMember.project_id))
                    .where(TaskImportBatchMember.batch_id == batch.id).order_by(TaskImportBatchMember.row_index))).all()
            return TaskImportBatchStatus(creation=original, current_tasks=tuple(
                TaskImportBatchCurrentTask(row_index=index, task_id=UUID(task_id), status=status)
                for index, task_id, status in rows
            ))
