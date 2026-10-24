"""Exact terminal AUTH and settlement custody for shared model effects."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.model_usage.api import ModelCallUsage, model_retry_terminal_digest
from app.modules.model_usage.models import ModelUsageBudgetAccount
from tests.checkers_model_calls.model_usage_pg_support import (
    DatabaseFacts,
    model_database as _model_database,
)
from tests.checkers_model_calls.model_usage_boundary_support import (
    BoundaryPorts,
    DatabaseBoundaryPorts,
)
from tests.checkers_model_calls.test_model_call_transactions_postgresql import (
    evidence,
    prepare_and_reserve,
    provision,
    service,
    setup_service,
    setup_slot_key,
    sha,
)

model_database = _model_database


async def test_known_failed_settles_once_and_allows_authorized_child(
    model_database: DatabaseFacts,
) -> None:
    ports = BoundaryPorts()
    reservation = 100 * 11 + 50 * 29
    profile = await provision(model_database, ports, limit=reservation * 2)
    _, paid_slot, prepared, dispatched, _ = await prepare_and_reserve(
        model_database, ports, profile, "model_known_failure"
    )
    usage = ModelCallUsage(
        input_tokens=22,
        cached_input_tokens=2,
        output_tokens=3,
        reasoning_tokens=1,
    )
    response_art = evidence("failed-response", sha("failed-response"))
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = service(session, ports)
            failed = await owner.complete_known_failure(
                dispatched.effect,
                provider_response_id="resp_terminal_failure",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            replay = await owner.complete_known_failure(
                dispatched.effect,
                provider_response_id="resp_terminal_failure",
                provider_model_snapshot=profile.spec.model_snapshot,
                response_evidence=response_art,
                usage=usage,
            )
            assert replay.replayed
            child = await owner.prepare_recovery_child(
                paid_slot,
                registry_entry_id=model_database.registry_entry_id,
                parent_attempt_id=prepared.attempt_id,
                terminal_digest=model_retry_terminal_digest(failed),
                request_sha256=prepared.request_sha256,
            )
            assert child.attempt_number == 2
            account = await session.get(ModelUsageBudgetAccount, str(model_database.project_id))
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == failed.settled_nanodollars


@pytest.mark.parametrize("substitution", ("project", "effect", "action", "actor", "digest"))
async def test_known_failed_rejects_substituted_terminal_authority(
    model_database: DatabaseFacts,
    substitution: str,
) -> None:
    """A shape-valid receipt cannot terminalize any other effect or service scope."""
    ports = BoundaryPorts(terminal_receipt_change=substitution)
    profile = await provision(model_database, ports, limit=10_000)
    _, _, _, dispatched, _ = await prepare_and_reserve(
        model_database,
        ports,
        profile,
        "model_terminal_authority_" + substitution,
    )
    with pytest.raises(DBAPIError, match="invalid known-failed checker model call"):
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                await service(session, ports).complete_known_failure(
                    dispatched.effect,
                    provider_response_id="resp_terminal_authority_" + substitution,
                    provider_model_snapshot=profile.spec.model_snapshot,
                    response_evidence=evidence(
                        "terminal-authority-" + substitution,
                        sha("terminal-authority-" + substitution),
                    ),
                    usage=ModelCallUsage(
                        input_tokens=22,
                        cached_input_tokens=2,
                        output_tokens=3,
                        reasoning_tokens=1,
                    ),
                )


@pytest.mark.parametrize("substitution", ("project", "effect", "action", "actor", "digest"))
async def test_setup_known_failure_rejects_substituted_terminal_authority(
    model_database: DatabaseFacts,
    substitution: str,
) -> None:
    """Setup terminal custody rejects every crossed project, effect or service receipt."""
    ports = BoundaryPorts(terminal_receipt_change=substitution)
    profile = await provision(model_database, ports, limit=10_000)
    key = await setup_slot_key(model_database, profile)
    request_sha = sha("setup-terminal-authority-" + substitution)
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        async with session.begin():
            owner = setup_service(session, ports)
            prepared = await owner.prepare(key, request_sha)
            dispatched = await owner.reserve_dispatch(
                prepared,
                evidence("setup-terminal-request-" + substitution, request_sha),
            )
    with pytest.raises(DBAPIError, match="invalid known-failed checker model call"):
        async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
            async with session.begin():
                await setup_service(session, ports).complete(
                    dispatched.effect,
                    provider_response_id="resp_setup_terminal_" + substitution,
                    provider_model_snapshot=profile.spec.model_snapshot,
                    response_evidence=evidence(
                        "setup-terminal-response-" + substitution,
                        sha("setup-terminal-response-" + substitution),
                    ),
                    usage=ModelCallUsage(
                        input_tokens=22,
                        cached_input_tokens=2,
                        output_tokens=3,
                        reasoning_tokens=1,
                    ),
                    usable=False,
                )


async def test_known_failed_rejects_distinct_settlement_authority(
    model_database: DatabaseFacts,
) -> None:
    """Settlement must use the exact terminal decision, not a second allowed receipt."""
    ports = BoundaryPorts()
    profile = await provision(model_database, ports, limit=10_000)
    _, _, _, dispatched, _ = await prepare_and_reserve(
        model_database,
        ports,
        profile,
        "model_terminal_settlement_authority",
    )
    response = evidence("settlement-authority", sha("settlement-authority"))
    usage = ModelCallUsage(
        input_tokens=22,
        cached_input_tokens=2,
        output_tokens=3,
        reasoning_tokens=1,
    )
    terminal_digest = canonical_json_hash(
        {
            "status": "known_failed",
            "provider_response_id": "resp_settlement_authority",
            "provider_model_snapshot": profile.spec.model_snapshot,
            "response_evidence": response.model_dump(mode="json"),
            "usage": usage.model_dump(mode="json"),
        }
    )
    async with AsyncSession(model_database.engine, expire_on_commit=False) as session:
        boundaries = DatabaseBoundaryPorts(session, ports)
        with pytest.raises(DBAPIError, match="invalid known-failed checker model call"):
            async with session.begin():
                terminal = await boundaries.authorize_complete(
                    dispatched.effect, response, terminal_digest
                )
                settlement = await boundaries.authorize_complete(
                    dispatched.effect, response, terminal_digest
                )
                await boundaries.require_response(dispatched.effect.attempt_id, response)
                await session.execute(
                    text(
                        "update model_usage_effects set state='known_failed',"
                        "provider_response_id='resp_settlement_authority',"
                        "response_binding_id=:binding,response_content_id=:content,"
                        "response_put_attempt_id=:put,"
                        "response_verification_receipt_id=:receipt,"
                        "response_content_sha256=:sha,response_byte_count=:bytes,"
                        "input_tokens=:input,cached_input_tokens=:cached,"
                        "output_tokens=:output,reasoning_tokens=:reasoning,"
                        "settled_nanodollars=:cost,"
                        "terminal_authorization_evidence_id=:terminal,"
                        "settlement_authorization_evidence_id=:settlement,"
                        "terminal_at=clock_timestamp(),settled_at=clock_timestamp() "
                        "where id=:effect"
                    ),
                    {
                        "binding": response.binding_id,
                        "content": response.content_id,
                        "put": response.put_attempt_id,
                        "receipt": response.verification_receipt_id,
                        "sha": response.content_sha256,
                        "bytes": response.byte_count,
                        "input": usage.input_tokens,
                        "cached": usage.cached_input_tokens,
                        "output": usage.output_tokens,
                        "reasoning": usage.reasoning_tokens,
                        "cost": 311,
                        "terminal": terminal.evidence_id,
                        "settlement": settlement.evidence_id,
                        "effect": dispatched.effect.attempt_id,
                    },
                )
