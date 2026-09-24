"""Two request-local PREP services sharing controlled identity and evidence ports."""

from contextlib import asynccontextmanager
from functools import partial
from unittest.mock import Mock
from uuid import uuid4

from app.core.identifiers import new_record_id

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization import guide_compilation_projections as adapters
from app.modules.authorization.api import (
    ProjectGuideProjectionLocator,
    projection_preparation_identity,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationService,
)

from .support import custody, policy_facts, sufficiency_facts


class ReplayCase:
    def __init__(self, monkeypatch, component="guide_sufficiency"):
        self.locator = ProjectGuideProjectionLocator(project_id=uuid4(), attempt_id=uuid4())
        expected_request_id, expected_correlation_id = projection_preparation_identity(
            attempt_id=self.locator.attempt_id, component=component
        )
        self.first, self.session, self.evidence = custody(
            request_id=expected_request_id, correlation_id=expected_correlation_id
        )
        self.services = []
        self.close_spies = []
        self.facts = (sufficiency_facts if component == "guide_sufficiency" else policy_facts)(
            self.locator.project_id, self.locator.attempt_id
        )
        self.operation_id = new_record_id()
        _, self.correlation_id = projection_preparation_identity(
            attempt_id=self.locator.attempt_id, component=component
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
            assert request_id == expected_request_id
            assert correlation_id == expected_correlation_id
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

    def bind(self, prepared):
        return prepared.identity(
            operation_id=self.operation_id,
            correlation_id=self.correlation_id,
            output_id=getattr(self.facts, "report_id", None) or self.facts.policy_id,
        )
