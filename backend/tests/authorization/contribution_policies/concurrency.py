"""Observe actual project locks in independent policy transactions."""

import asyncio
from uuid import uuid4

from sqlalchemy import text

from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from tests.auth_concurrency_support import wait_for_named_database_lock


async def ordered_policy_calls(first, second, database_url, monkeypatch):
    """Release the held owner lock only after PostgreSQL observes its exact waiter."""
    owner = ProjectContributionPolicyEligibility
    original = owner.lock_contribution_policy_project
    held, waiting = asyncio.Event(), asyncio.Event()
    identity = "policy-race-" + uuid4().hex
    pids = {}

    async def hook(self, project_id):
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
        await held.wait()
        pids["second"] = await self._session.scalar(text("select pg_backend_pid()"))
        await self._session.execute(
            text("select set_config('application_name', :name, true)"), {"name": identity}
        )
        waiting.set()
        return await original(self, project_id)

    with monkeypatch.context() as patch:
        patch.setattr(owner, "lock_contribution_policy_project", hook)
        tasks = [
            asyncio.create_task(first(), name=identity + "-first"),
            asyncio.create_task(second(), name=identity + "-second"),
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
