"""Public Operator contract for checker model profile, budget and recovery controls."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.db import session as db_session
from app.api.deps.checker_models import CheckerModelAdminCommands
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.main import create_app
from app.modules.checkers.api.model_calls import (
    ModelCallExecutionFacts,
    ModelCallConflict,
    ModelGenerationSettings,
    ModelPaidSlotKey,
    ModelPricing,
    ModelRecoveryChildRequest,
    ProjectModelBudgetConfigurationSpec,
    ProjectModelProfileSpec,
)
from tests.authorization.admin_access.support import create_project
from tests.checkers.external.support import post_registry_spec


PROFILE_PATH = "/api/v1/operations/projects/{project_id}/model-profiles"
BUDGET_PATH = "/api/v1/operations/projects/{project_id}/model-budget-configurations"


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


def profile_spec(project_id):
    return ProjectModelProfileSpec(
        project_id=project_id,
        profile_version=1,
        registry_entry_id=new_record_id(),
        registry_entry_digest=sha("registry"),
        provider="openai_responses",
        api="responses.v1",
        model_snapshot="gpt-example-2026-10-01",
        settings=ModelGenerationSettings(reasoning_effort="medium", text_verbosity="low"),
        maximum_request_bytes=10_000,
        maximum_output_bytes=4_000,
        maximum_response_bytes=30_000,
        maximum_input_tokens=100,
        maximum_output_tokens=50,
        deadline_ms=30_000,
        pricing=ModelPricing(
            pricing_policy_id=new_record_id(),
            pricing_policy_version=1,
            pricing_policy_digest=sha("pricing"),
            uncached_input_nanodollars_per_token=11,
            cached_input_nanodollars_per_token=2,
            output_nanodollars_per_token=29,
        ),
    )


def test_openapi_exposes_only_exact_operator_model_mutations() -> None:
    paths = create_app().openapi()["paths"]
    expected = {
        "/api/v1/operations/projects/{project_id}/model-profiles": (
            "project.model_profile.provision",
            "ProjectModelProfileSpec",
        ),
        "/api/v1/operations/projects/{project_id}/model-budget-configurations": (
            "project.model_budget.configure",
            "ProjectModelBudgetConfigurationSpec",
        ),
        "/api/v1/operations/projects/{project_id}/model-call-attempts/"
        "{parent_attempt_id}/recovery-children": (
            "project.model_call.recovery_child.authorize",
            "ModelRecoveryChildRequest",
        ),
    }
    for path, (action, schema_name) in expected.items():
        operation = paths[path]["post"]
        assert operation["x-workstream-action-id"] == action
        assert operation["requestBody"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{schema_name}"
        }
        keys = [item for item in operation["parameters"] if item["name"] == "Idempotency-Key"]
        if schema_name == "ModelRecoveryChildRequest":
            assert keys == []
        else:
            assert len(keys) == 1
            assert keys[0]["required"] is True


@pytest.mark.asyncio
async def test_public_commands_bind_actor_key_project_and_exact_recovery_facts() -> None:
    class Service:
        calls = []

        async def provision_profile(self, facts):
            self.calls.append(("profile", facts))
            return facts

        async def provision_budget(self, facts):
            self.calls.append(("budget", facts))
            return facts

        async def prepare_recovery_child(self, slot, **values):
            self.calls.append(("child", slot, values))
            return values

    project_id = new_record_id()
    actor_id = new_record_id()
    operation_id = new_record_id()
    service = Service()
    commands = CheckerModelAdminCommands(service, actor_id, operation_id)
    profile = profile_spec(project_id)
    await commands.provision_profile(project_id, profile)
    budget = ProjectModelBudgetConfigurationSpec(
        project_id=project_id,
        configuration_version=1,
        lifetime_limit_nanodollars=10_000_000_000,
    )
    await commands.configure_budget(project_id, budget)

    execution = ModelCallExecutionFacts(
        project_id=project_id,
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        submission_id=new_record_id(),
        submission_version=1,
        evaluation_request_id=new_record_id(),
        evaluation_generation=1,
        checker_run_id=new_record_id(),
        worker_lease_id=new_record_id(),
        worker_lease_generation=1,
        worker_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    slot = ModelPaidSlotKey(
        project_id=project_id,
        assignment_id=execution.assignment_id,
        submission_id=execution.submission_id,
        submission_version=1,
        requirement_id="model_review",
        registry_entry_digest=profile.registry_entry_digest,
        configuration_sha256=sha("configuration"),
        profile_id=new_record_id(),
        profile_version=1,
        profile_digest=sha("profile"),
    )
    request = ModelRecoveryChildRequest(
        slot=slot,
        registry_entry_id=profile.registry_entry_id,
        terminal_digest=sha("terminal"),
        request_sha256=sha("request"),
    )
    parent_id = new_record_id()
    await commands.prepare_recovery_child(project_id, parent_id, request)

    profile_facts = service.calls[0][1]
    assert profile_facts.operation_id == operation_id
    assert profile_facts.actor_profile_id == actor_id
    assert profile_facts.spec == profile
    assert profile_facts.profile_digest == canonical_json_hash(profile.model_dump(mode="json"))
    budget_facts = service.calls[1][1]
    assert budget_facts.operation_id == operation_id
    assert budget_facts.actor_profile_id == actor_id
    assert budget_facts.spec == budget
    assert service.calls[2] == (
        "child",
        slot,
        {
            "registry_entry_id": profile.registry_entry_id,
            "parent_attempt_id": parent_id,
            "terminal_digest": request.terminal_digest,
            "request_sha256": request.request_sha256,
        },
    )

    with pytest.raises(ModelCallConflict, match="project_conflict"):
        await commands.provision_profile(new_record_id(), profile)


async def _model_control_counts() -> dict[str, int]:
    async with db_session.get_session_factory()() as session:
        rows = {}
        for name in (
            "checker_model_profiles",
            "checker_model_budget_configurations",
            "checker_model_budget_accounts",
            "checker_model_call_attempts",
        ):
            rows[name] = int(await session.scalar(text(f"select count(*) from {name}")) or 0)
        events = (
            await session.execute(
                text(
                    "select action_id,after_facts->>'allowed' as allowed,count(*) as count "
                    "from audit_events where action_id in "
                    "('project.model_profile.provision','project.model_budget.configure',"
                    "'project.model_call.recovery_child.authorize') "
                    "group by action_id,after_facts->>'allowed'"
                )
            )
        ).mappings()
        for event in events:
            rows[f"{event['action_id']}:{event['allowed']}"] = int(event["count"])
        return rows


@pytest.mark.asyncio
async def test_signed_operator_profile_budget_replay_and_fresh_denial(
    admin_access,
) -> None:
    """Replay retains one row, while revoked authority still denies the same key."""
    grant_id = await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="operator"
    )
    registry_key = uuid4()
    registered = await admin_access.signed.client.post(
        "/api/v1/operations/external-checker-registry",
        headers=admin_access.target.headers | {"Idempotency-Key": str(registry_key)},
        json=post_registry_spec().model_dump(mode="json"),
    )
    assert registered.status_code == 201, registered.text
    entry = registered.json()
    project_id = await create_project("Model control replay")

    profile_key = uuid4()
    profile = profile_spec(project_id).model_copy(
        update={
            "registry_entry_id": UUID(entry["registry_entry_id"]),
            "registry_entry_digest": entry["entry_digest"],
        }
    )
    profile_headers = admin_access.target.headers | {"Idempotency-Key": str(profile_key)}
    profile_path = PROFILE_PATH.format(project_id=project_id)
    malformed_profile = profile.model_dump(mode="json")
    malformed_profile["registry_entry_id"] = "not-a-uuid"
    malformed = await admin_access.signed.client.post(
        profile_path,
        headers=admin_access.target.headers,
        json=malformed_profile,
    )
    assert malformed.status_code == 422, malformed.text
    first_profile = await admin_access.signed.client.post(
        profile_path,
        headers=profile_headers,
        json=profile.model_dump(mode="json"),
    )
    assert first_profile.status_code == 201, first_profile.text
    replayed_profile = await admin_access.signed.client.post(
        profile_path,
        headers=profile_headers,
        json=profile.model_dump(mode="json"),
    )
    assert replayed_profile.status_code == 201, replayed_profile.text
    assert replayed_profile.json() == first_profile.json()
    assert first_profile.json()["operation_id"] == str(profile_key)
    substituted_profile = profile.model_copy(
        update={"registry_entry_digest": sha("substituted-registry")}
    )
    substituted = await admin_access.signed.client.post(
        profile_path,
        headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
        json=substituted_profile.model_dump(mode="json"),
    )
    assert substituted.status_code == 409, substituted.text
    assert substituted.json()["error"]["code"] == "checker_model_control_conflict"

    budget_key = uuid4()
    budget = ProjectModelBudgetConfigurationSpec(
        project_id=project_id,
        configuration_version=1,
        lifetime_limit_nanodollars=10_000_000_000,
    )
    budget_headers = admin_access.target.headers | {"Idempotency-Key": str(budget_key)}
    budget_path = BUDGET_PATH.format(project_id=project_id)
    malformed_budget = budget.model_dump(mode="json")
    malformed_budget["project_id"] = "not-a-uuid"
    malformed = await admin_access.signed.client.post(
        budget_path,
        headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
        json=malformed_budget,
    )
    assert malformed.status_code == 422, malformed.text
    first_budget = await admin_access.signed.client.post(
        budget_path,
        headers=budget_headers,
        json=budget.model_dump(mode="json"),
    )
    assert first_budget.status_code == 201, first_budget.text
    replayed_budget = await admin_access.signed.client.post(
        budget_path,
        headers=budget_headers,
        json=budget.model_dump(mode="json"),
    )
    assert replayed_budget.status_code == 201, replayed_budget.text
    assert replayed_budget.json() == first_budget.json()
    assert first_budget.json()["operation_id"] == str(budget_key)
    async with db_session.get_session_factory()() as session:
        targets = (
            (
                await session.execute(
                    text(
                        "select action_id,project_id,resource_type,resource_id,"
                        "target_ref_kind,target_ref_id from audit_events "
                        "where id in (:profile,:budget) order by action_id"
                    ),
                    {
                        "profile": first_profile.json()["authorization_evidence_id"],
                        "budget": first_budget.json()["authorization_evidence_id"],
                    },
                )
            )
            .mappings()
            .all()
        )
    assert len(targets) == 2
    assert all(
        (
            str(row["project_id"]),
            row["resource_type"],
            row["resource_id"],
            row["target_ref_kind"],
            row["target_ref_id"],
        )
        == (str(project_id), "project", str(project_id), "project", str(project_id))
        for row in targets
    )

    revoked = await admin_access.signed.revoke(admin_access.admin, grant_id)
    assert revoked.status_code == 200, revoked.text
    for path, headers, payload in (
        (profile_path, profile_headers, profile.model_dump(mode="json")),
        (budget_path, budget_headers, budget.model_dump(mode="json")),
    ):
        denied = await admin_access.signed.client.post(
            path,
            headers=headers,
            json=payload,
        )
        assert denied.status_code == 404, denied.text
        assert denied.json()["error"]["code"] == "checker_model_control_not_found"

    selector = first_profile.json()
    execution = ModelCallExecutionFacts(
        project_id=project_id,
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        submission_id=new_record_id(),
        submission_version=1,
        evaluation_request_id=new_record_id(),
        evaluation_generation=1,
        checker_run_id=new_record_id(),
        worker_lease_id=new_record_id(),
        worker_lease_generation=1,
        worker_lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    slot = ModelPaidSlotKey(
        project_id=project_id,
        assignment_id=execution.assignment_id,
        submission_id=execution.submission_id,
        submission_version=1,
        requirement_id="model_review",
        registry_entry_digest=entry["entry_digest"],
        configuration_sha256=sha("configuration"),
        profile_id=UUID(selector["profile_id"]),
        profile_version=selector["spec"]["profile_version"],
        profile_digest=selector["profile_digest"],
    )
    recovery = ModelRecoveryChildRequest(
        slot=slot,
        registry_entry_id=UUID(entry["registry_entry_id"]),
        terminal_digest=sha("terminal"),
        request_sha256=sha("request"),
    )
    malformed_recovery = recovery.model_dump(mode="json")
    malformed_recovery["slot"]["profile_id"] = "not-a-uuid"
    malformed = await admin_access.signed.client.post(
        "/api/v1/operations/projects/"
        f"{project_id}/model-call-attempts/{new_record_id()}/recovery-children",
        headers=admin_access.target.headers,
        json=malformed_recovery,
    )
    assert malformed.status_code == 422, malformed.text
    denied_recovery = await admin_access.signed.client.post(
        "/api/v1/operations/projects/"
        f"{project_id}/model-call-attempts/{new_record_id()}/recovery-children",
        headers=admin_access.target.headers,
        json=recovery.model_dump(mode="json"),
    )
    assert denied_recovery.status_code == 404, denied_recovery.text
    assert denied_recovery.json()["error"]["code"] == "checker_model_control_not_found"

    assert await _model_control_counts() == {
        "checker_model_profiles": 1,
        "checker_model_budget_configurations": 1,
        "checker_model_budget_accounts": 1,
        "checker_model_call_attempts": 0,
        "project.model_profile.provision:true": 2,
        "project.model_profile.provision:false": 1,
        "project.model_budget.configure:true": 2,
        "project.model_budget.configure:false": 1,
        "project.model_call.recovery_child.authorize:false": 1,
    }
