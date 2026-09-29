"""Action-specific denial until canonical AUTH installs execute/finalize custody."""

from app.modules.checkers.api.execution import CheckerExecutionUnavailable


class DenyExecutionAuthority:
    """Keep production execution unavailable until live AUTH is installed."""

    async def preflight(self, request):
        """Deny execution before any prepared authority or material access."""
        raise CheckerExecutionUnavailable("post_submit_execution_unavailable")

    def prepare_execution(self, request):
        """Refuse preparation even if a caller bypasses preflight."""
        raise CheckerExecutionUnavailable("post_submit_execution_unavailable")


class DenyFinalizationAuthority:
    """Keep production finalization unavailable until live AUTH is installed."""

    async def preflight(self, request):
        """Deny publication before any prepared finalization authority."""
        raise CheckerExecutionUnavailable("post_submit_finalization_unavailable")

    def prepare_finalization(self, request):
        """Refuse finalization preparation independently of preflight."""
        raise CheckerExecutionUnavailable("post_submit_finalization_unavailable")
