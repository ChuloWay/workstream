"""Durable model-call orchestration for project-owned checker images."""

import asyncio
from contextlib import AbstractAsyncContextManager
from collections.abc import Callable
from dataclasses import asdict
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select, func

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.checker_model_provider import (
    CheckerModelCreateOutcome,
    CheckerModelProvider,
    CheckerModelProviderStatus,
    CheckerModelRecoveryOutcome,
    CheckerModelRequest,
    CheckerModelResponseReference,
)
from app.interfaces.checker_model_proxy import ModelProxyRequest, ModelProxyReply
from app.modules.checkers.api.model_calls import (
    ModelCallEffectAuthorityFacts,
    ModelCallEvidence,
    ModelCallUsage,
    ModelCallUnavailable,
    ModelProfileSelector,
    PreparedModelCallAttempt,
    KnownNoEffectProof,
    ProjectModelProfile,
)
from app.modules.checkers.api.output_custody import (
    CheckerArtifactOutputPort,
    CheckerOutputArtifactRequest,
    CheckerOutputBindingRequest,
    CheckerOutputSelector,
    CheckerOutputUnavailable,
)


def _canonical_bytes(value: object) -> bytes:
    """Serialize exact bounded private evidence without logging its contents."""
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _unavailable(code: str) -> ModelProxyReply:
    return ModelProxyReply("unavailable", None, None, code)


class CheckerModelProxy:
    """Persist intent before provider I/O and recover the original effect across runs."""

    def __init__(
        self,
        *,
        sessions,
        authorization,
        grants,
        calls,
        profiles,
        outputs: CheckerArtifactOutputPort,
        bindings,
        provider: Callable[
            [ProjectModelProfile], AbstractAsyncContextManager[CheckerModelProvider]
        ],
    ):
        self._sessions, self._authorization = sessions, authorization
        self._grants, self._calls, self._profiles = grants, calls, profiles
        self._outputs, self._bindings, self._provider = outputs, bindings, provider

    async def handle(self, request: ModelProxyRequest) -> ModelProxyReply:
        """Consume one invocation capability; failed infrastructure never becomes a verdict."""
        try:
            return await self._handle(request)
        except (ModelCallUnavailable, CheckerOutputUnavailable):
            return _unavailable("model_call_unavailable")

    async def _handle(self, request: ModelProxyRequest) -> ModelProxyReply:
        # Reject malformed bytes before consuming invocation custody or reserving spend.
        try:
            provider_request = CheckerModelRequest(request.prompt)
        except ValueError:
            return _unavailable("model_request_invalid")
        data = _canonical_bytes(
            {
                "schema_version": "workstream.checker_model_request.v1",
                "prompt": request.prompt,
            }
        )
        request_sha = _sha(data)
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, uuid4())
            grants = self._grants(session, authority)
            facts = await grants.resolve(request.grant_id, request.request_digest)
            profile = await self._profiles(session).read_exact(
                ModelProfileSelector(
                    profile_id=facts.slot.profile_id,
                    profile_version=facts.slot.profile_version,
                    profile_digest=facts.slot.profile_digest,
                ),
                project_id=facts.slot.project_id,
                registry_entry_id=facts.registry_entry_id,
                registry_entry_digest=facts.slot.registry_entry_digest,
            )
            if len(data) > profile.spec.maximum_request_bytes:
                return _unavailable("model_request_too_large")
            attached = await self._calls(session, authority).prepare_attempt(
                facts.execution,
                facts.slot,
                registry_entry_id=facts.registry_entry_id,
                request_sha256=request_sha,
            )
            await grants.consume_prepared(
                facts,
                request_sha256=request_sha,
                prepared_attempt_id=attached.attempt_id,
            )
        effect = ModelCallEffectAuthorityFacts(
            project_id=facts.execution.project_id,
            task_id=facts.execution.task_id,
            slot_id=attached.slot_id,
            slot_key=attached.slot_key,
            attempt_id=attached.attempt_id,
            internal_call_request_id=attached.internal_call_request_id,
        )
        if attached.state == "completed":
            return await self._cached(facts, effect)
        if attached.state in {"known_failed", "known_no_effect"}:
            return _unavailable("model_call_operator_recovery_required")
        async with self._provider(profile) as provider:
            dispatch = None
            if attached.state == "prepared":
                prepared = PreparedModelCallAttempt.model_validate(attached.model_dump())
                request_evidence = await self._store(facts, effect, "model_request", data)
                async with self._sessions() as session, session.begin():
                    authority = await self._authorization(
                        session, facts.execution.evaluation_request_id
                    )
                    dispatch = await self._calls(session, authority).reserve_dispatch(
                        facts.execution,
                        prepared,
                        request_evidence,
                    )
                if dispatch.state == "completed":
                    return await self._cached(facts, effect)
            deadline = asyncio.get_running_loop().time() + profile.spec.deadline_ms / 1000
            if dispatch is not None and not dispatch.replayed:
                try:
                    created = await asyncio.wait_for(
                        provider.create(provider_request),
                        timeout=max(0.001, deadline - asyncio.get_running_loop().time()),
                    )
                except TimeoutError:
                    await self._record_reference(effect, None)
                    return _unavailable("model_provider_delivery_uncertain")
                if created.outcome is CheckerModelCreateOutcome.NO_EFFECT:
                    async with self._sessions() as session, session.begin():
                        authority = await self._authorization(
                            session, effect.internal_call_request_id
                        )
                        proof = KnownNoEffectProof(
                            proof_id=new_record_id(),
                            proof_digest=canonical_json_hash(
                                {
                                    "attempt_id": str(effect.attempt_id),
                                    "provider_outcome": created.outcome.value,
                                    "failure_code": created.failure.value,
                                }
                            ),
                            observed_at=await session.scalar(select(func.clock_timestamp())),
                        )
                        await self._calls(session, authority).mark_known_no_effect(effect, proof)
                    return _unavailable("model_provider_no_effect")
                reference = created.known_response
                await self._record_reference(effect, reference)
                if created.outcome is CheckerModelCreateOutcome.UNCERTAIN:
                    return _unavailable("model_provider_delivery_uncertain")
                observation = created.observation
            else:
                async with self._sessions() as session, session.begin():
                    authority = await self._authorization(
                        session, facts.execution.evaluation_request_id
                    )
                    recovery = await self._calls(session, authority).attach_recovery(
                        facts.execution, effect
                    )
                reference = CheckerModelResponseReference(recovery.provider_response_id)
                observation = None
            while True:
                if observation is not None and observation.status not in {
                    CheckerModelProviderStatus.QUEUED,
                    CheckerModelProviderStatus.IN_PROGRESS,
                }:
                    if observation.usage is None:
                        return _unavailable("model_provider_usage_unavailable")
                    return await self._complete(facts, effect, profile, observation)
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return _unavailable("model_provider_pending")
                await asyncio.sleep(min(1, remaining))
                try:
                    recovered = await asyncio.wait_for(
                        provider.recover(reference),
                        timeout=max(0.001, deadline - asyncio.get_running_loop().time()),
                    )
                except TimeoutError:
                    return _unavailable("model_provider_pending")
                if recovered.outcome is not CheckerModelRecoveryOutcome.OBSERVED:
                    return _unavailable("model_provider_recovery_unavailable")
                observation = recovered.observation

    async def _record_reference(self, effect, reference) -> None:
        """Persist the provider identity before response storage or further polling."""
        provider_id = reference.provider_response_id if reference is not None else None
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, effect.internal_call_request_id)
            await self._calls(session, authority).mark_uncertain(
                effect,
                canonical_json_hash({"provider_response_id": provider_id}),
                provider_response_id=provider_id,
            )

    async def _store(self, facts, effect, role: str, data: bytes) -> ModelCallEvidence:
        """Use ART's existing prepare, immutable put, verification and binding pipeline."""
        selector = CheckerOutputSelector(
            paid_slot=effect.slot_key,
            task_id=facts.execution.task_id,
            model_call_slot_id=effect.slot_id,
            model_call_attempt_id=effect.attempt_id,
            slot_key=role,
            content_sha256=_sha(data),
            execution=facts.execution if role == "model_request" else None,
        )

        async def source():
            yield data

        stored = await self._outputs.store(CheckerOutputArtifactRequest(selector, source()))
        if stored.status != "verified" or stored.verification_receipt_id is None:
            raise ModelCallUnavailable("model_call_evidence_unavailable")
        async with self._sessions() as session, session.begin():
            binding = await self._bindings(session).bind_checker_output(
                CheckerOutputBindingRequest(
                    selector,
                    stored.put_attempt_id,
                    stored.verification_receipt_id,
                )
            )
        return ModelCallEvidence(
            binding_id=binding.binding_id,
            content_id=binding.content_id,
            put_attempt_id=binding.put_attempt_id,
            verification_receipt_id=binding.verification_receipt_id,
            content_sha256=selector.content_sha256,
            byte_count=len(data),
        )

    async def _complete(self, facts, effect, profile, observation) -> ModelProxyReply:
        """Record authenticated terminal evidence before settling once, including late results."""
        data = _canonical_bytes(
            {
                "schema_version": "workstream.checker_model_response.v1",
                "observation": asdict(observation),
            }
        )
        if len(data) > profile.spec.maximum_response_bytes:
            return _unavailable("model_response_too_large")
        evidence = await self._store(facts, effect, "model_response", data)
        raw_usage = observation.usage
        usage = ModelCallUsage(
            input_tokens=raw_usage.input_tokens,
            cached_input_tokens=raw_usage.cached_input_tokens,
            output_tokens=raw_usage.output_tokens,
            reasoning_tokens=raw_usage.reasoning_tokens,
        )
        usable = observation.status is CheckerModelProviderStatus.COMPLETED and bool(
            observation.output_text
        )
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, effect.internal_call_request_id)
            calls = self._calls(session, authority)
            operation = calls.complete if usable else calls.complete_known_failure
            await operation(
                effect,
                provider_response_id=observation.reference.provider_response_id,
                provider_model_snapshot=observation.provider_model,
                response_evidence=evidence,
                usage=usage,
            )
        if not usable:
            return _unavailable("model_provider_failed")
        # Fresh current-run attachment gates image access; late completion itself remains retained.
        return await self._cached(facts, effect)

    async def _cached(self, facts, effect) -> ModelProxyReply:
        """Reauthorize current invocation before releasing the original verified response."""
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, facts.execution.evaluation_request_id)
            completed = await self._calls(session, authority).attach_completed(
                facts.execution, effect
            )
        selector = CheckerOutputSelector(
            paid_slot=effect.slot_key,
            task_id=facts.execution.task_id,
            model_call_slot_id=effect.slot_id,
            model_call_attempt_id=effect.attempt_id,
            slot_key="model_response",
            content_sha256=completed.response_evidence.content_sha256,
        )
        data = await self._outputs.read_response(selector, completed.response_evidence)
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, facts.execution.evaluation_request_id)
            await self._calls(session, authority).attach_completed(facts.execution, effect)
        body = json.loads(data)
        if body.get("schema_version") != "workstream.checker_model_response.v1":
            raise ModelCallUnavailable("model_call_response_unavailable")
        output = body["observation"]["output_text"]
        receipt = canonical_json_hash(completed.model_dump(mode="json", exclude={"replayed"}))
        return ModelProxyReply("completed", output, receipt, None)
