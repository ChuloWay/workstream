"""Each original malformed selector reaches the real API validation boundary."""

from uuid import uuid4

import pytest

from tests.authorization.admin_access.support import AdminAccess, authority_snapshot, grant_body


@pytest.mark.parametrize(
    "case,status,code",
    [
        ("pending_status", 422, "invalid_request"),
        ("zero_limit", 422, "invalid_request"),
        ("excessive_limit", 422, "invalid_request"),
        ("malformed_actor", 422, "invalid_request"),
        ("unknown_role", 422, "invalid_request"),
        ("unknown_scope", 422, "invalid_request"),
        ("malformed_grant", 422, "invalid_request"),
        ("operator_project", 422, "invalid_role_scope"),
        ("oversized_utf8_reason", 422, "invalid_request"),
        ("absent_project", 404, "resource_not_found"),
        ("system_with_project", 400, "invalid_request"),
        ("missing_project", 400, "invalid_request"),
        ("invalid_cursor", 400, "invalid_request"),
    ],
)
async def test_invalid_admin_request_is_bounded(
    admin_access: AdminAccess,
    case: str,
    status: int,
    code: str,
) -> None:
    access = admin_access
    path = "/api/v1/admin-role-grants"
    params = {"scope_type": "system"}
    body = grant_body(access.target.id)
    method = "get"
    if case in {"pending_status", "zero_limit", "excessive_limit"}:
        params |= {
            "pending_status": {"status": "pending"},
            "zero_limit": {"limit": 0},
            "excessive_limit": {"limit": 101},
        }[case]
    elif case == "malformed_actor":
        path = "/api/v1/actors/not-a-uuid/admin-role-grants"
    elif case == "system_with_project":
        params["scope_project_id"] = str(uuid4())
    elif case == "missing_project":
        params["scope_type"] = "project"
    elif case == "invalid_cursor":
        params["cursor"] = "not-a-cursor"
    else:
        method = "post"
        if case == "malformed_grant":
            path, body = (
                "/api/v1/admin-role-grants/not-a-uuid/revoke",
                {"reason": "Invalid selector"},
            )
        elif case == "unknown_role":
            body["role"] = "administrator"
        elif case == "unknown_scope":
            body |= {"role": "project_manager", "scope_type": "organization"}
        elif case == "oversized_utf8_reason":
            body["reason"] = "é" * 251
        else:
            assert case in {"operator_project", "absent_project"}
            body |= {
                "role": "operator" if case == "operator_project" else "project_manager",
                "scope_type": "project",
                "scope_project_id": str(uuid4()),
            }
    before = await authority_snapshot()
    if method == "get":
        response = await access.signed.client.get(path, headers=access.admin.headers, params=params)
    else:
        response = await access.signed.client.post(
            path,
            headers=access.admin.headers | {"Idempotency-Key": str(uuid4())},
            json=body,
        )
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    after = await authority_snapshot()
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]
