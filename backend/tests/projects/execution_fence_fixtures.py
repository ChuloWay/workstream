"""Passive connection ports for PROJECT execution-fence delegation tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.modules.authorization.catalogue import ActionId
from app.modules.projects import submission_policy_mutation_service as submission
from app.modules.projects import sufficiency_mutation_service as sufficiency


@pytest.fixture(params=["sufficiency", "submission-policy"])
def fence_case(request: pytest.FixtureRequest) -> SimpleNamespace:
    """Expose standard mock ports; never implement or validate a fence here."""
    if request.param == "sufficiency":
        module = sufficiency
        service_type = sufficiency.GuideSufficiencyMutationService
        conflict = sufficiency.GuideSufficiencyMutationConflict
        action = ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
        domain = "workstream.guide_sufficiency.execution_fence.v1"
    else:
        module = submission
        service_type = submission.SubmissionPolicyMutationService
        conflict = submission.SubmissionPolicyMutationConflict
        action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE
        domain = "workstream.submission_policy.execution_fence.v1"
    events = []
    connection = MagicMock(spec=AsyncConnection)
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = connection

    async def enter():
        events.append("enter")
        return connection

    async def exit_connection(*_):
        events.append("exit")
        return False

    async def acquire(*_):
        events.append("acquire")
        return True

    async def release(*_):
        events.append("unlock")

    connection.__aenter__.side_effect = enter
    connection.__aexit__.side_effect = exit_connection
    connection.scalar.side_effect = acquire
    connection.execute.side_effect = release
    return SimpleNamespace(
        module=module, service=service_type(SimpleNamespace(bind=engine)),
        conflict=conflict, action=action, domain=domain,
        actor_id="00000000-0000-0000-0000-000000000001", key=UUID(int=2),
        connection=connection, engine=engine, events=events,
    )


def open_fence(case: SimpleNamespace):
    """Call the actual service method, without reconstructing its key or policy."""
    return case.service._execution_fence(case.actor_id, case.action, case.key)
