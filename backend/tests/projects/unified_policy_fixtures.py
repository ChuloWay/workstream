"""Arrange real unified projection, finalization and hidden manager approval."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.adapters.artifacts import guide_document_manifest_port
from app.adapters.auth import (
    artifact_policy_projection_authorization,
    guide_sufficiency_projection_authorization,
)
from app.db import session as db_session
from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.models import AdminRoleGrant
from app.modules.checkers.catalogue import (
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api import (
    ProjectGuideProjectionCommand,
    ProjectGuideSetupFinalizationCommand,
)
from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalSelection
from app.modules.projects.guide_compilation.models import ProjectGuideCompilation
from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    SubmissionArtifactPolicy,
)
from app.modules.projects.schemas import (
    EffectiveProjectSubmissionArtifactPolicyResponse,
    SubmissionArtifactPolicyResponse,
)
from committed_guide_fixtures import create_compiled_report_fixture
from tests.projects.guide_compilation.finalization.pg_support import finalize
from tests.projects.guide_compilation.proposals.pg_support import ProposalAuthority


def downstream_artifact_proposal():
    return SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000_000,
        maximum_package_size_bytes=5_000_000,
        required_artifacts=("outputs/answer.md",),
        required_evidence=("reasoning_trace",),
        forbidden_artifacts=("*.tmp",),
        attestation_terms=("project_specific_originality",),
    )


async def create_unified_submission_policy(report_id, snapshot_id, *, proposal=None):
    """Project the actual scripted result, with no manual policy row replacement."""
    sessions = db_session.get_session_factory()
    proposal = proposal or downstream_artifact_proposal()
    await create_compiled_report_fixture(
        report_id,
        snapshot_id,
        artifact_proposal=proposal,
    )
    async with sessions() as session:
        compilation = (
            await session.scalars(
                select(ProjectGuideCompilation).where(
                    ProjectGuideCompilation.source_snapshot_id == snapshot_id,
                )
            )
        ).one()
        service_actor, service_link = (
            await session.execute(
                select(ActorProfile.id, ActorIdentityLink.id)
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(
                    ActorProfile.service_identity == "workstream.project.setup",
                    ActorIdentityLink.status == "active",
                ),
            )
        ).one()
        command = ProjectGuideSetupFinalizationCommand(
            project_id=UUID(compilation.project_id),
            guide_id=UUID(compilation.guide_id),
            setup_run_id=UUID(compilation.setup_run_id),
            setup_generation=compilation.setup_generation,
            compilation_id=compilation.id,
        )
        assert compilation.canonical_result["submission_artifact_policy"] == proposal.model_dump(
            mode="json"
        )
    projections = GuideCompilationProjectionService(
        sessions,
        material_factory=guide_document_manifest_port,
        sufficiency_authorization_factory=guide_sufficiency_projection_authorization,
        policy_authorization_factory=artifact_policy_projection_authorization,
    )
    projected = await projections.project_submission_artifact_policy(
        ProjectGuideProjectionCommand(attempt_id=compilation.attempt_id),
    )
    await finalize(sessions, {"actor": UUID(service_actor), "link": UUID(service_link)}, command)
    async with sessions() as session:
        policy = await session.get(SubmissionArtifactPolicy, str(projected.output_id))
        return SubmissionArtifactPolicyResponse.model_validate(policy).model_dump(mode="json")


async def approve_unified_submission_policy(project_id, guide_id, policy_id):
    """Use strict hidden test authority and the real approval owner; no live route exists."""
    sessions = db_session.get_session_factory()
    async with sessions() as session:
        actor_id, link_id, grant_id = (
            await session.execute(
                select(ActorProfile.id, ActorIdentityLink.id, AdminRoleGrant.id)
                .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
                .join(AdminRoleGrant, AdminRoleGrant.target_actor_profile_id == ActorProfile.id)
                .where(
                    AdminRoleGrant.scope_project_id == project_id,
                    AdminRoleGrant.role == "project_manager",
                    AdminRoleGrant.status == "active",
                    ActorIdentityLink.status == "active",
                ),
            )
        ).one()
        compilation = (
            await session.scalars(
                select(ProjectGuideCompilation).where(
                    ProjectGuideCompilation.project_id == project_id,
                    ProjectGuideCompilation.guide_id == guide_id,
                )
            )
        ).one()
    actor = ActorIdentityFacts(UUID(actor_id), UUID(link_id), ActorKind.HUMAN)
    async with sessions() as session, session.begin():
        service = GuideProposalService(
            session, ProposalAuthority(session, actor, UUID(project_id), grant_id)
        )
        package = await service.review_package(
            GuideProposalSelection(
                project_id=project_id,
                guide_id=guide_id,
                compilation_id=compilation.id,
            ),
            actor=actor,
            request_id=uuid4(),
        )
    assert str(package.target.artifact_policy_id) == policy_id
    planner = build_pre_submission_checker_catalogue()
    async with sessions() as session, session.begin():
        receipt = await GuideProposalService(
            session,
            ProposalAuthority(
                session,
                actor,
                UUID(project_id),
                grant_id,
            ),
        ).approve(
            GuideProposalApproval(
                target=package.target,
                idempotency_key=uuid4(),
                acknowledged_warning_hashes=package.warning_hashes,
                expected_previous_approval_operation_id=package.current_approval_operation_id,
                expected_previous_approval_output_digest=package.current_approval_output_digest,
            ),
            actor=actor,
            request_id=uuid4(),
            material=guide_document_manifest_port(session),
            pre_capabilities=project_guide_pre_submission_capabilities(planner),
            post_capabilities=current_post_submit_catalogue(),
            planner=planner,
        )
    async with sessions() as session:
        effective = await session.get(
            EffectiveProjectSubmissionArtifactPolicy, str(receipt.effective_policy_id)
        )
        return EffectiveProjectSubmissionArtifactPolicyResponse.model_validate(
            effective
        ).model_dump(mode="json")
