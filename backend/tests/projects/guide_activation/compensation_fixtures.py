"""Real scoped adapter binding for activation's compensated-policy control."""

from uuid import uuid4

from app.adapters.auth import compensation_adapter_binding_authorization
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.compensation.api import AdapterBindingCreateRequest
from app.modules.contributions.models import ProjectCompensationUnit
from app.modules.compensation.service import AdapterBindingService
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility


async def create_binding(factory, world):
    adapter = uuid4()
    async with factory() as session, session.begin():
        session.add(
            ActorProfile(
                id=str(adapter),
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=ServiceIdentity.COMPENSATION_ADAPTER.value,
                created_by="activation-fixture",
            )
        )
        await session.flush()
        session.add(
            ActorIdentityLink(
                id=str(uuid4()),
                actor_profile_id=str(adapter),
                issuer="workstream-internal",
                subject="activation-compensation-adapter",
                subject_kind="service",
                status="active",
                linked_by="activation-fixture",
            )
        )
        session.add(
            ProjectCompensationUnit(
                project_id=str(world.project),
                instrument_type="money",
                unit_code="USD",
                iso_currency_code="USD",
                status="active",
                created_by=str(world.context.actor_profile_id),
            )
        )
    async with factory() as session, session.begin():
        authority = compensation_adapter_binding_authorization(session, world.context)
        binding = await AdapterBindingService(
            session,
            mutation_authorization=authority,
            projects=ProjectCompensationBindingEligibility(session),
            actors=CompensationAdapterActorEligibility(session),
        ).create(
            AdapterBindingCreateRequest(
                operation_id=uuid4(),
                actor_profile_id=world.context.actor_profile_id,
                project_id=world.project,
                instrument_type="money",
                adapter_actor_id=adapter,
                route_key="activation.money",
            )
        )
    return binding.adapter_binding_id
