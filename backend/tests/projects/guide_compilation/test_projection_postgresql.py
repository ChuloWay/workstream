"""Real PostgreSQL proofs for hidden unified-compilation projections."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
from app.core.identifiers import new_record_id

from app.adapters.artifacts import (
    guide_document_manifest_port,
)
from app.modules.authorization.api import (
    ArtifactPolicyProjectionFacts,
    GuideSufficiencyProjectionFacts,
    ProjectGuideProjectionAuthorityReceipt,
    artifact_policy_projection_facts_digest,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_facts_digest,
    guide_sufficiency_projection_identity,
    projection_authority_digest,
)
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideProjectionCommand,
)
from app.modules.projects.guide_compilation.projections import (
    GuideCompilationProjectionService,
)

from .helpers import (
    seed_database,
    context,
    SOURCE_ITEM_ID,
    DOCUMENT_VERSION_ID,
    SOURCE_SHA256,
)
from .test_hidden_orchestrator_postgresql import (
    _Runtime,
    _authorized_attempt,
    _port,
)


class _PreparedProjection:
    def __init__(
        self,
        session: AsyncSession,
        actor_profile_id: UUID,
        identity_link_id: UUID,
        component: str,
        *,
        resource_type_override: str | None = None,
    ) -> None:
        self._session = session
        self._actor_profile_id = actor_profile_id
        self._identity_link_id = identity_link_id
        self._identity = None
        self._component = component
        self._resource_type_override = resource_type_override

    def identity(self, *, operation_id: UUID, correlation_id: UUID, output_id: UUID):
        factory = (
            guide_sufficiency_projection_identity
            if self._component == "guide_sufficiency"
            else artifact_policy_projection_identity
        )
        supplied = factory(
            operation_id=operation_id,
            correlation_id=correlation_id,
            output_id=output_id,
            actor_profile_id=self._actor_profile_id,
            identity_link_id=self._identity_link_id,
        )
        if self._identity is not None:
            assert supplied == self._identity
        self._identity = supplied
        return supplied

    def _bound_identity(self):
        assert self._identity is not None
        return self._identity

    async def consume_new(
        self, facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts
    ) -> ProjectGuideProjectionAuthorityReceipt:
        if self._component == "guide_sufficiency":
            facts_digest = guide_sufficiency_projection_facts_digest(facts)
            action = "project.guide_sufficiency.run"
            permission = "project.guide.manage"
            resource_type = "project_guide_sufficiency_projection"
        else:
            facts_digest = artifact_policy_projection_facts_digest(facts)
            action = "project.submission_artifact_policy.derive"
            permission = "project.effective_policy.manage"
            resource_type = "project_submission_artifact_policy_projection"
        identity = self._bound_identity()
        resource_digest = projection_authority_digest(
            component=self._component,
            identity=identity,
            project_id=facts.project_id,
            facts_digest=facts_digest,
        )
        event_id = new_record_id()
        await self._session.execute(
            text(
                "insert into audit_events(id,entity_type,entity_id,event_type,actor_id,"
                "actor_roles,claim_snapshot,auth_source,is_dev_auth,event_payload,"
                "event_domain,event_version,actor_ref_kind,request_id,correlation_id,"
                "permission_id,action_id,reason,project_id,resource_type,resource_id,"
                "after_facts) values(:id,'authorization_decision',:id,"
                "'SensitiveAuthorizationAllowed',:actor,'[]'::json,'{}'::json,"
                "'local_authority',false,'{}'::json,'authority',1,'actor_profile',"
                ":request_id,:correlation_id,:permission,:action,"
                "'authorization_evaluation',:project_id,:resource_type,:resource_id,"
                "jsonb_build_object('allowed',true,'resource_context_digest',"
                "cast(:resource_digest as text))::json)"
            ),
            {
                "id": str(event_id),
                "actor": str(identity.actor_profile_id),
                "request_id": str(identity.operation_id),
                "correlation_id": str(identity.correlation_id),
                "permission": permission,
                "action": action,
                "project_id": str(facts.project_id),
                "resource_type": self._resource_type_override or resource_type,
                "resource_id": str(identity.operation_id),
                "resource_digest": resource_digest,
            },
        )
        return ProjectGuideProjectionAuthorityReceipt(
            decision_event_id=event_id,
            actor_profile_id=identity.actor_profile_id,
            identity_link_id=identity.identity_link_id,
            service_identity=identity.service_identity,
            resource_context_digest=resource_digest,
        )

    async def validate_replay(
        self,
        facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts,
        stored_decision_id: UUID,
    ) -> None:
        identity = self._bound_identity()
        count = await self._session.scalar(
            text(
                "select count(*) from audit_events where id=:id and actor_id=:actor "
                "and project_id=:project"
            ),
            {
                "id": str(stored_decision_id),
                "actor": str(identity.actor_profile_id),
                "project": str(facts.project_id),
            },
        )
        if count != 1:
            raise AssertionError("stored authorization decision is unavailable")


class _ProjectionAuthorization:
    def __init__(
        self,
        session: AsyncSession,
        values: dict[str, UUID],
        *,
        resource_type_override: str | None = None,
    ) -> None:
        self._session = session
        self._values = values
        self._resource_type_override = resource_type_override

    @asynccontextmanager
    async def prepare_sufficiency_projection(self, locator):
        yield _PreparedProjection(
            self._session,
            self._values["actor"],
            self._values["link"],
            "guide_sufficiency",
            resource_type_override=self._resource_type_override,
        )

    @asynccontextmanager
    async def prepare_artifact_policy_projection(self, locator):
        yield _PreparedProjection(
            self._session,
            self._values["actor"],
            self._values["link"],
            "submission_artifact_policy",
            resource_type_override=self._resource_type_override,
        )


async def _persist_compilation(database_url: str, values: dict[str, UUID], *, outcome=None):
    requested = await _authorized_attempt(database_url, values)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(outcome) if outcome is not None else _Runtime()
    try:
        receipt = await _port(factory, runtime).execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
        )
        assert runtime.calls == 1
        return requested.attempt_id, receipt.compilation_id
    finally:
        await engine.dispose()


async def _project_both(database_url: str, values: dict[str, UUID]):
    attempt_id, compilation_id = await _persist_compilation(database_url, values)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    service = GuideCompilationProjectionService(
        factory,
        material_factory=guide_document_manifest_port,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
    )
    command = ProjectGuideProjectionCommand(attempt_id=attempt_id)
    try:
        sufficiency = await service.project_guide_sufficiency(command)
        sufficiency_replay = await service.project_guide_sufficiency(command)
        policy = await service.project_submission_artifact_policy(command)
        policy_replay = await service.project_submission_artifact_policy(command)
        return (
            attempt_id,
            compilation_id,
            sufficiency,
            sufficiency_replay,
            policy,
            policy_replay,
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_direct_projection_insert_binds_audit_correlation_to_row(
    clean_postgres_database: str,
) -> None:
    """Changing only row correlation must invalidate otherwise exact authority custody."""
    values = await seed_database(clean_postgres_database)
    attempt_id, _ = await _persist_compilation(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = GuideCompilationProjectionService(
        factory,
        material_factory=guide_document_manifest_port,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
    )
    try:
        await service.project_guide_sufficiency(
            ProjectGuideProjectionCommand(attempt_id=attempt_id)
        )
        async with factory() as session:
            transaction = await session.begin()
            try:
                await session.execute(
                    text(
                        "create temporary table saved_projection_operation on commit drop as "
                        "select * from project_guide_component_projection_operations "
                        "where component='guide_sufficiency'"
                    )
                )
                await session.execute(
                    text(
                        "alter table project_guide_component_projection_operations "
                        "disable trigger projection_operation_change_guard"
                    )
                )
                await session.execute(
                    text(
                        "delete from project_guide_component_projection_operations "
                        "where component='guide_sufficiency'"
                    )
                )
                await session.execute(
                    text(
                        "alter table project_guide_component_projection_operations "
                        "enable trigger projection_operation_change_guard"
                    )
                )
                # Positive control: the exact retained row still satisfies every guard.
                await session.execute(
                    text(
                        "insert into project_guide_component_projection_operations "
                        "select * from saved_projection_operation"
                    )
                )
                await session.execute(
                    text(
                        "alter table project_guide_component_projection_operations "
                        "disable trigger projection_operation_change_guard"
                    )
                )
                await session.execute(
                    text("delete from project_guide_component_projection_operations")
                )
                await session.execute(
                    text(
                        "alter table project_guide_component_projection_operations "
                        "enable trigger projection_operation_change_guard"
                    )
                )
                await session.execute(
                    text("update saved_projection_operation set correlation_id=:correlation"),
                    {"correlation": new_record_id()},
                )
                with pytest.raises(
                    SQLAlchemyError, match="projection authority custody is invalid"
                ):
                    async with session.begin_nested():
                        await session.execute(
                            text(
                                "insert into project_guide_component_projection_operations "
                                "select * from saved_projection_operation"
                            )
                        )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_projects_both_components_once_and_replays_without_new_effects(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    (
        _attempt_id,
        compilation_id,
        sufficiency,
        sufficiency_replay,
        policy,
        policy_replay,
    ) = await _project_both(
        clean_postgres_database,
        values,
    )
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        assert sufficiency.disposition == "projected"
        assert sufficiency_replay.disposition == "replayed"
        assert policy.disposition == "projected"
        assert policy_replay.disposition == "replayed"
        assert sufficiency_replay.output_id == sufficiency.output_id
        assert policy_replay.output_id == policy.output_id

        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select "
                        "(select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from project_guide_document_accesses),"
                        "(select count(*) from submission_artifact_policies),"
                        "(select count(*) from project_guide_component_projection_operations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_sufficiency.run'),"
                        "(select count(*) from audit_events where action_id="
                        "'project.submission_artifact_policy.derive')"
                    )
                )
            ).one()
            setup = (
                await session.execute(
                    text(
                        "select status,current_step,output_sufficiency_report_id,"
                        "output_submission_artifact_policy_id,"
                        "output_post_submit_checker_policy_id from project_setup_runs "
                        "where id=:id"
                    ),
                    {"id": str(values["setup_1"])},
                )
            ).one()
            rows = (
                await session.execute(
                    text(
                        "select component,compilation_id,output_id,output_digest "
                        "from project_guide_component_projection_operations "
                        "order by component"
                    )
                )
            ).all()
            usage = (
                (
                    await session.execute(
                        text("select * from project_guide_document_accesses")
                    )
                )
                .mappings()
                .one()
            )
            expected_usage = {
                "source_item_id": SOURCE_ITEM_ID,
                "document_version_id": DOCUMENT_VERSION_ID,
                "manifest_sha256": context(values).material.sha256,
                "sha256": SOURCE_SHA256,
            }
            assert {key: usage[key] for key in expected_usage} == expected_usage
            material = context(values).material
            report = (
                await session.execute(
                    text(
                        "select agent_material_sha256,agent_material_byte_count from guide_sufficiency_reports"
                    )
                )
            ).one()
            assert report == (material.sha256, len(material.model_dump_json().encode("utf-8")))
            await session.rollback()

        assert counts == (1, 1, 1, 2, 1, 1)
        assert setup == ("queued", "queued", None, None, None)
        assert {row.compilation_id for row in rows} == {compilation_id}
        assert {row.output_id for row in rows} == {
            sufficiency.output_id,
            policy.output_id,
        }
        assert {row.output_digest for row in rows} == {
            sufficiency.output_digest,
            policy.output_digest,
        }
    finally:
        await engine.dispose()
