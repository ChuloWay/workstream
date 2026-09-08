"""Real PREP/kernel with bounded identity/evidence doubles; no storage claims."""

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization import project_setup_finalization as adapters
from app.modules.authorization.api import (
    ProjectSetupFinalizationLocator,
    setup_finalization_identity,
)
from app.modules.authorization.domain.project_setup_finalization import (
    finalization_resource_context,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationService,
)
from tests.authorization.guide_compilation_projections.support import custody
from tests.projects.guide_compilation.finalization.support import scenario

DIGEST = "sha256:" + "f" * 64
FIELDS = (
    "project_id",
    "guide_id",
    "guide_version",
    "source_snapshot_id",
    "source_snapshot_hash",
    "setup_run_id",
    "setup_generation",
    "celery_task_id",
    "source_state_digest",
    "operation_id",
    "correlation_id",
    "finalization_id",
    "attempt_id",
    "request_operation_id",
    "provider_idempotency_key",
    "compilation_id",
    "canonical_input_hash",
    "result_hash",
    "result_schema_version",
    "compilation_agent_name",
    "compilation_agent_version",
    "component_hashes",
    "result_classification",
    "setup_outcome",
    "sufficiency_operation_id",
    "sufficiency_report_id",
    "sufficiency_output_digest",
    "artifact_policy_operation_id",
    "artifact_policy_id",
    "artifact_policy_output_digest",
)


def locator_for(facts):
    return ProjectSetupFinalizationLocator(
        project_id=facts.project_id,
        operation_id=facts.operation_id,
        correlation_id=facts.correlation_id,
    )


def alternate(facts, field):
    """A valid alternate vector, including coupled identity and classification fields."""
    value = getattr(facts, field)
    changes = {field: uuid4() if isinstance(value, UUID) else DIGEST}
    if field in {"finalization_id", "operation_id", "correlation_id"}:
        changes = {"compilation_id": uuid4()}
    elif field == "setup_generation":
        changes[field] = value + 1
    elif field == "component_hashes":
        changes[field] = ((value[0][0], DIGEST), *value[1:])
    elif field == "result_classification":
        changes[field] = "draft_ready_with_warnings"
    elif field == "setup_outcome":
        changes.update(
            result_classification="guide_blocked",
            setup_outcome="sufficiency_blocked",
            artifact_policy_id=None,
            artifact_policy_operation_id=None,
            artifact_policy_output_digest=None,
        )
    elif isinstance(value, str) and not field.endswith(("hash", "digest")):
        changes[field] = value + "-changed"
    result = replace(facts, **changes)
    receipt, operation, correlation = setup_finalization_identity(
        result.setup_run_id, result.setup_generation, result.compilation_id
    )
    return replace(
        result, finalization_id=receipt, operation_id=operation, correlation_id=correlation
    )


class Case:
    """Fresh request-local handles with actual private PREP request and principal custody."""

    def __init__(self, monkeypatch, classification="draft_ready", **custody_options):
        self.facts = scenario(classification).auth.expected
        self.first, self.session, self.evidence = custody(
            request_id=self.facts.operation_id,
            correlation_id=self.facts.correlation_id,
            **custody_options,
        )
        self.services = []
        self.closed = []
        self.event_changes = {}
        self.fixed_calls = []
        original_get = self.evidence.get_authority_event

        async def get_event(event_id):
            event = await original_get(event_id)
            if event is None:
                return None
            stored = SimpleNamespace(
                **vars(event),
                event_domain="authority",
                actor_ref_kind="actor_profile",
                denial_code=None,
            )
            for key, value in self.event_changes.items():
                setattr(stored, key, value)
            return stored

        self.evidence.get_authority_event = get_event

        @asynccontextmanager
        async def fixed(session, *, service_identity, request_id, correlation_id):
            assert session is self.session
            assert service_identity is ServiceIdentity.PROJECT_SETUP
            self.fixed_calls.append((request_id, correlation_id))
            original = self.first.service
            context = original._context.model_copy(
                update={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }
            )
            # A new real kernel context accompanies each new preparation request.
            kernel_type = type(original._authorization)
            kernel = kernel_type(session, context, admin_repository=original._repository)
            kernel._audit = self.evidence
            service = PreparedAuthorizationService(session, context, kernel, original._repository)
            self.services.append(service)
            try:
                yield FixedServicePreparedAuthorization(
                    actor_profile_id=context.actor_profile_id,
                    identity_link_id=context.identity_link_id,
                    service=service,
                )
            finally:
                service.close()
                self.closed.append(service)

        monkeypatch.setattr(adapters, "fixed_service_prepared_authorization", fixed)
        self.adapter = adapters.SetupFinalizationAuthorization(self.session)

    def prepare(self, facts=None):
        return self.adapter.prepare_setup_finalization(locator_for(facts or self.facts))

    def resource(self, facts=None):
        return finalization_resource_context(
            facts or self.facts, self.first.actor_profile_id, self.first.identity_link_id
        )


def finalization_facts(project_id):
    """A complete public fact vector for isolated resource-shape tests."""
    return replace(scenario().auth.expected, project_id=project_id)
