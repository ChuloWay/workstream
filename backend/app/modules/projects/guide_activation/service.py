"""One hidden complete-guide activation operation in the caller root transaction."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.authorization.api import ActorKind
from app.modules.checkers.api.pre_submit import EffectivePreSubmissionPlanLineage
from app.modules.projects.api.guide_activation import (
    GuideActivationCommand,
    GuideActivationFacts,
    GuideActivationLocator,
    GuideActivationReceipt,
    GuideContributionPolicyFacts,
    PreparedGuideActivation,
)
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import PostPolicySelection
from app.modules.projects.guide_compilation.proposal_approval import require_catalogues
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.modules.projects.guide_mutation_repository import GuideMutationRepository
from app.modules.projects.post_policy.repository import PostPolicyRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.service import GuideActivationBlocked, ProjectService, ProjectServiceError

from .custody import ACTION, activation_custody, load_guide_activation, require_authority


class GuideActivationService:
    """Default-deny composition; AUTH-12H supplies a live nominal participant later."""

    def __init__(
        self, session, *, contribution, planner, pre_catalogue, post_catalogue, authorization=None
    ):
        self.session = session
        self.authorization = authorization
        self.contribution = contribution
        self.planner, self.pre_catalogue, self.post_catalogue = (
            planner,
            pre_catalogue,
            post_catalogue,
        )
        self.projects = ProjectRepository(session)
        self.replay = GuideMutationRepository(session)
        self.post = PostPolicyRepository(session)

    async def activate(
        self, command: GuideActivationCommand, *, actor, request_id: UUID
    ) -> GuideActivationReceipt:
        """Validate both approvals, consume exact authority, and commit no partial effects."""
        if (
            self.authorization is None
            or actor.actor_kind is not ActorKind.HUMAN
            or not self.session.in_transaction()
            or self.session.in_nested_transaction()
            or self.session.new
            or self.session.dirty
            or self.session.deleted
        ):
            raise GuideProposalError("authority_unavailable")
        command = GuideActivationCommand.model_validate(command.model_dump(mode="json"))
        target = command.target.proposal
        operation_id = uuid5(
            NAMESPACE_URL,
            f"workstream.guide.activate:{actor.actor_profile_id}:{command.idempotency_key}",
        )
        locator = GuideActivationLocator(
            project_id=target.project_id,
            guide_id=target.guide_id,
            actor_profile_id=actor.actor_profile_id,
            identity_link_id=actor.identity_link_id,
            operation_id=operation_id,
            request_id=request_id,
        )
        async with GuideProposalService._bounded_errors():
            # Enter full AUTH control/caller/link/grant scope before owner locks.
            async with self.authorization.lock_activation_scope(locator) as prepared:
                if not isinstance(prepared, PreparedGuideActivation):
                    raise GuideProposalError("authority_unavailable")
                project = await self.projects.get_project(str(target.project_id), for_update=True)
                if project is None:
                    raise GuideProposalError("proposal_unavailable")
                existing = await self.replay.find(
                    str(actor.actor_profile_id), ACTION, command.idempotency_key
                )
                if existing is not None:
                    receipt, facts, authority = activation_custody(existing, request_id=request_id)
                    if receipt.command != command or facts.locator != locator:
                        raise GuideProposalError("operation_conflict")
                    guide = await self.projects.lock_project_guide(str(target.guide_id))
                    if guide is None or await load_guide_activation(self.session, guide) != receipt:
                        raise GuideProposalError("operation_conflict")
                    await prepared.validate_replay(facts, authority.authorization_decision_event_id)
                    return receipt
                if project.status not in {"draft", "active"}:
                    raise GuideProposalError("approval_blocked")
                locked, policy, post_custody = await self.post.lock_policy(
                    PostPolicySelection(
                        project_id=target.project_id,
                        guide_id=target.guide_id,
                        compilation_id=target.compilation_id,
                        policy_id=command.target.policy_id,
                    )
                )
                await self.post.require_current_upstream(locked)
                if (
                    post_custody.target != command.target
                    or post_custody.approval is None
                    or post_custody.approval.operation_id != command.post_approval_operation_id
                    or post_custody.approval.output_digest != command.post_approval_output_digest
                ):
                    raise GuideProposalError("proposal_stale")
                guide = locked.view.guide
                if (
                    guide.status != "draft"
                    or guide.mutation_generation != command.guide_mutation_generation
                ):
                    raise GuideProposalError("proposal_stale")
                previous = await self.projects.lock_active_guide(str(target.project_id))
                if (
                    UUID(previous.id) if previous else None
                ) != command.expected_previous_active_guide_id or (
                    previous.mutation_generation if previous else None
                ) != command.expected_previous_active_guide_generation:
                    raise GuideProposalError("proposal_stale")
                review = await self.projects.lock_review_policy(guide.project_id, guide.version)
                revision = await self.projects.lock_revision_policy(guide.project_id, guide.version)
                for kind, row in (("review", review), ("revision", revision)):
                    selection = getattr(command, kind)
                    if row is None or (row.id, row.policy_generation, row.policy_hash) != (
                        str(selection.policy_id),
                        selection.generation,
                        selection.policy_hash,
                    ):
                        raise GuideProposalError("proposal_stale")
                try:
                    source_items = await self.projects.lock_guide_source_snapshot_items(
                        locked.view.snapshot.id
                    )
                    await ProjectService(self.session).validate_source_snapshot_integrity(
                        locked.view.snapshot,
                        GuideActivationBlocked,
                        persisted_items=source_items,
                    )
                    self._readiness(command, locked, policy, post_custody, review, revision)
                except ProjectServiceError:
                    raise GuideProposalError("approval_blocked") from None
                contribution = GuideContributionPolicyFacts.model_validate(
                    await self.contribution.validate_for_activation(
                        target.project_id,
                        command.contribution_policy_id,
                        command.contribution_policy_version_id,
                    )
                )
                receipt = GuideActivationReceipt(
                    operation_id=operation_id,
                    command=command,
                    contribution=contribution,
                    activation_generation=command.guide_mutation_generation + 1,
                    effective_at=datetime.now(UTC),
                    prior_project_status=project.status,
                )
                facts = GuideActivationFacts(locator=locator, receipt=receipt)
                authority = await prepared.consume_new(facts)
                require_authority(authority, facts)
            # A failed capability close cannot leave a reservation or lifecycle write.
            disposition, record = await self.replay.reserve(
                actor_profile_id=str(actor.actor_profile_id),
                identity_link_id=str(actor.identity_link_id),
                action_id=ACTION,
                idempotency_key=command.idempotency_key,
                request_digest=command.digest,
                resource_context_digest=facts.digest,
                operation_id=operation_id,
                project_id=guide.project_id,
                resource_id=guide.id,
                operation_generation=receipt.activation_generation,
                activation_facts_json=facts.resource_json(),
                activation_authority_json=authority.model_dump(mode="json"),
            )
            if disposition != "claimed":
                raise GuideProposalError("operation_conflict")
            if previous is not None:
                previous.status, previous.superseded_at = "superseded", receipt.effective_at
                await self.session.flush()
            guide.status, guide.effective_at, guide.approved_by = (
                "active",
                receipt.effective_at,
                record.actor_profile_id,
            )
            guide.contribution_policy_id = command.contribution_policy_id
            guide.contribution_policy_version_id = command.contribution_policy_version_id
            guide.activation_operation_id = operation_id
            guide.mutation_generation = receipt.activation_generation
            guide.last_mutated_by_actor_profile_id = record.actor_profile_id
            guide.last_mutated_via_identity_link_id = record.identity_link_id
            guide.last_mutated_by_admin_role_grant_id = authority.admin_role_grant_id
            guide.last_mutation_action_id = ACTION
            guide.last_mutation_scope_type = "project"
            guide.last_mutation_scope_project_id = guide.project_id
            guide.last_authorization_decision_event_id = str(
                authority.authorization_decision_event_id
            )
            if project.status == "draft":
                project.status = "active"
            await self.session.flush()
            await self.replay.complete(record, response_json=receipt.model_dump(mode="json"))
            return receipt

    def _readiness(self, command, locked, policy, post, review, revision):
        target, approval = command.target.proposal, locked.view.approval_custody
        require_catalogues(target, self.pre_catalogue, self.post_catalogue)
        post.compiled.validate_catalogue(self.post_catalogue)
        ProjectService(self.session).validate_activation_ready(
            locked.view.guide,
            locked.view.snapshot,
            locked.view.report,
            locked.view.policy,
            approval.effective,
            approval.pre,
            policy,
            review,
            revision,
            approval_custody=approval,
            post_policy_custody=post,
        )
        upstream = command.target.upstream
        plan = self.planner.compile_effective_plan(
            lineage=EffectivePreSubmissionPlanLineage(
                project_id=target.project_id,
                guide_id=target.guide_id,
                guide_version=target.guide_version,
                source_snapshot_id=target.source_snapshot_id,
                source_snapshot_hash=target.source_snapshot_hash,
                effective_policy_id=upstream.effective_policy_id,
                effective_policy_hash=upstream.effective_policy_hash,
                pre_submit_policy_id=upstream.pre_submit_policy_id,
                pre_submit_policy_bundle_hash=upstream.pre_submit_bundle_hash,
            ),
            effective_policy=approval.effective.effective_policy,
            compiled_bundle=approval.pre.compiled_bundle,
        )
        if (
            plan.plan_sha256 != upstream.effective_pre_submit_plan_hash
            or plan.catalogue_manifest_sha256 != target.pre_catalogue_manifest_hash
        ):
            raise GuideProposalError("approval_blocked")
