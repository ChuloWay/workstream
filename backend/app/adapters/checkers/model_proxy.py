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
from app.modules.model_usage.api import (
    ModelCallEffectAuthorityFacts,
    ModelCallEvidence,
    ModelCallBudgetUnavailable,
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


def _unavailable(
    code: str,
    call_index: int,
    *,
    session_exhausted: bool = True,
) -> ModelProxyReply:
    return ModelProxyReply(
        outcome="unavailable",
        output=None,
        receipt_digest=None,
        failure_code=code,
        call_index=call_index,
        session_exhausted=session_exhausted,
    )


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
        except ModelCallBudgetUnavailable:
            return _unavailable("model_budget_unavailable", request.call_index)
        except (ModelCallUnavailable, CheckerOutputUnavailable):
            return _unavailable("model_call_unavailable", request.call_index)

    async def _handle(self, request: ModelProxyRequest) -> ModelProxyReply:
        resolved_receipts = [
            {
                "receipt_sha256": receipt.receipt_sha256,
                "receipt": json.loads(receipt.canonical_receipt_utf8),
            }
            for receipt in request.resolved_receipts
        ]
        data = _canonical_bytes(
            {
                "schema_version": "workstream.model_session_call.v2",
                "call_index": request.call_index,
                "prompt": request.prompt,
                "resolved_receipts": resolved_receipts,
            }
        )
        # The trusted relay resolves opaque handles; providers receive the exact retained
        # facts, never image-authored receipt claims.  Keep the ordinary prompt unchanged
        # for calls without tools while using one closed envelope when receipts are present.
        provider_prompt = request.prompt
        if resolved_receipts:
            provider_prompt = _canonical_bytes(
                {
                    "schema_version": "workstream.model_prompt_with_receipts.v1",
                    "prompt": request.prompt,
                    "trusted_receipts": resolved_receipts,
                }
            ).decode("utf-8")
        try:
            provider_request = CheckerModelRequest(provider_prompt)
        except ValueError:
            return _unavailable("model_request_invalid", request.call_index)
        request_sha = _sha(data)
        async with self._sessions() as session, session.begin():
            authority = await self._authorization(session, uuid4())
            grants = self._grants(session, authority)
            facts = await grants.resolve(request.grant_id, request.request_digest)
            paid_slot = facts.slot.model_copy(update={"slot_index": request.call_index})
            profile = await self._profiles(session).read_exact(
                ModelProfileSelector(
                    profile_id=facts.slot.profile_id,
                    profile_version=facts.slot.profile_version,
                    profile_digest=facts.slot.profile_digest,
                ),
                project_id=facts.slot.project_id,
            )
            receipt_bytes = sum(
                len(receipt.canonical_receipt_utf8.encode("utf-8"))
                for receipt in request.resolved_receipts
            )
            if (
                request.call_index >= profile.spec.maximum_calls
                or len(request.resolved_receipts) > profile.spec.maximum_tool_calls
                or receipt_bytes > profile.spec.maximum_tool_output_bytes
            ):
                return _unavailable("model_session_exhausted", request.call_index)
            if max(len(data), len(provider_prompt.encode("utf-8"))) > (
                profile.spec.maximum_request_bytes
            ):
                return _unavailable("model_request_too_large", request.call_index)
            attached = await self._calls(session, authority).prepare_attempt(
                facts.execution,
                paid_slot,
                registry_entry_id=facts.registry_entry_id,
                request_sha256=request_sha,
            )
            await grants.consume_prepared(
                facts,
                call_index=request.call_index,
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
            return await self._cached(facts, effect, profile, request.call_index)
        if attached.state in {"known_failed", "known_no_effect"}:
            return _unavailable("model_call_operator_recovery_required", request.call_index)
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
                    return await self._cached(facts, effect, profile, request.call_index)
            deadline = asyncio.get_running_loop().time() + profile.spec.deadline_ms / 1000
            if dispatch is not None and not dispatch.replayed:
                try:
                    created = await asyncio.wait_for(
                        provider.create(provider_request),
                        timeout=max(0.001, deadline - asyncio.get_running_loop().time()),
                    )
                except TimeoutError:
                    await self._record_reference(effect, None)
                    return _unavailable("model_provider_delivery_uncertain", request.call_index)
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
                    return _unavailable("model_provider_no_effect", request.call_index)
                reference = created.known_response
                await self._record_reference(effect, reference)
                if created.outcome is CheckerModelCreateOutcome.UNCERTAIN:
                    return _unavailable("model_provider_delivery_uncertain", request.call_index)
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
                        return _unavailable("model_provider_usage_unavailable", request.call_index)
                    return await self._complete(
                        facts, effect, profile, observation, request.call_index
                    )
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return _unavailable("model_provider_pending", request.call_index)
                await asyncio.sleep(min(1, remaining))
                try:
                    recovered = await asyncio.wait_for(
                        provider.recover(reference),
                        timeout=max(0.001, deadline - asyncio.get_running_loop().time()),
                    )
                except TimeoutError:
                    return _unavailable("model_provider_pending", request.call_index)
                if recovered.outcome is not CheckerModelRecoveryOutcome.OBSERVED:
                    return _unavailable(
                        "model_provider_recovery_unavailable", request.call_index
                    )
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

    async def _complete(
        self, facts, effect, profile, observation, call_index: int
    ) -> ModelProxyReply:
        """Record authenticated terminal evidence before settling once, including late results."""
        data = _canonical_bytes(
            {
                "schema_version": "workstream.checker_model_response.v1",
                "observation": asdict(observation),
            }
        )
        if len(data) > profile.spec.maximum_response_bytes:
            return _unavailable("model_response_too_large", call_index)
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
            return _unavailable("model_provider_failed", call_index)
        # Fresh current-run attachment gates image access; late completion itself remains retained.
        return await self._cached(facts, effect, profile, call_index)

    async def _cached(self, facts, effect, profile, call_index: int) -> ModelProxyReply:
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
        return ModelProxyReply(
            outcome="completed",
            output=output,
            receipt_digest=receipt,
            failure_code=None,
            call_index=call_index,
            session_exhausted=call_index + 1 >= profile.spec.maximum_calls,
        )
