"""Two request-local PREP services sharing controlled identity and evidence ports."""

from contextlib import asynccontextmanager
from functools import partial
from unittest.mock import Mock
from uuid import UUID, uuid4

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization import guide_compilation_projections as adapters
from app.modules.authorization.api import (
    ProjectGuideProjectionLocator,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_identity,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationService,
)

from .support import custody, policy_facts, sufficiency_facts


class ReplayCase:
    def __init__(self, monkeypatch, component="guide_sufficiency"):
        self.locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
        identity_factory = (
            guide_sufficiency_projection_identity
            if component == "guide_sufficiency"
            else artifact_policy_projection_identity
        )
        seed = identity_factory(
            attempt_id=self.locator.attempt_id,
            actor_profile_id=UUID(int=0),
            identity_link_id=UUID(int=0),
        )
        self.first, self.session, self.evidence = custody(
            request_id=seed.operation_id, correlation_id=seed.correlation_id
        )
        self.services = []
        self.close_spies = []
        self.facts = (sufficiency_facts if component == "guide_sufficiency" else policy_facts)(
            self.locator.project_id, self.locator.attempt_id
        )
        adapter = (
            adapters.GuideSufficiencyProjectionAuthorization(self.session)
            if component == "guide_sufficiency"
            else adapters.ArtifactPolicyProjectionAuthorization(self.session)
        )
        self.prepare = partial(
            adapter.prepare_sufficiency_projection
            if component == "guide_sufficiency"
            else adapter.prepare_artifact_policy_projection,
            self.locator,
        )

        @asynccontextmanager
        async def fixed(session, *, service_identity, request_id, correlation_id):
            assert session is self.session
            assert service_identity is ServiceIdentity.PROJECT_SETUP
            assert request_id == seed.operation_id
            assert correlation_id == seed.correlation_id
            assert len(self.services) < 2, "fixture supports only original and replay preparation"
            original = self.first.service
            service = (
                original
                if not self.services
                else PreparedAuthorizationService(
                    self.session, original._context, original._authorization, original._repository
                )
            )
            self.services.append(service)
            close = Mock(wraps=service.close)
            self.close_spies.append(close)
            monkeypatch.setattr(service, "close", close)
            try:
                yield FixedServicePreparedAuthorization(
                    actor_profile_id=self.first.actor_profile_id,
                    identity_link_id=self.first.identity_link_id,
                    service=service,
                )
            finally:
                service.close()

        monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
