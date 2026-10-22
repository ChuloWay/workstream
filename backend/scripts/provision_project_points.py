#!/usr/bin/env python3
"""Enable project points for one project through the owners' authorized commands.

The script ensures three prerequisites of a ``project_points`` award rule:

1. the ``workstream.compensation.adapter`` service actor, provisioned through
   ``POST /api/v1/service-actors`` under the Access Administrator named by
   ``--admin-subject`` (skipped when the actor already exists);
2. the project's points unit (default ``FLOW``, "Flow Points"), created by
   ``contribution.compensation_unit.create`` under the Finance Authority named
   by ``--finance-actor-profile-id``;
3. the project's active ``project_points`` adapter binding, created by
   ``compensation.adapter_binding.create`` under the same Finance Authority.

The existing AUTH decisions, not this script, grant each change. The script
does not authenticate its caller: whoever can run it already holds the database
credentials, so it is a local operator tool only and refuses production-like
environments. Each step is its own commit. A rerun reports what already exists
and changes nothing; a binding that exists with another adapter actor or route
key is reported as a mismatch, not as ready.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any
from uuid import UUID, uuid5

import httpx
from sqlalchemy import select

from app.adapters.auth import compensation_adapter_binding_authorization, contribution_policy_authorization
from app.adapters.contributions import project_compensation_unit_service
from app.core.config import PRODUCTION_LIKE_ENVIRONMENTS, get_settings
from app.core.identifiers import new_record_id
from app.db.session import dispose_engine, get_session_factory
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.compensation.api import AdapterBindingCreateRequest
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.compensation.service import AdapterBindingService
from app.modules.contributions.api import ProjectCompensationUnitCreateRequest
from app.modules.contributions.models import ProjectCompensationUnit
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility

if __package__:
    from .provision_local_service_actors import provision as provision_service_actors
    from .provision_local_service_actors import safe_api_url
else:
    from provision_local_service_actors import provision as provision_service_actors
    from provision_local_service_actors import safe_api_url

ADAPTER_IDENTITY = ServiceIdentity.COMPENSATION_ADAPTER.value
INSTRUMENT = "project_points"
DEFAULT_UNIT_CODE = "FLOW"
DEFAULT_ROUTE_KEY = "flow_points.local"
_OPERATION_NAMESPACE = UUID("3c4f0b9e-2a7d-4e51-8b6c-9d1e0f2a7b33")


class ProvisioningUnavailable(RuntimeError):
    """A prerequisite is missing and this run cannot create it."""


def operation_id(step: str, project_id: UUID, value: str) -> UUID:
    """Return the stable operation identifier of one step for one project."""
    return uuid5(_OPERATION_NAMESPACE, f"{step}\n{project_id}\n{value}")


async def _adapter_actor_id() -> UUID | None:
    """Return the active compensation-adapter service actor, if provisioned."""
    async with get_session_factory()() as session:
        value = await session.scalar(
            select(ActorProfile.id).where(
                ActorProfile.service_identity == ADAPTER_IDENTITY,
                ActorProfile.status == "active",
            )
        )
    return None if value is None else UUID(str(value))


async def _provision_adapter_actor(api_url: str, admin_subject: str, subject_prefix: str) -> str:
    """Create the adapter actor through the existing Access Administrator route."""
    if not safe_api_url(api_url):
        raise ProvisioningUnavailable("invalid_api_url")
    with httpx.Client(base_url=api_url, timeout=30) as client:
        result = provision_service_actors(client, admin_subject, (ADAPTER_IDENTITY,), subject_prefix)
    return result[ADAPTER_IDENTITY]


async def _finance_context(actor_profile_id: UUID) -> HumanAuthorizationContext:
    """Bind the Finance Authority's single active identity link; AUTH decides the rest."""
    async with get_session_factory()() as session:
        links = (
            await session.scalars(
                select(ActorIdentityLink.id).where(
                    ActorIdentityLink.actor_profile_id == str(actor_profile_id),
                    ActorIdentityLink.status == "active",
                )
            )
        ).all()
    if len(links) != 1:
        raise ProvisioningUnavailable("finance_identity_unavailable")
    return HumanAuthorizationContext(
        actor_profile_id=actor_profile_id,
        identity_link_id=UUID(str(links[0])),
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
    )


async def _ensure_unit(
    context: HumanAuthorizationContext, project_id: UUID, unit_code: str
) -> str:
    """Create the points unit unless the project already has it."""
    async with get_session_factory()() as session, session.begin():
        existing = await session.get(
            ProjectCompensationUnit, (str(project_id), INSTRUMENT, unit_code)
        )
        if existing is not None:
            return "existing"
        await project_compensation_unit_service(
            session,
            mutation_authorization=contribution_policy_authorization(session, context),
        ).create(
            ProjectCompensationUnitCreateRequest(
                operation_id=operation_id("unit", project_id, unit_code),
                actor_profile_id=context.actor_profile_id,
                project_id=project_id,
                instrument_type=INSTRUMENT,
                unit_code=unit_code,
            )
        )
    return "created"


async def _ensure_binding(
    context: HumanAuthorizationContext, project_id: UUID, adapter_actor_id: UUID, route_key: str
) -> tuple[str, UUID]:
    """Create the project's active points binding unless one already exists."""
    async with get_session_factory()() as session, session.begin():
        existing = await session.scalar(
            select(ProjectCompensationAdapterBinding).where(
                ProjectCompensationAdapterBinding.project_id == str(project_id),
                ProjectCompensationAdapterBinding.instrument_type == INSTRUMENT,
                ProjectCompensationAdapterBinding.status == "active",
            )
        )
        if existing is not None:
            if (
                existing.adapter_actor_id != str(adapter_actor_id)
                or existing.route_key != route_key
            ):
                raise ProvisioningUnavailable("active_binding_mismatch")
            return "existing", UUID(str(existing.id))
        authorization = compensation_adapter_binding_authorization(session, context)
        result = await AdapterBindingService(
            session,
            read_authorization=authorization,
            mutation_authorization=authorization,
            projects=ProjectCompensationBindingEligibility(session),
            actors=CompensationAdapterActorEligibility(session),
        ).create(
            AdapterBindingCreateRequest(
                operation_id=operation_id("binding", project_id, route_key),
                actor_profile_id=context.actor_profile_id,
                project_id=project_id,
                instrument_type=INSTRUMENT,
                adapter_actor_id=adapter_actor_id,
                route_key=route_key,
            )
        )
    return "created", result.adapter_binding_id


async def run(args: argparse.Namespace, output: dict[str, Any]) -> dict[str, Any]:
    """Ensure each prerequisite in order, recording each completed step in ``output``."""
    try:
        if get_settings().environment in PRODUCTION_LIKE_ENVIRONMENTS:
            raise ProvisioningUnavailable("production_like_environment")
        adapter_actor_id = await _adapter_actor_id()
        if adapter_actor_id is not None:
            output["adapter_actor"] = "existing"
        elif args.admin_subject is None:
            raise ProvisioningUnavailable("adapter_actor_missing_and_no_admin_subject")
        else:
            outcome = await _provision_adapter_actor(
                args.api_url, args.admin_subject, args.subject_prefix
            )
            adapter_actor_id = await _adapter_actor_id()
            if outcome.startswith("failed") or adapter_actor_id is None:
                raise ProvisioningUnavailable(f"adapter_actor_{outcome}")
            output["adapter_actor"] = outcome
        output["adapter_actor_id"] = str(adapter_actor_id)
        context = await _finance_context(args.finance_actor_profile_id)
        output["unit"] = await _ensure_unit(context, args.project_id, args.unit_code)
        output["unit_code"] = args.unit_code
        binding_result, binding_id = await _ensure_binding(
            context, args.project_id, adapter_actor_id, args.route_key
        )
        output["binding"] = binding_result
        output["adapter_binding_id"] = str(binding_id)
        return {"result_code": "ready", **output}
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run every step and print one privacy-bounded JSON summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-id", type=UUID, required=True)
    parser.add_argument("--finance-actor-profile-id", type=UUID, required=True)
    parser.add_argument("--unit-code", default=DEFAULT_UNIT_CODE)
    parser.add_argument("--route-key", default=DEFAULT_ROUTE_KEY)
    parser.add_argument("--admin-subject", help="Flow subject of the Access Administrator")
    parser.add_argument(
        "--api-url", default=os.environ.get("WORKSTREAM_LOCAL_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--subject-prefix", default="local-agent-loop")
    args = parser.parse_args(argv)
    output: dict[str, Any] = {"project_id": str(args.project_id)}
    try:
        result = asyncio.run(run(args, output))
    except ProvisioningUnavailable as error:
        print(json.dumps({"result_code": "unavailable", "detail": str(error), **output}))
        return 3
    except Exception as error:  # noqa: BLE001 - AUTH and database detail stay privacy-bounded.
        # Steps already listed were committed; the failed step was rolled back.
        print(json.dumps({"result_code": "failed", "error_type": type(error).__name__, **output}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
