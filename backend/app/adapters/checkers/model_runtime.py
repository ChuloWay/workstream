"""Compose the private model listener with the existing AUTH, CHECKERS and ART owners."""

from contextlib import asynccontextmanager
import os

from app.adapters.artifacts import (
    artifact_preparation_service,
    artifact_provider_activation_guard,
    checker_output_binding,
    checker_output_storage,
    configured_artifact_storage_namespace,
    create_artifact_scratch_manager,
    create_artifact_store_bootstrap,
    validate_configured_artifact_storage_namespace,
)
from app.adapters.auth import checker_model_service_authorization
from app.adapters.checkers import (
    checker_model_proxy,
    create_checker_model_provider,
    model_call_service,
    model_invocation_grants,
    model_profile_reader,
)
from app.adapters.checkers.model_provider import (
    OpenAIResponsesSettings,
)
from app.adapters.checkers.model_proxy_transport import ModelProxyTransport
from app.modules.checkers.api.model_calls import ModelCallUnavailable, ProjectModelProfile


@asynccontextmanager
async def configured_model_provider(profile: ProjectModelProfile):
    """Construct exactly the provider selected by a trusted immutable profile."""
    spec = profile.spec
    if (spec.provider, spec.api) != ("openai_responses", "responses.v1"):
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ModelCallUnavailable("model_provider_credentials_unavailable")
    provider = create_checker_model_provider(
        OpenAIResponsesSettings(
            api_key=key,
            model=spec.model_snapshot,
            maximum_request_bytes=spec.maximum_request_bytes,
            maximum_input_tokens=spec.maximum_input_tokens,
            maximum_output_tokens=spec.maximum_output_tokens,
            maximum_output_bytes=spec.maximum_output_bytes,
            request_timeout_seconds=float(spec.deadline_ms / 1000),
            reasoning_effort=spec.settings.reasoning_effort,
            text_verbosity=spec.settings.text_verbosity,
        )
    )
    try:
        yield provider
    finally:
        await provider.aclose()


@asynccontextmanager
async def configured_model_proxy_runtime(settings, sessions):
    """Own one optional listener and retain its storage resources until handlers drain."""
    if settings.checker_model_proxy_socket is None:
        yield
        return
    bootstrap = create_artifact_store_bootstrap(
        settings,
        activation_guard=artifact_provider_activation_guard(settings, sessions),
    )
    manager = None
    try:
        claim = await validate_configured_artifact_storage_namespace(
            bootstrap,
            settings,
            sessions,
        )
        store = bootstrap.initialize_after_namespace_claim(claim)
        namespace = configured_artifact_storage_namespace(settings, bootstrap)
        manager = create_artifact_scratch_manager(settings)
        outputs = checker_output_storage(
            sessions=sessions,
            store=store,
            namespace=namespace,
            preparation=artifact_preparation_service(manager),
            settings=settings,
        )
        proxy = checker_model_proxy(
            sessions=sessions,
            authorization=checker_model_service_authorization,
            grants=model_invocation_grants,
            calls=model_call_service,
            profiles=model_profile_reader,
            outputs=outputs,
            bindings=lambda session: checker_output_binding(session, namespace=namespace),
            provider=configured_model_provider,
        )
        async with ModelProxyTransport(
            socket_path=settings.checker_model_proxy_socket,
            handler=proxy.handle,
            shutdown_timeout_seconds=7200.0,
        ):
            yield
    finally:
        if manager is not None:
            manager.close()
        bootstrap.close()
