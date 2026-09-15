"""Observe actual project locks in independent policy transactions."""

import asyncio
from uuid import uuid4

from sqlalchemy import text

from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from tests.auth_concurrency_support import wait_for_named_database_lock


async def ordered_policy_calls(first, second, database_url, monkeypatch):
    """Release the held owner lock only after PostgreSQL observes its exact waiter."""
    owner = ProjectContributionPolicyEligibility
    original = owner.lock_contribution_policy_project
    original_control = AdminAuthorizationRepository.lock_control
    held, waiting = asyncio.Event(), asyncio.Event()
    identity = "policy-race-" + uuid4().hex
    pids = {}

    async def name_waiter(session):
        pids["second"] = await session.scalar(text("select pg_backend_pid()"))
        await session.execute(
            text("select set_config('application_name', :name, true)"), {"name": identity}
        )
        waiting.set()

    async def project_hook(self, project_id):
        name = asyncio.current_task().get_name()
        if name not in {identity + "-first", identity + "-second"}:
            return await original(self, project_id)
        if name.endswith("-first"):
            result = await original(self, project_id)
            pids["first"] = await self._session.scalar(text("select pg_backend_pid()"))
            held.set()
            await waiting.wait()
            await wait_for_named_database_lock(
                database_url,
                identity,
                expected_waiter_pid=pids["second"],
                expected_blocker_pid=pids["first"],
            )
            return result
        if not waiting.is_set():
            await name_waiter(self._session)
        return await original(self, project_id)

    async def control_hook(self):
        if asyncio.current_task().get_name() == identity + "-second":
            await name_waiter(self._session)
        return await original_control(self)

    async def start_second():
        await held.wait()
        return await second()

    with monkeypatch.context() as patch:
        patch.setattr(owner, "lock_contribution_policy_project", project_hook)
        patch.setattr(AdminAuthorizationRepository, "lock_control", control_hook)
        tasks = [
            asyncio.create_task(first(), name=identity + "-first"),
            asyncio.create_task(start_second(), name=identity + "-second"),
        ]
        try:
            result = await asyncio.wait_for(asyncio.gather(*tasks), timeout=60)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    assert pids["first"] != pids["second"]
    return result
