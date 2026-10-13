"""Sealed process-local custody for one checked submission continuation."""

from __future__ import annotations

from typing import final
from uuid import UUID

from app.modules.artifacts.sources import CommittedArtifactSource, PreparedArtifact
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitCompletion,
    SelectedPreSubmitReservationFacts,
)


@final
class SubmissionBundlePreparedCustody:
    """Unforgeable join of live prepared bytes and their fresh pass capability."""

    __slots__ = ("_prepared", "_selected")

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("submission bundle custody requires live prepared work")


    @classmethod
    def _from_selected_pre_submit(
        cls,
        *,
        prepared: PreparedArtifact,
        completion: SelectedPreSubmitCompletion,
    ) -> SubmissionBundlePreparedCustody:
        """Seal a completed selected run to the still-live verified bytes once."""
        if (
            type(prepared) is not PreparedArtifact
            or type(completion) is not SelectedPreSubmitCompletion
            or completion.capability is None
            or completion.terminal.outcome != "completed"
            or completion.terminal.execution is None
            or not completion.terminal.execution.eligible
        ):
            raise TypeError("submission bundle selected custody requires a passing run")
        reservation = completion.terminal.lease.reservation
        if (
            type(reservation) is not SelectedPreSubmitReservationFacts
            or reservation.admission_lineage is None
            or reservation.prepared_generation_id != prepared.generation_id
            or reservation.archive_sha256 != prepared.commitment.sha256
            or reservation.archive_byte_count != prepared.commitment.byte_count
        ):
            raise TypeError("submission bundle selected custody differs from prepared bytes")
        run_id = completion.capability.consume(
            run_id=reservation.attempt_id,
            terminal_digest=completion.terminal.terminal_digest,
            attempt_id=reservation.attempt_id,
            prepared_generation_id=reservation.prepared_generation_id,
            archive_sha256=reservation.archive_sha256,
            semantic_manifest_sha256=reservation.semantic_manifest_sha256,
        )
        if run_id != reservation.attempt_id:
            raise TypeError("submission bundle selected custody is unavailable")
        custody = object.__new__(cls)
        custody._prepared = prepared
        custody._selected = completion.terminal
        return custody

    @property
    def prepared_generation_id(self) -> UUID:
        return self._prepared.generation_id


    @property
    def selected_reservation(self) -> SelectedPreSubmitReservationFacts:
        """Return the exact selected request only for selected-run custody."""
        if self._selected is None:
            raise TypeError("selected submission custody is unavailable")
        return self._selected.lease.reservation

    @property
    def selected_terminal_digest(self) -> str:
        """Return the terminal digest paired with the selected reservation."""
        if self._selected is None:
            raise TypeError("selected submission custody is unavailable")
        return self._selected.terminal_digest

    @property
    def selected_terminal_body(self) -> dict[str, object]:
        """Return a fresh canonical terminal body for the durable ART snapshot."""
        if self._selected is None:
            raise TypeError("selected submission custody is unavailable")
        return self._selected.canonical_body()

    @property
    def source(self) -> CommittedArtifactSource:
        return self._prepared.committed_source
