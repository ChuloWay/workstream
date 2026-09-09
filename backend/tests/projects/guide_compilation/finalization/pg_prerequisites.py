"""Real compiled/projected parents; finalization authority stays a strict test port."""

from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
from dataclasses import asdict, replace
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    ProjectGuideCompilationRequestFacts,
    project_guide_compilation_execute_resource_digest,
)
from app.modules.authorization.guide_compilation import ProjectGuideCompilationAuthorizationAdapter
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.projects.api import (
    ProjectGuideProjectionCommand,
    ProjectGuideSetupFinalizationCommand,
)
from app.modules.projects.guide_compilation.contracts import accepted_compilation_result
from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
from app.modules.projects.guide_compilation.service import GuideCompilationService
from ..helpers import (
    context,
    identity,
    insert_authorization_evidence,
    persistence_facts,
    result,
    service_actor,
)


async def request_compilation(factory, values, compilation_context, predecessor_id):
    """Exercise real human request authority using a narrowly seeded project manager."""
    human, link, grant = uuid4(), uuid4(), uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "insert into actor_profiles(id,actor_kind,status,provisioning_method,created_by) "
                "values(:id,'human','active','automatic_first_access','test')"
            ),
            {"id": str(human)},
        )
        await session.execute(
            text(
                "insert into actor_identity_links(id,actor_profile_id,issuer,subject,subject_kind,"
                "status,linked_by,last_verified_at) values(:id,:actor,'https://identity.flowresearch.tech',:subject,"
                "'human','active','test',:now)"
            ),
            {"id": str(link), "actor": str(human), "subject": str(human), "now": datetime.now(UTC)},
        )
        await session.execute(text("alter table admin_role_grants disable trigger user"))
        await session.execute(
            text(
                "insert into admin_role_grants(id,target_actor_profile_id,role,scope_type,scope_project_id,"
                "status,version,granted_by_system_principal,grant_reason) values(:id,:actor,'project_manager','project',"
                ":project,'active',1,'workstream:system:bootstrap','finalization fixture')"
            ),
            {"id": grant, "actor": str(human), "project": str(values["project"])},
        )
        await session.execute(text("alter table admin_role_grants enable trigger user"))
    actor = ActorIdentityFacts(human, link, ActorKind.HUMAN)
    ctx = HumanAuthorizationContext(
        actor_profile_id=human,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=link,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    attempt_identity = identity(compilation_context)
    all_facts = asdict(
        persistence_facts(values, uuid4(), attempt_identity, predecessor_id=predecessor_id)
    )
    facts = ProjectGuideCompilationRequestFacts(
        **{
            name: all_facts[name]
            for name in ProjectGuideCompilationRequestFacts.__dataclass_fields__
        }
    )
    async with factory() as session:
        repository = AdminAuthorizationRepository(session)
        kernel = AuthorizationService(session, ctx, admin_repository=repository)
        prepared = PreparedAuthorizationService(session, ctx, kernel, repository)
        return await GuideCompilationService(
            session, ProjectGuideCompilationAuthorizationAdapter(kernel, prepared)
        ).authorize_request(origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"), actor=actor, facts=facts, identity=attempt_identity)


async def compilation_and_projections(
    url,
    factory,
    values,
    *,
    classification="draft_ready",
    project=True,
    compilation_context=None,
    predecessor_id=None,
):
    """Persist one accepted compilation with real custody guards and real projection adapters."""
    compilation_context = compilation_context or context(values)
    requested = await request_compilation(factory, values, compilation_context, predecessor_id)
    outcome = result()
    if classification != "draft_ready":
        patch = {
            "status": classification,
            "findings": (
                outcome.findings[0].model_copy(
                    update={
                        "severity": "blocking_gap"
                        if classification == "guide_blocked"
                        else "warning"
                    }
                ),
            ),
        }
        if classification == "guide_blocked":
            patch.update(
                submission_artifact_policy=None,
                requirements=(),
                pre_submit_bindings=(),
                post_submit_bindings=(),
                capability_suggestions=(),
            )
        outcome = outcome.model_copy(update=patch)
    async with factory() as session, session.begin():
        await GuideCompilationRepository(session).accept_result(
            attempt_id=requested.attempt_id, context=compilation_context, result=outcome
        )
    accepted = accepted_compilation_result(outcome)
    facts = persistence_facts(
        values, requested.attempt_id, identity(compilation_context), predecessor_id=predecessor_id
    )
    hashes = accepted.component_hashes
    facts = replace(
        facts,
        result_hash=accepted.result_hash,
        sufficiency_component_hash=hashes.sufficiency_hash,
        artifact_policy_component_hash=hashes.artifact_policy_hash,
        requirement_inventory_component_hash=hashes.requirement_inventory_hash,
        pre_submit_policy_component_hash=hashes.pre_submit_hash,
        post_submit_policy_component_hash=hashes.post_submit_hash,
        capability_suggestions_component_hash=hashes.capability_suggestions_hash,
        setup_notes_component_hash=hashes.setup_notes_hash,
    )
    facts = replace(
        facts,
        resource_context_digest=project_guide_compilation_execute_resource_digest(
            service_actor(values), facts
        ),
    )
    decision = await insert_authorization_evidence(
        url, values, requested.attempt_id, resource_context_digest=facts.resource_context_digest
    )
    async with factory() as session, session.begin():
        compilation = await GuideCompilationRepository(session).persist_accepted(
            attempt_id=requested.attempt_id,
            context=compilation_context,
            expected_predecessor_id=predecessor_id,
            actor=service_actor(values),
            facts=facts,
            authorization_decision_event_id=decision,
        )
    if project:
        projections = GuideCompilationProjectionService(
            factory,
            material_factory=SqlAlchemyGuideSufficiencyMaterialAdapter,
            sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
            policy_authorization_factory=artifact_policy_projection_authorization,
        )
        command = ProjectGuideProjectionCommand(attempt_id=requested.attempt_id)
        await projections.project_guide_sufficiency(command)
        if classification != "guide_blocked":
            await projections.project_submission_artifact_policy(command)
    return ProjectGuideSetupFinalizationCommand(
        project_id=values["project"],
        guide_id=values["guide"],
        setup_run_id=compilation_context.setup_run_id,
        setup_generation=compilation_context.setup_generation,
        compilation_id=compilation.id,
    )
