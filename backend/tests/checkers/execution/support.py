"""Strict phase-specific participants, never fake AUTH catalogue or audit evidence."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.checkers import post_submission_executor
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import (
    ExecuteEvidence,
    ExecuteFacts,
    FinalizeEvidence,
    FinalizeFacts,
    PreparedExecution,
    PreparedFinalization,
)


class ForbiddenMaterial:
    async def materialize(self, *args):
        pytest.fail("denied execution accessed material")


def denied_executor():
    # No bind is needed: real production preflight denies before any SQL.
    return post_submission_executor(
        sessions=async_sessionmaker(), materialization=ForbiddenMaterial()
    )


class ControlledExecution(PreparedExecution):
    def __init__(self, request):
        self.request, self.consumed = request, False

    async def consume(self, facts):
        assert type(facts) is ExecuteFacts and facts.request == self.request and not self.consumed
        self.consumed = True
        return ExecuteEvidence(
            evidence_id=new_record_id(),
            facts_digest=canonical_json_hash(facts.model_dump(mode="json")),
        )


class ControlledFinalization(PreparedFinalization):
    def __init__(self, request):
        self.request, self.consumed = request, False

    async def consume(self, facts):
        assert type(facts) is FinalizeFacts and facts.request == self.request and not self.consumed
        self.consumed = True
        return FinalizeEvidence(
            evidence_id=new_record_id(),
            facts_digest=canonical_json_hash(facts.model_dump(mode="json")),
        )


class ControlledExecuteAuthority:
    async def preflight(self, request):
        assert request.evaluation_generation > 0

    @asynccontextmanager
    async def prepare_execution(self, request):
        yield ControlledExecution(request)


class ControlledFinalizeAuthority:
    async def preflight(self, request):
        assert request.evaluation_generation > 0

    @asynccontextmanager
    async def prepare_finalization(self, request):
        yield ControlledFinalization(request)


def controlled_executor(h, *, registry=None, outbox=None):
    from app.adapters.outbox import outbox_append
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.modules.checkers.runner import default_checker_registry

    return PostSubmissionExecutor(
        sessions=h.factory,
        materialization=h.service,
        execute_authority=lambda session: ControlledExecuteAuthority(),
        finalize_authority=lambda session: ControlledFinalizeAuthority(),
        registry=registry if registry is not None else default_checker_registry(),
        outbox=outbox if outbox is not None else outbox_append,
    )


async def reserve(h, request=None):
    from app.modules.checkers.execution_coordination import EvaluationCoordinator

    async with h.factory() as session, session.begin():
        return await EvaluationCoordinator(session).reserve_current_evaluation(
            request if request is not None else h.request
        )
