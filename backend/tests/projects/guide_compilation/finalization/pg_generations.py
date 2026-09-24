"""Create a second setup generation through the real correction workflow."""

from uuid import UUID, uuid4

from sqlalchemy import text

from app.adapters.artifacts import guide_document_manifest_port
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.api.guide_documents import GuideDocumentManifestRequest
from app.modules.projects.api.guide_proposals import GuideProposalCorrection
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService

from ..helpers import context
from ..proposals.pg_support import ProposalAuthority, read_package, request_corrected_attempt
from .pg_support import finalize


async def second_generation(factory, values, first):
    """Admit generation two only through finalized-proposal correction custody."""
    await finalize(factory, values, first)
    async with factory() as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT a.id,l.id AS link,g.id AS grant FROM actor_profiles a "
                        "JOIN actor_identity_links l ON l.actor_profile_id=a.id "
                        "JOIN admin_role_grants g ON g.target_actor_profile_id=a.id "
                        "WHERE g.role='project_manager' AND g.scope_project_id=:project "
                        "AND g.status='active'"
                    ),
                    {"project": str(first.project_id)},
                )
            )
            .mappings()
            .one()
        )
    actor = ActorIdentityFacts(
        UUID(str(row["id"])), UUID(str(row["link"])), ActorKind.HUMAN
    )
    package = await read_package(factory, first, actor, row["grant"])
    async with factory() as session, session.begin():
        correction = await GuideProposalService(
            session,
            ProposalAuthority(session, actor, first.project_id, row["grant"]),
        ).request_correction(
            GuideProposalCorrection(
                target=package.target,
                idempotency_key=uuid4(),
                reason="Exercise exact successor-generation custody.",
            ),
            actor=actor,
            request_id=uuid4(),
        )
    requested = await request_corrected_attempt(factory, actor, correction)
    async with factory() as session:
        material = await guide_document_manifest_port(session).load(
            GuideDocumentManifestRequest(
                project_id=first.project_id,
                guide_id=first.guide_id,
                guide_source_snapshot_id=values["snapshot"],
                project_setup_run_id=correction.successor_setup_run_id,
                setup_generation=correction.successor_setup_generation,
            )
        )
    compilation_context = context(values, generation=2).model_copy(
        update={
            "setup_run_id": correction.successor_setup_run_id,
            "setup_generation": correction.successor_setup_generation,
            "material": material,
        }
    )
    return compilation_context, requested
