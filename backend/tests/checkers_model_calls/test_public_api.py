"""Public Operator contract for checker model profile, budget and recovery controls."""

from datetime import UTC, datetime, timedelta

import pytest

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

        async def prepare_recovery_child(self, execution, slot, **values):
            self.calls.append(("child", execution, slot, values))
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
        execution=execution,
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
        execution,
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
