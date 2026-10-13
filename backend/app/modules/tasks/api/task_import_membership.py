"""Native immutable import membership; these facts never grant Task authority."""

from dataclasses import dataclass
from uuid import UUID


class TaskImportBatchError(RuntimeError):
    """A controlled batch outcome with bounded document-row diagnostics."""

    def __init__(self, code: str, status_code: int, row_indexes: tuple[int, ...] = ()):
        self.code, self.status_code, self.row_indexes = code, status_code, row_indexes
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TaskImportMemberIdentity:
    """One actual ordered native row and its original canonical CREATE custody."""

    member_id: UUID
    task_id: UUID
    row_index: int
    external_task_id: str
    row_digest: str
    create_idempotency_key: UUID
    task_command_receipt_id: UUID
    authorization_decision_id: UUID
