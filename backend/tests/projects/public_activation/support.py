"""Existing approved-guide fixtures, with public Finance and manager operations."""

from contextlib import asynccontextmanager
from uuid import uuid4

from tests.projects.post_policy.public_support import public_approved_case, deliver
from tests.projects.guide_compilation.proposals.public_support import proposal_client, proposal_path
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor, seed_selected_review_revision_inputs
from tests.contributions.public_policy.support import UNPAID


def activation_body(package):
    """Copy the displayed selections as an API client, without database lookups."""
    context = package["activation_context"]
    return dict(
        target=package["target"],
        post_approval_operation_id=context["post_approval_operation_id"],
        post_approval_output_digest=context["post_approval_output_digest"],
        guide_mutation_generation=context["guide_mutation_generation"],
        review=context["review"], revision=context["revision"],
        **context["contribution"],
        expected_previous_active_guide_id=context["expected_previous_active_guide_id"],
        expected_previous_active_guide_generation=context["expected_previous_active_guide_generation"],
    )


async def publish(client, project_id):
    root = f"/api/v1/projects/{project_id}/contribution-policies"
    response = await client.post(root + "/drafts", json={"name": "Governed project policy"}, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 201, response.text
    receipt = response.json()
    version = root + f"/{receipt['contribution_policy_id']}/versions/{receipt['contribution_policy_version_id']}"
    response = await client.put(version, json=UNPAID, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 200, response.text
    response = await client.post(version + "/publication", json={}, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json(), version


@asynccontextmanager
async def activation_case(url, monkeypatch, worker):
    async with public_approved_case(url, monkeypatch) as (factory, command, actor, grant, approval_id, _):
        await seed_selected_review_revision_inputs(factory, command, actor)
        outcome = deliver(worker, approval_id)
        assert outcome["status"] == "policy_draft_ready", outcome
        policy_path = proposal_path(command) + "/post-submission-policies/" + outcome["policy_id"]
        finance, _ = await seed_review_actor(factory, command.project_id, role="finance_authority")
        async with proposal_client(factory, actor) as manager, proposal_client(factory, finance) as finance_client:
            before = await manager.get(policy_path)
            assert before.status_code == 200, before.text
            assert before.json()["activation_context"]["contribution"] is None
            assert before.json()["activation_context"]["post_approval_operation_id"] is None
            result = await manager.post(policy_path + "/approval", json={"target": before.json()["target"]}, headers={"Idempotency-Key": str(uuid4())})
            assert result.status_code == 200, result.text
            published, version_path = await publish(finance_client, command.project_id)
            response = await manager.get(policy_path)
            assert response.status_code == 200, response.text
            body = activation_body(response.json())
            path = f"/api/v1/projects/{command.project_id}/guides/{command.guide_id}/activate"
            yield factory, command, actor, grant, manager, finance_client, policy_path, path, body, published, version_path
