"""Ports for trusted, non-monetary checker trial authority."""

from __future__ import annotations

from typing import Protocol

from app.modules.checkers.api.trial_profiles import (
    TrialExecutionProfile,
    TrialProfileSelector,
)


class TrialProfileReaderPort(Protocol):
    """Resolve only locally provisioned immutable execution profiles."""

    def read(self, selector: TrialProfileSelector) -> TrialExecutionProfile | None:
        """Return an exact id/version/digest match, or no authority."""


__all__ = ("TrialProfileReaderPort",)
