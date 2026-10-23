"""Cross-port call sequencing; PostgreSQL/ART custody have separate integration proof."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.checker_model_provider import (
    CheckerModelCreateFailure,
    CheckerModelCreateOutcome,
    CheckerModelCreateResult,
    CheckerModelObservation,
    CheckerModelProviderStatus,
    CheckerModelRecoveryOutcome,
    CheckerModelRecoveryResult,
    CheckerModelResponseReference,
    CheckerModelUsage,
)
from app.interfaces.checker_model_proxy import ModelProxyRequest
from app.modules.model_usage.api import (
    AttachedModelCallAttempt,
    CompletedModelCall,
    ModelCallBudgetUnavailable,
    ModelCallEvidence,
    ModelCallExecutionFacts,
    ModelCallUnavailable,
    ModelPaidSlotKey,
    ProjectModelProfile,
)
from app.adapters.checkers.model_proxy import CheckerModelProxy
from tests.checkers_model_calls.test_model_call_contract import profile_spec, sha


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class Harness:
    """Retain port-observable effects across fresh proxy instances and invocations."""

    def __init__(self):
        spec = profile_spec()
        self.profile = ProjectModelProfile(
            operation_id=uuid4(),
            actor_profile_id=new_record_id(),
            spec=spec,
            profile_digest=canonical_json_hash(spec.model_dump(mode="json")),
            profile_id=new_record_id(),
            authorization_evidence_id=new_record_id(),
            created_at=datetime.now(UTC),
        )
        self.execution = ModelCallExecutionFacts(
            project_id=spec.project_id,
            task_id=new_record_id(),
            assignment_id=new_record_id(),
            submission_id=new_record_id(),
            submission_version=1,
            evaluation_request_id=new_record_id(),
            evaluation_generation=1,
            checker_run_id=new_record_id(),
            worker_lease_id=uuid4(),
            worker_lease_generation=1,
            worker_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        self.slot = ModelPaidSlotKey(
            project_id=spec.project_id,
            assignment_id=self.execution.assignment_id,
            submission_id=self.execution.submission_id,
            submission_version=1,
            requirement_id="quality",
            registry_entry_digest=sha("registry"),
            configuration_sha256=canonical_json_hash({"selector": "quality"}),
            **self.profile.selector.model_dump(),
        )
        self.facts = SimpleNamespace(
            execution=self.execution,
            slot=self.slot,
            registry_entry_id=new_record_id(),
        )
        self.state, self.request_sha = "prepared", None
        self.slot_id, self.attempt_id, self.internal_id = (new_record_id() for _ in range(3))
        self.reference = CheckerModelResponseReference("resp_original")
        self.observation = CheckerModelObservation(
            reference=self.reference,
            provider_model=spec.model_snapshot,
            status=CheckerModelProviderStatus.COMPLETED,
            output_text='{"verdict":"pass"}',
            usage=CheckerModelUsage(20, 5, 10, 2, 30),
        )
        self.create_result = CheckerModelCreateResult(
            CheckerModelCreateOutcome.ACCEPTED,
            observation=self.observation,
            known_response=self.reference,
        )
        self.active_transactions = 0
        self.events, self.blobs, self.evidence = [], {}, {}
        self.create_count, self.recover_count, self.settle_count = 0, 0, 0
        self.budget_available = True
        self.provider_id = None
        self.completed = None
        self.stale = False

    @asynccontextmanager
    async def sessions(self):
        yield self

    @asynccontextmanager
    async def begin(self):
        self.active_transactions += 1
        try:
            yield self
        finally:
            self.active_transactions -= 1

    async def scalar(self, _):
        return datetime.now(UTC)

    async def authorization(self, *_):
        return object()

    async def resolve(self, *_):
        return self.facts

    async def read_exact(self, *_args, **_kwargs):
        return self.profile

    async def prepare_attempt(self, _execution, _slot, *, request_sha256, **_):
        if self.request_sha not in {None, request_sha256}:
            raise ModelCallUnavailable("changed_prompt")
        self.request_sha = request_sha256
        return AttachedModelCallAttempt(
            slot_id=self.slot_id,
            slot_key=self.slot,
            attempt_id=self.attempt_id,
            attempt_number=1,
            internal_call_request_id=self.internal_id,
            request_sha256=request_sha256,
            state=self.state,
            replayed=self.state != "prepared",
        )

    async def consume_prepared(self, *_args, **_kwargs):
        self.events.append("grant_consumed")

    async def reserve_dispatch(self, _execution, _prepared, evidence):
        if not self.budget_available:
            raise ModelCallBudgetUnavailable("no_budget")
        self.events.append("dispatch_committed")
        self.state = "dispatching"
        return SimpleNamespace(state=self.state, replayed=False)

    async def mark_uncertain(self, _effect, _digest, *, provider_response_id):
        self.provider_id = provider_response_id
        self.state = "uncertain"
        self.events.append("reference_committed")

    async def mark_known_no_effect(self, *_):
        self.state = "known_no_effect"

    async def attach_recovery(self, *_):
        if self.provider_id is None:
            raise ModelCallUnavailable("unknown_effect")
        return SimpleNamespace(provider_response_id=self.provider_id)

    async def complete(self, _effect, *, response_evidence, usage, **_):
        self.settle_count += 1
        self.state = "completed"
        self.completed = CompletedModelCall(
            slot_id=self.slot_id,
            attempt_id=self.attempt_id,
            attempt_number=1,
            internal_call_request_id=self.internal_id,
            provider_response_id=self.provider_id,
            request_evidence=self.evidence["model_request"],
            response_evidence=response_evidence,
            usage=usage,
            settled_nanodollars=465,
            completed_at=datetime.now(UTC),
            replayed=False,
        )

    async def complete_known_failure(self, *args, **kwargs):
        await self.complete(*args, **kwargs)
        self.state = "known_failed"

    async def attach_completed(self, *_):
        if self.stale:
            raise ModelCallUnavailable("stale_invocation")
        return self.completed

    @asynccontextmanager
    async def provider(self, _):
        yield self

    async def create(self, _):
        assert self.active_transactions == 0
        assert "dispatch_committed" in self.events
        self.create_count += 1
        return self.create_result

    async def recover(self, reference):
        assert self.active_transactions == 0
        assert reference == self.reference
        self.recover_count += 1
        return CheckerModelRecoveryResult(
            CheckerModelRecoveryOutcome.OBSERVED,
            self.reference,
            self.observation,
        )

    async def store(self, request):
        assert self.active_transactions == 0
        data = b"".join([chunk async for chunk in request.byte_source])
        assert digest(data) == request.selector.content_sha256
        role = request.selector.slot_key
        if role == "model_response":
            assert self.provider_id is not None
        self.blobs[role] = data
        evidence = self.evidence.setdefault(
            role,
            ModelCallEvidence(
                binding_id=new_record_id(),
                content_id=new_record_id(),
                put_attempt_id=new_record_id(),
                verification_receipt_id=new_record_id(),
                content_sha256=digest(data),
                byte_count=len(data),
            ),
        )
        return SimpleNamespace(status="verified", **evidence.model_dump())

    async def bind_checker_output(self, request):
        return self.evidence[request.selector.slot_key]

    async def read_response(self, _selector, evidence):
        assert evidence == self.evidence["model_response"]
        return self.blobs["model_response"]

    def proxy(self):
        return CheckerModelProxy(
            sessions=self.sessions,
            authorization=self.authorization,
            grants=lambda *_: self,
            calls=lambda *_: self,
            profiles=lambda *_: self,
            outputs=self,
            bindings=lambda *_: self,
            provider=self.provider,
        )

    async def invoke(self, prompt="Evaluate this work"):
        return await self.proxy().handle(
            ModelProxyRequest(
                "model_" + uuid4().hex,
                canonical_json_hash({"request": 1}),
                prompt,
            )
        )


async def test_completed_effect_is_reused_across_proxy_restart():
    h = Harness()
    first = await h.invoke()
    second = await h.invoke()
    assert first == second
    assert first.outcome == "completed"
    assert (h.create_count, h.recover_count, h.settle_count) == (1, 0, 1)
    assert json.loads(h.blobs["model_request"])["prompt"] == "Evaluate this work"


async def test_invalid_prompt_cannot_consume_grant_store_bytes_or_reserve_spend():
    h = Harness()
    reply = await h.invoke("")
    assert reply.failure_code == "model_request_invalid"
    assert h.state == "prepared"
    assert h.request_sha is None
    assert h.events == []
    assert h.blobs == {}
    assert h.create_count == 0


async def test_crash_before_provider_identity_commit_retains_one_paid_effect():
    h = Harness()

    async def crash_before_reference(*_args, **_kwargs):
        raise RuntimeError("controlled process loss before provider identity commit")

    h.mark_uncertain = crash_before_reference
    with pytest.raises(RuntimeError, match="controlled process loss"):
        await h.invoke()
    assert h.state == "dispatching"
    assert h.provider_id is None
    assert h.create_count == 1
    assert (await h.invoke()).outcome == "unavailable"
    assert (h.create_count, h.recover_count, h.settle_count) == (1, 0, 0)


async def test_lease_loss_during_cached_art_read_denies_output_but_preserves_effect():
    h = Harness()
    original = await h.invoke()
    read_response = h.read_response

    async def lose_lease_while_reading(*args):
        data = await read_response(*args)
        h.stale = True
        return data

    h.read_response = lose_lease_while_reading
    assert (await h.invoke()).outcome == "unavailable"
    assert (h.create_count, h.settle_count) == (1, 1)
    h.read_response, h.stale = read_response, False
    assert await h.invoke() == original
    assert (h.create_count, h.settle_count) == (1, 1)


@pytest.mark.parametrize("known_id", [True, False])
async def test_lost_create_response_never_creates_again(known_id):
    h = Harness()
    h.create_result = CheckerModelCreateResult(
        CheckerModelCreateOutcome.UNCERTAIN,
        known_response=h.reference if known_id else None,
        failure=CheckerModelCreateFailure.DELIVERY_UNCERTAIN,
    )
    assert (await h.invoke()).outcome == "unavailable"
    assert h.state == "uncertain"
    retried = await h.invoke()
    assert retried.outcome == ("completed" if known_id else "unavailable")
    assert h.create_count == 1
    assert h.recover_count == int(known_id)
    assert h.settle_count == int(known_id)


async def test_budget_denial_never_reaches_provider():
    h = Harness()
    h.budget_available = False
    assert (await h.invoke()).outcome == "unavailable"
    assert h.create_count == h.recover_count == h.settle_count == 0
    assert h.state == "prepared"


async def test_changed_prompt_is_not_a_new_paid_call():
    h = Harness()
    assert (await h.invoke()).outcome == "completed"
    assert (await h.invoke("Different work")).outcome == "unavailable"
    assert h.create_count == h.settle_count == 1


async def test_missing_usage_retains_uncertain_effect_for_later_recovery():
    h = Harness()
    h.create_result = CheckerModelCreateResult(
        CheckerModelCreateOutcome.ACCEPTED,
        known_response=h.reference,
        observation=CheckerModelObservation(
            reference=h.reference,
            provider_model=h.profile.spec.model_snapshot,
            status=CheckerModelProviderStatus.FAILED,
        ),
    )
    assert (await h.invoke()).outcome == "unavailable"
    assert h.state == "uncertain" and h.settle_count == 0
    assert "model_response" not in h.blobs
    assert (await h.invoke()).outcome == "completed"
    assert h.create_count == h.settle_count == 1


async def test_stale_invocation_cannot_read_a_completed_effect():
    h = Harness()
    h.stale = True
    assert (await h.invoke()).outcome == "unavailable"
    assert h.state == "completed" and h.settle_count == 1
    h.stale = False
    assert (await h.invoke()).outcome == "completed"
    assert h.create_count == 1
