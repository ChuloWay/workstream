"""Real predecessor upgrade proof for the false-only second-review invariant."""

import asyncio
from pathlib import Path
import runpy
from uuid import uuid4

from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.projects.api.policy_lineage import ReviewPolicySemantics
from app.modules.projects.policy_mutation_service import (
    NO_CURRENT_POLICY_ETAG,
    ProjectPolicyMutationService,
)
from app.modules.projects.schemas import ReviewPolicyInput, ReviewPolicyResponse
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config
from tests.projects.guide_activation.source_fixtures import source_case

pytestmark = pytest.mark.postgres_schema_contract


class _PreInvariantReviewPolicyResponse(ReviewPolicyResponse):
    """Decode the predecessor's once-permitted retained true value."""

    requires_second_review: bool


def _upgrade(connection) -> None:
    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[3]
            / "alembic/versions/0024_require_second_review_false.py"
        )
    )
    with Operations.context(MigrationContext.configure(connection)):
        migration["upgrade"]()


async def _seed_review_policy(factory, command_context, actor, *, retained_true: bool) -> None:
    async with factory() as session:
        resolved = ResolvedActor(
            await session.get(ActorProfile, str(actor.actor_profile_id)),
            await session.get(ActorIdentityLink, str(actor.identity_link_id)),
        )
        context = HumanAuthorizationContext(
            actor_profile_id=actor.actor_profile_id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=actor.identity_link_id,
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        repository = AdminAuthorizationRepository(session)
        kernel = AuthorizationService(session, context, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, context, kernel, repository)
        service = ProjectPolicyMutationService(session)
        values = ReviewPolicyInput(
            review_preference_window_seconds=3600,
            review_lease_duration_seconds=1800,
            allowed_decisions=["accept", "needs_revision", "reject"],
        ).model_dump()
        if retained_true:
            values["requires_second_review"] = True
            values["allowed_decisions"] = tuple(values["allowed_decisions"])
            values["minimum_finding_fields"] = tuple(values["minimum_finding_fields"])
            # Construct the exact predecessor semantics to create a committed
            # historical fact through the real writer, authority, and custody
            # transaction. Current validation is exercised separately.
            semantics = ReviewPolicySemantics.model_construct(**values)
            await service._replace(
                "review",
                resolved,
                prepared,
                uuid4(),
                NO_CURRENT_POLICY_ETAG,
                command_context.project_id,
                command_context.guide_id,
                semantics,
                _PreInvariantReviewPolicyResponse,
            )
        else:
            await service.replace_review_policy(
                resolved,
                prepared,
                uuid4(),
                NO_CURRENT_POLICY_ETAG,
                command_context.project_id,
                command_context.guide_id,
                ReviewPolicyInput.model_validate(values),
            )
        await session.commit()


async def _snapshot(connection) -> dict[str, object]:
    return {
        "policies": list(
            await connection.scalars(
                text(
                    "select to_jsonb(p) from public.review_policies p "
                    "order by policy_generation,id"
                )
            )
        ),
        "selectors": list(
            await connection.scalars(
                text(
                    "select jsonb_build_object("
                    "'id',id,'policy_id',selected_review_policy_id,"
                    "'generation',selected_review_policy_generation,"
                    "'hash',selected_review_policy_hash) "
                    "from public.project_guides order by id"
                )
            )
        ),
        "version": await connection.scalar(
            text("select version_num from public.alembic_version")
        ),
    }


async def test_upgrade_refuses_retained_true_without_changing_its_lineage(
    isolated_database_env,
    migration_lock,
) -> None:
    await db_session.dispose_engine()
    with migration_lock():
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(
            command.upgrade, _config(), "0023_remove_task_payment_policy"
        )
        async with source_case(isolated_database_env) as (
            _values,
            factory,
            command_context,
            actor,
            _grant,
        ):
            await _seed_review_policy(factory, command_context, actor, retained_true=True)
            async with factory.kw["bind"].connect() as connection, connection.begin():
                before = await _snapshot(connection)
                assert before["policies"][0]["requires_second_review"] is True
                with pytest.raises(
                    IntegrityError,
                    match="retained requires_second_review=true policy",
                ):
                    async with connection.begin_nested():
                        await connection.run_sync(_upgrade)
                assert await _snapshot(connection) == before


async def test_upgrade_installs_false_guard_without_changing_hash_or_lineage(
    isolated_database_env,
    migration_lock,
) -> None:
    await db_session.dispose_engine()
    with migration_lock():
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(
            command.upgrade, _config(), "0023_remove_task_payment_policy"
        )
        async with source_case(isolated_database_env) as (
            _values,
            factory,
            command_context,
            actor,
            _grant,
        ):
            await _seed_review_policy(factory, command_context, actor, retained_true=False)
            async with factory.kw["bind"].connect() as connection:
                before = await _snapshot(connection)
                await connection.rollback()
            await asyncio.to_thread(command.upgrade, _config(), "head")
            async with factory.kw["bind"].connect() as connection:
                after = await _snapshot(connection)
                constraint = await connection.scalar(
                    text(
                        "select pg_get_constraintdef(oid) from pg_constraint "
                        "where conrelid='public.review_policies'::regclass "
                        "and conname="
                        "'ck_review_policies_review_policy_second_review_disabled'"
                    )
                )
            assert before["policies"] == after["policies"]
            assert before["selectors"] == after["selectors"]
            assert before["version"] == "0023_remove_task_payment_policy"
            assert after["version"] == "0024_require_second_review_false"
            assert constraint == "CHECK ((NOT requires_second_review))"
