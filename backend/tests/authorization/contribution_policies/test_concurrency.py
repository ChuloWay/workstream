"""Competing CON lifecycle operations retain their existing serialization."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.contributions.api import ContributionPolicyConflict, ContributionPolicyUnavailable
from .postgresql_support import world
from .concurrency import ordered_policy_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("race", ("publish_publish", "publish_retire"))
@pytest.mark.parametrize("first", ("publish", "contender"))
async def test_concurrent_policy_publication_and_retirement_are_serialized(
    admin_access, auth_database_env, monkeypatch, race, first
):
    target = await world(admin_access)
    prior = await target.execute("create_draft", target.request("create_draft"))
    prior = await target.execute("update_draft", target.request("update_draft", prior))
    if race == "publish_retire":
        published = await target.execute("publish", target.request("publish", prior))
        retire = target.request("retire", published)
        prior = await target.execute("create_draft", target.request("create_draft"))
        prior = await target.execute("update_draft", target.request("update_draft", prior))
    publish = target.request("publish", prior)
    contender = replace(publish, operation_id=uuid4()) if race == "publish_publish" else retire
    second_op = "publish" if race == "publish_publish" else "retire"

    async def run(operation, request):
        try:
            return await target.execute(operation, request)
        except (ContributionPolicyConflict, ContributionPolicyUnavailable):
            return "denied"

    calls = ((lambda: run("publish", publish)), (lambda: run(second_op, contender)))
    if first == "contender":
        calls = calls[::-1]
    a, b = await ordered_policy_calls(*calls, auth_database_env, monkeypatch)
    assert a != "denied"
    assert b == "denied"
    winning_op, winning_request = (
        ("publish", publish) if first == "publish" else (second_op, contender)
    )
    assert await target.execute(winning_op, winning_request) == a
    losing_op, losing_request = (
        (second_op, contender) if first == "publish" else ("publish", publish)
    )
    assert await run(losing_op, losing_request) == "denied"
