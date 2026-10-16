"""Signed public API proof for Operator checker registration and readback."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.db import session as db_session
from app.main import create_app
from app.modules.actors.models import ActorIdentityLink
from tests.authorization.admin_access.concurrency_support import ordered_owner_calls
from tests.checkers.external.support import registry_spec


PATH = "/api/v1/operations/external-checker-registry"


def test_registry_openapi_exposes_exact_actions_and_server_owned_identity() -> None:
    schema = create_app().openapi()
    registration = schema["paths"][PATH]["post"]
    read = schema["paths"][PATH + "/{registry_entry_id}"]["get"]
    assert registration["x-workstream-action-id"] == "checker.registry.register"
    assert read["x-workstream-action-id"] == "checker.registry.read"
    assert registration["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ExternalCheckerRegistrySpec"
    }
    idempotency = [
        parameter
        for parameter in registration["parameters"]
        if parameter["name"] == "Idempotency-Key"
    ]
    assert len(idempotency) == 1
    assert idempotency[0]["required"] is True


async def _counts() -> tuple[int, int]:
    async with db_session.get_session_factory()() as session:
        rows = await session.scalar(text("select count(*) from external_checker_registry_entries"))
        allows = await session.scalar(
            text(
                "select count(*) from audit_events "
                "where action_id='checker.registry.register' "
                "and after_facts->>'allowed'='true'"
            )
        )
    return int(rows or 0), int(allows or 0)


async def _read_events() -> list[dict]:
    async with db_session.get_session_factory()() as session:
        rows = (
            await session.execute(
                text(
                    "select actor_id,action_id,permission_id,resource_id,after_facts "
                    "from audit_events where action_id='checker.registry.read' order by id"
                )
            )
        ).mappings().all()
    return [dict(row) for row in rows]


async def _registration_denials() -> int:
    async with db_session.get_session_factory()() as session:
        count = await session.scalar(
            text(
                "select count(*) from audit_events "
                "where action_id='checker.registry.register' "
                "and after_facts->>'allowed'='false'"
            )
        )
    return int(count or 0)


@pytest.mark.asyncio
async def test_operator_registers_replays_reads_and_loses_access_after_revoke(
    admin_access,
) -> None:
    grant_id = await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    operation_id = uuid4()
    headers = admin_access.target.headers | {"Idempotency-Key": str(operation_id)}
    payload = registry_spec().model_dump(mode="json")

    first = await admin_access.signed.client.post(PATH, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    entry = first.json()
    entry_id = UUID(entry["registry_entry_id"])
    assert entry_id.version == 7
    assert entry["registration_operation_id"] == str(operation_id)
    assert entry["registered_by_actor_profile_id"] == str(admin_access.target.id)

    replay = await admin_access.signed.client.post(PATH, headers=headers, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json() == entry
    assert await _counts() == (1, 2)

    read = await admin_access.signed.client.get(
        f"{PATH}/{entry_id}", headers=admin_access.target.headers
    )
    assert read.status_code == 200, read.text
    assert read.json() == entry
    read_events = await _read_events()
    assert len(read_events) == 1
    assert {
        key: read_events[0][key]
        for key in ("actor_id", "action_id", "permission_id", "resource_id")
    } == {
        "actor_id": str(admin_access.target.id),
        "action_id": "checker.registry.read",
        "permission_id": "operations.status.read",
        "resource_id": str(entry_id),
    }
    assert read_events[0]["after_facts"]["allowed"] is True

    response = await admin_access.signed.revoke(admin_access.admin, grant_id)
    assert response.status_code == 200, response.text
    denied_replay = await admin_access.signed.client.post(PATH, headers=headers, json=payload)
    assert denied_replay.status_code == 403, denied_replay.text
    assert denied_replay.json()["error"]["code"] == "checker_registry_authority_denied"
    concealed_read = await admin_access.signed.client.get(
        f"{PATH}/{entry_id}", headers=admin_access.target.headers
    )
    assert concealed_read.status_code == 404, concealed_read.text
    assert await _counts() == (1, 2)
    assert await _registration_denials() == 1


@pytest.mark.asyncio
async def test_registration_conflict_and_denials_leave_no_partial_row(admin_access) -> None:
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    operation_id = uuid4()
    headers = admin_access.target.headers | {"Idempotency-Key": str(operation_id)}
    payload = registry_spec().model_dump(mode="json")
    created = await admin_access.signed.client.post(PATH, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    baseline = await _counts()

    mutated = payload | {"image_digest": "sha256:" + "b" * 64}
    conflict = await admin_access.signed.client.post(PATH, headers=headers, json=mutated)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "external_checker_registry_conflict"
    assert await _counts() == baseline

    auditor = await admin_access.signed.actor("registry-auditor")
    await admin_access.signed.grant(
        admin_access.admin, auditor, role="audit_authority"
    )
    denied = await admin_access.signed.client.post(
        PATH,
        headers=auditor.headers | {"Idempotency-Key": str(uuid4())},
        json=registry_spec("post_submit").model_dump(mode="json"),
    )
    assert denied.status_code == 403, denied.text
    missing = await admin_access.signed.client.get(
        f"{PATH}/{uuid4()}", headers=admin_access.target.headers
    )
    assert missing.status_code == 404, missing.text
    assert await _counts() == baseline
    assert await _registration_denials() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("transition", ["grant", "identity_link"])
@pytest.mark.parametrize("first_operation", ["registration", "revocation"])
async def test_registration_serializes_with_crossed_authority_revocation(
    admin_access,
    auth_database_env,
    monkeypatch,
    transition,
    first_operation,
) -> None:
    grant_id = await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    operation_id = uuid4()
    headers = admin_access.target.headers | {"Idempotency-Key": str(operation_id)}
    payload = registry_spec().model_dump(mode="json")

    if transition == "grant":
        async def disable():
            return await admin_access.signed.revoke(admin_access.admin, grant_id)
    else:
        async with db_session.get_session_factory()() as session:
            link_id = await session.scalar(
                select(ActorIdentityLink.id).where(
                    ActorIdentityLink.actor_profile_id == str(admin_access.target.id)
                )
            )

        async def disable():
            return await admin_access.signed.client.post(
                f"/api/v1/actor-identity-links/{link_id}/revoke",
                headers=admin_access.admin.headers | {"Idempotency-Key": str(uuid4())},
                json={"reason": "Crossed checker registration revocation"},
            )

    async def register():
        return await admin_access.signed.client.post(PATH, headers=headers, json=payload)

    calls = {"registration": register, "revocation": disable}
    second_operation = (
        "revocation" if first_operation == "registration" else "registration"
    )
    first, second, observation = await ordered_owner_calls(
        calls[first_operation],
        calls[second_operation],
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert observation.observed
    responses = {first_operation: first, second_operation: second}
    registered = responses["registration"]
    revoked = responses["revocation"]
    assert revoked.status_code == 200, revoked.text
    expected_count = 1 if first_operation == "registration" else 0
    assert registered.status_code == (201 if expected_count else 403), registered.text
    assert await _counts() == (expected_count, expected_count)

    denied = await admin_access.signed.client.post(PATH, headers=headers, json=payload)
    assert denied.status_code in {401, 403}, denied.text
    assert await _counts() == (expected_count, expected_count)
