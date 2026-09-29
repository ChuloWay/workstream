"""Action-specific denial until canonical AUTH installs execute/finalize custody."""

from app.modules.checkers.api.execution import CheckerExecutionUnavailable


class DenyExecutionAuthority:
    async def preflight(self, request):
        raise CheckerExecutionUnavailable("post_submit_execution_unavailable")

    def prepare_execution(self, request):
        raise CheckerExecutionUnavailable("post_submit_execution_unavailable")


class DenyFinalizationAuthority:
    async def preflight(self, request):
        raise CheckerExecutionUnavailable("post_submit_finalization_unavailable")

    def prepare_finalization(self, request):
        raise CheckerExecutionUnavailable("post_submit_finalization_unavailable")
