"""Real approval, AUTH, PostgreSQL and ART with an offline provider and image boundary."""

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy import select, func

from app.adapters.artifacts import checker_output_binding, checker_output_storage
from app.adapters.auth import checker_model_service_authorization
from app.adapters.checkers import model_call_service, model_invocation_grants, model_profile_reader
from app.adapters.checkers.model_execution import ModelAwareExternalExecution
from app.interfaces.checker_model_provider import (
    CheckerModelCreateOutcome,
    CheckerModelCreateResult,
    CheckerModelObservation,
    CheckerModelProviderStatus,
    CheckerModelResponseReference,
    CheckerModelUsage,
)
from app.interfaces.checker_model_proxy import ModelProxyRequest
from app.interfaces.external_services import ExternalServiceAdapterIdentity
from app.interfaces.project_agents import CapabilityParameter
from app.modules.actors.api import ServiceIdentity
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.model_calls.models import (
    CheckerModelCallAttempt,
    CheckerModelBudgetAccount,
)
from app.modules.checkers.model_calls.proxy import CheckerModelProxy
from tests.checkers.external.support import post_registry_spec
from tests.checkers.execution.support import (
    ControlledSelectedExecution,
    live_executor,
    reserve,
    provision_post_submit_service,
)
from tests.checkers_model_calls.test_public_api import profile_spec
from tests.post_submit_materialization_helpers import material_fixture


def model_registry_spec():
    spec = post_registry_spec()
    document = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "model_profile_id": {"type": "string"},
            "model_profile_version": {"type": "integer"},
            "model_profile_digest": {"type": "string"},
        },
        "required": ["model_profile_id", "model_profile_version", "model_profile_digest"],
    }
    return spec.model_copy(
        update={
            "configuration_schema": ExternalCheckerSchema(
                schema_id="acme.model_review.configuration",
                schema_version="v1",
                document=document,
                schema_sha256=external_checker_json_hash(document),
            )
        }
    )


async def test_public_profile_to_private_model_call_and_completed_checker(
    tmp_path,
    isolated_database_env,
    admin_access,
):
    await admin_access.signed.grant(admin_access.admin, admin_access.target, role="operator")
    profiles = []

    async def publish(_factory, project_id, registry):
        spec = profile_spec(project_id).model_copy(
            update={
                "registry_entry_id": registry.registry_entry_id,
                "registry_entry_digest": registry.entry_digest,
            }
        )
        response = await admin_access.signed.client.post(
            f"/api/v1/operations/projects/{project_id}/model-profiles",
            headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
            json=spec.model_dump(mode="json"),
        )
        assert response.status_code == 201, response.text
        profile = response.json()
        profiles.append(profile)
        budget = await admin_access.signed.client.post(
            f"/api/v1/operations/projects/{project_id}/model-budget-configurations",
            headers=admin_access.target.headers | {"Idempotency-Key": str(uuid4())},
            json={
                "project_id": str(project_id),
                "configuration_version": 1,
                "lifetime_limit_nanodollars": 10_000_000_000,
            },
        )
        assert budget.status_code == 201, budget.text
        return tuple(
            CapabilityParameter(name=key, value=value)
            for key, value in {
                "model_profile_id": profile["profile_id"],
                "model_profile_version": profile["spec"]["profile_version"],
                "model_profile_digest": profile["profile_digest"],
            }.items()
        )

    async with material_fixture(
        tmp_path,
        isolated_database_env,
        post_submit_registry_spec=model_registry_spec(),
        post_submit_binding_setup=publish,
    ) as h:
        await provision_post_submit_service(h.factory, ServiceIdentity.ARTIFACT_CHECKER_OUTPUT)
        creates = []

        class Provider:
            async def create(self, request):
                creates.append(request.prompt)
                reference = CheckerModelResponseReference("resp_composed")
                return CheckerModelCreateResult(
                    CheckerModelCreateOutcome.ACCEPTED,
                    known_response=reference,
                    observation=CheckerModelObservation(
                        reference,
                        profiles[0]["spec"]["model_snapshot"],
                        CheckerModelProviderStatus.COMPLETED,
                        '{"verdict":"passed"}',
                        CheckerModelUsage(20, 5, 10, 2, 30),
                    ),
                )

            async def recover(self, _):
                raise AssertionError("completed call must use its retained ART response")

        @asynccontextmanager
        async def provider(_):
            yield Provider()

        proxy = CheckerModelProxy(
            sessions=h.factory,
            authorization=checker_model_service_authorization,
            grants=model_invocation_grants,
            calls=model_call_service,
            profiles=model_profile_reader,
            outputs=checker_output_storage(
                sessions=h.factory,
                store=h.store,
                namespace=h.namespace,
                preparation=h.preparation,
                settings=h.settings,
            ),
            bindings=lambda session: checker_output_binding(session, namespace=h.namespace),
            provider=provider,
        )

        class Image(ControlledSelectedExecution):
            identity = ExternalServiceAdapterIdentity("external_checker_execution", "rust_unix")

            async def execute(self, request, grant, *, model_grant=None):
                assert model_grant is not None
                reply = await proxy.handle(
                    ModelProxyRequest(
                        model_grant.grant_id,
                        request.request_digest,
                        "Evaluate the verified work",
                    )
                )
                assert reply.outcome == "completed", reply.failure_code
                assert reply.output == '{"verdict":"passed"}'
                return await super().execute(request, grant)

        await reserve(h)
        executor = live_executor(
            h,
            selected_execution=ModelAwareExternalExecution(
                execution=Image(),
                sessions=h.factory,
            ),
        )
        result = await executor.evaluate_post_submission(h.request)
        assert result.outcome == "completed"
        assert len(result.execution.external_members) == 1
        assert await executor.evaluate_post_submission(h.request) == result
        assert len(creates) == 1
        async with h.factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(CheckerModelCallAttempt)) == 1
            )
            attempt = await session.scalar(select(CheckerModelCallAttempt))
            account = await session.get(CheckerModelBudgetAccount, str(h.request.project_id))
            assert attempt.state == "completed"
            assert account.lifetime_reserved_nanodollars == 0
            assert account.lifetime_settled_nanodollars == 15 * 11 + 5 * 2 + 10 * 29
            assert UUID(attempt.response_binding_id).version == 7
            assert UUID(attempt.request_binding_id).version == 7
