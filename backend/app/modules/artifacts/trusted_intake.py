"""ART ownership of one upload/download-overlapped trusted intake session."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import BinaryIO

from app.core.cancellation import await_cancellation_resistant, await_completion_preserving_cancellation
from app.interfaces.external_services import ExternalServiceAdapterError
from app.interfaces.trusted_submission_intake import (
    TrustedIntakePreparation, TrustedIntakeSession, TrustedSubmissionIntakeAdapter,
)
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.api.submission_archive import SubmissionArchiveInspectionResult


class TrustedArchiveInspector:
    """Bind PreparedArtifact's retained reader to its exact server commitment."""

    def __init__(self, intake: TrustedIntakeSession, commitment: ArtifactCommitment) -> None:
        self._intake, self._commitment = intake, commitment

    def inspect(self, reader: BinaryIO) -> SubmissionArchiveInspectionResult:
        return self._intake.inspect(reader, archive_sha256=self._commitment.sha256,
                                    archive_byte_count=self._commitment.byte_count)


@asynccontextmanager
async def prepared_trusted_intake(adapter: TrustedSubmissionIntakeAdapter,
                                 request: TrustedIntakePreparation):
    """Prepare while bytes arrive; every exit drains preparation and cleanup."""
    pending = asyncio.create_task(adapter.prepare(request))
    failure: BaseException | None = None
    try:
        yield pending
    except BaseException as error:
        failure = error
        raise
    finally:
        if not pending.done():
            pending.cancel()
        try:
            session = await await_cancellation_resistant(pending)
        except (asyncio.CancelledError, ExternalServiceAdapterError):
            if failure is None:
                raise
        else:
            cancelled = isinstance(failure, asyncio.CancelledError)
            if cancelled:
                session.abort()
            try:
                await await_completion_preserving_cancellation(session.close())
            except ExternalServiceAdapterError:
                if not cancelled:
                    raise
