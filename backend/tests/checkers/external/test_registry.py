"""Registry registration remains caller-transactional, authorized and replay exact."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.checker_registry_authorization import (
    ExternalCheckerRegistryAuthorizationAdapter,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistrationAuthorityFacts,
    ExternalCheckerRegistrationAuthorityReceipt,
    ExternalCheckerRegistrationCommand,
    ExternalCheckerRegistrationPreparation,
    ExternalCheckerRegistryConflict,
    ExternalCheckerRegistryNotFound,
    ExternalCheckerRegistryUnavailable,
    external_checker_registration_request_digest,
)
from app.modules.checkers.external_registry import ExternalCheckerRegistryService
from tests.checkers.external.support import registration_request, schema


class _Session:
    def __init__(self, active: bool = True) -> None:
        self.root = SimpleNamespace(is_active=active) if active else None
        self.sync_session = self
        self.rows = []

    async def get(self, model, entry_id, *, populate_existing):
        from app.modules.checkers.models import ExternalCheckerRegistryEntryRecord

        assert model is ExternalCheckerRegistryEntryRecord and populate_existing is True
        return next((row for row in self.rows if row.id == entry_id), None)

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return False


class _NativeDriverUUID(UUID):
    """Represent a valid PostgreSQL driver UUID subtype at the storage boundary."""


class _Authority:
    def __init__(self) -> None:
        self.preparations: list[ExternalCheckerRegistrationPreparation] = []
        self.calls: list[ExternalCheckerRegistrationAuthorityFacts] = []
        self.closed: list[object] = []

    async def prepare_registration(self, facts):
        self.preparations.append(facts)
        return object()

    async def consume_registration(self, prepared, preparation, facts):
        self.calls.append(facts)
        return ExternalCheckerRegistrationAuthorityReceipt(
            actor_profile_id=facts.actor_profile_id,
            authorization_decision_event_id=uuid4(),
        )

    def close_registration(self, prepared):
        self.closed.append(prepared)

    async def prepare_read(self, actor_profile_id):
        return None

    async def authorize_read(self, facts):
        self.calls.append(facts)


class _KernelAdminRepository:
    def __init__(self) -> None:
        self.grant_id = uuid4()
        self.filters = None

    async def lock_control(self) -> None:
        return None

    async def lock_request_actor(self, identity_link_id, actor_profile_id):
        return (
            SimpleNamespace(
                id=str(identity_link_id),
                actor_profile_id=str(actor_profile_id),
                status="active",
            ),
            SimpleNamespace(
                id=str(actor_profile_id), actor_kind="human", status="active"
            ),
        )

    async def find_effective_grant(self, *_args, **kwargs):
        self.filters = kwargs
        return SimpleNamespace(
            id=self.grant_id,
            status="active",
            scope_project_id=None,
        )


class _Evidence:
    def __init__(self) -> None:
        self.events = []

    async def add_authority_event(self, event) -> None:
        self.events.append(event)


class _Repository:
    def __init__(self) -> None:
        self.rows = []
        self.locks: list[tuple] = []

    async def lock_registration_scopes(self, operation_id, **identity):
        self.locks.append((operation_id, identity))

    async def by_operation(self, operation_id):
        return next(
            (row for row in self.rows if row.registration_operation_id == operation_id),
            None,
        )

    async def by_identity(self, **identity):
        return next(
            (
                row
                for row in self.rows
                if all(getattr(row, name) == value for name, value in identity.items())
            ),
            None,
        )

    async def add(self, row):
        row.created_at = datetime.now(timezone.utc)
        self.rows.append(row)

    async def by_exact_id(self, entry_id):
        return next((row for row in self.rows if row.id == entry_id), None)


def _service(active: bool = True):
    authority = _Authority()
    session = _Session(active)
    service = ExternalCheckerRegistryService(session, authority)  # type: ignore[arg-type]
    repository = _Repository()
    session.rows = repository.rows
    service._repository = repository  # type: ignore[assignment]
    return service, authority, repository


@pytest.mark.asyncio
async def test_register_flushes_once_and_freshly_authorizes_exact_replay() -> None:
    service, authority, repository = _service()
    request = registration_request()

    first = await service.register(request)
    repository.rows[0].id = _NativeDriverUUID(str(repository.rows[0].id))
    replay = await service.register(request)

    assert replay == first
    assert len(repository.rows) == 1
    assert authority.calls == [authority.calls[0], authority.calls[0]]
    assert len(authority.preparations) == len(authority.closed) == 2
    assert {call.registry_entry_id for call in authority.calls} == {
        first.registry_entry_id
    }
    assert {call.request_digest for call in authority.calls} == {
        repository.rows[0].request_digest
    }
    assert first.entry_digest == request.spec.spec_digest
    assert first.registered_by_actor_profile_id == request.actor_profile_id


@pytest.mark.asyncio
async def test_register_rejects_operation_or_logical_identity_substitution() -> None:
    service, authority, repository = _service()
    request = registration_request()
    await service.register(request)

    changed_operation = registration_request()
    changed_operation = changed_operation.model_copy(
        update={"spec": request.spec}
    )
    with pytest.raises(ExternalCheckerRegistryConflict):
        await service.register(changed_operation)

    assert len(repository.rows) == 1
    assert len(authority.preparations) == 2
    assert len(authority.calls) == 1


@pytest.mark.asyncio
async def test_same_operation_rejects_every_mutated_payload_and_preserves_row() -> None:
    service, authority, repository = _service()
    request = registration_request()
    stored = await service.register(request)
    spec = request.spec
    changed_image = type(spec).model_validate(
        spec.model_dump() | {"image_digest": "sha256:" + "b" * 64}
    )
    changed_schema = type(spec).model_validate(
        spec.model_dump()
        | {"configuration_schema": schema("acme.changed.configuration")}
    )
    changed_resources = type(spec).model_validate(
        spec.model_dump()
        | {"resources": spec.resources.model_dump() | {"cpu_millis": 600}}
    )
    mutations = (
        ExternalCheckerRegistrationCommand(
            actor_profile_id=request.actor_profile_id,
            operation_id=request.operation_id,
            spec=changed,
        )
        for changed in (
            changed_image,
            changed_schema,
            changed_resources,
        )
    )
    for mutation in mutations:
        with pytest.raises(ExternalCheckerRegistryConflict):
            await service.register(mutation)

    assert len(repository.rows) == 1
    assert len(authority.preparations) == 4
    assert len(authority.calls) == 1
    assert await service.read_exact(stored.registry_entry_id, stored.entry_digest) == stored


@pytest.mark.asyncio
async def test_register_requires_an_active_caller_owned_root_transaction() -> None:
    service, authority, repository = _service(active=False)
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await service.register(registration_request())
    assert authority.preparations == authority.calls == []
    assert repository.rows == []


@pytest.mark.asyncio
async def test_authorized_read_returns_only_the_exact_validated_entry() -> None:
    service, authority, _repository = _service()
    command = registration_request()
    stored = await service.register(command)

    assert await service.read_authorized(
        command.actor_profile_id, stored.registry_entry_id
    ) == stored
    assert authority.calls[-1].registry_entry_id == stored.registry_entry_id
    assert authority.calls[-1].entry_digest == stored.entry_digest

    with pytest.raises(ExternalCheckerRegistryNotFound):
        await service.read_authorized(command.actor_profile_id, new_record_id())


@pytest.mark.asyncio
async def test_real_kernel_classifies_registry_as_system_operator_mutation() -> None:
    operation_id, actor_id = uuid4(), uuid4()
    context = HumanAuthorizationContext(
        actor_profile_id=actor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=uuid4(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=operation_id,
    )
    repository = _KernelAdminRepository()
    session = _Session()
    authorization = AuthorizationService(
        session,
        context,
        admin_repository=repository,  # type: ignore[arg-type]
    )
    evidence = _Evidence()
    authorization._audit = evidence  # type: ignore[assignment]
    prepared = PreparedAuthorizationService(
        session, context, authorization, repository  # type: ignore[arg-type]
    )
    adapter = ExternalCheckerRegistryAuthorizationAdapter(authorization, prepared)
    command = registration_request(actor_profile_id=actor_id)
    command = command.model_copy(update={"operation_id": operation_id})
    preparation = ExternalCheckerRegistrationPreparation(
        actor_profile_id=actor_id,
        operation_id=operation_id,
        entry_digest=command.spec.spec_digest,
    )
    handle = await adapter.prepare_registration(preparation)
    registry_entry_id = new_record_id()
    facts = ExternalCheckerRegistrationAuthorityFacts(
        actor_profile_id=actor_id,
        operation_id=operation_id,
        registry_entry_id=registry_entry_id,
        request_digest=external_checker_registration_request_digest(
            command, registry_entry_id
        ),
        entry_digest=command.spec.spec_digest,
    )

    receipt = await adapter.consume_registration(handle, preparation, facts)
    adapter.close_registration(handle)

    assert receipt.actor_profile_id == actor_id
    assert len(evidence.events) == 1
    assert evidence.events[0].action_id == ActionId.CHECKER_REGISTRY_REGISTER
    assert evidence.events[0].resource_id == str(registry_entry_id)
    assert repository.filters is not None
    assert repository.filters["scope_project_id"] is None
    assert repository.filters["system_scope_only"] is True
    assert {role.value for role in repository.filters["allowed_roles"]} == {"operator"}

    mismatched = context.model_copy(update={"correlation_id": uuid4()})
    other_repository = _KernelAdminRepository()
    other_authorization = AuthorizationService(
        session, mismatched, admin_repository=other_repository  # type: ignore[arg-type]
    )
    other_prepared = PreparedAuthorizationService(
        session, mismatched, other_authorization, other_repository  # type: ignore[arg-type]
    )
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await ExternalCheckerRegistryAuthorizationAdapter(
            other_authorization, other_prepared
        ).prepare_registration(preparation)
