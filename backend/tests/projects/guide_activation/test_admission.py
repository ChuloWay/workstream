"""Activation cannot enter owner SQL without a clean root and nominal authority."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.api.guide_activation import GuideActivationCommand
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_activation.service import GuideActivationService
from .test_contracts import command_values


@pytest.mark.parametrize(
    "denial", ["no_root", "nested", "new", "dirty", "deleted", "service", "duck_handle"]
)
async def test_invalid_transaction_or_authority_denies_before_product_sql(denial):
    session = SimpleNamespace(
        in_transaction=lambda: denial != "no_root",
        in_nested_transaction=lambda: denial == "nested",
        new={object()} if denial == "new" else set(),
        dirty={object()} if denial == "dirty" else set(),
        deleted={object()} if denial == "deleted" else set(),
        execute=AsyncMock(side_effect=AssertionError("invalid admission reached SQL")),
    )
    entered = []

    class Authority:
        @asynccontextmanager
        async def lock_activation_scope(self, locator):
            entered.append(locator)
            yield SimpleNamespace(consume_new=AsyncMock(), validate_replay=AsyncMock())

    actor = ActorIdentityFacts(
        uuid4(),
        uuid4(),
        ActorKind.SERVICE if denial == "service" else ActorKind.HUMAN,
        service_identity="workstream.project.setup" if denial == "service" else None,
    )
    service = GuideActivationService(
        session,
        contribution=None,
        planner=None,
        pre_catalogue=None,
        post_catalogue=None,
        authorization=Authority(),
    )
    with pytest.raises(GuideProposalError, match="authority_unavailable"):
        await service.activate(
            GuideActivationCommand(**command_values()), actor=actor, request_id=uuid4()
        )
    assert len(entered) == (1 if denial == "duck_handle" else 0)
    session.execute.assert_not_awaited()
