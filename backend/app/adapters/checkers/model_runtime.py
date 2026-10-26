"""Compose the private model listener with the existing AUTH, CHECKERS and ART owners."""

import os
from contextlib import asynccontextmanager

from app.adapters.artifacts import (
    artifact_preparation_service,
    artifact_provider_activation_guard,
    checker_output_binding,
    checker_output_storage,
    configured_artifact_storage_namespace,
    create_artifact_scratch_manager,
    create_artifact_store_bootstrap,
    setup_model_evidence,
    setup_model_output_binding,
    setup_model_output_storage,
    validate_configured_artifact_storage_namespace,
)
from app.adapters.auth import (
    checker_model_service_authorization,
    setup_model_service_authorization,
)
from app.adapters.checkers import (
    checker_model_proxy,
    create_checker_model_provider,
    model_call_service,
    model_invocation_grants,
    model_profile_reader,
)
from app.adapters.checkers.model_proxy_transport import ModelProxyTransport
from app.adapters.model_usage import setup_model_usage_service
from app.adapters.project_agents.setup_model_handler import (
    SetupModelProxyHandler,
    configured_setup_provider,
)
from app.adapters.projects import setup_model_usage_owner
from app.modules.model_usage.api import ModelCallUnavailable, ProjectModelProfile


@asynccontextmanager
async def configured_model_provider(profile: ProjectModelProfile):
    """Construct exactly the provider selected by a trusted immutable profile."""
    spec = profile.spec
    credential = {
        ("openai_responses", "responses.v1"): "OPENAI_API_KEY",
        ("openrouter", "chat_completions"): "OPENROUTER_API_KEY",
    }.get((spec.provider, spec.api))
    if credential is None:
        raise ModelCallUnavailable("model_profile_provider_unavailable")
    key = os.environ.get(credential, "")
    if not key:
        raise ModelCallUnavailable("model_provider_credentials_unavailable")
    provider = create_checker_model_provider(profile, api_key=key)
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
        setup_outputs = setup_model_output_storage(
            sessions=sessions,
            store=store,
            namespace=namespace,
            preparation=artifact_preparation_service(manager),
            settings=settings,
            owner=setup_model_usage_owner,
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
        setup_proxy = SetupModelProxyHandler(
            sessions=sessions,
            authorization=setup_model_service_authorization,
            calls=lambda session, authority: setup_model_usage_service(
                session,
                authority=authority,
                evidence=setup_model_evidence(session),
                owner=setup_model_usage_owner(session),
            ),
            profiles=model_profile_reader,
            outputs=setup_outputs,
            bindings=lambda session: setup_model_output_binding(
                session,
                namespace=namespace,
                owner=setup_model_usage_owner(session),
            ),
            provider=configured_setup_provider,
        )
        async with ModelProxyTransport(
            socket_path=settings.checker_model_proxy_socket,
            handler=proxy.handle,
            setup_handler=setup_proxy.handle,
            shutdown_timeout_seconds=7200.0,
        ):
            yield
    finally:
        if manager is not None:
            manager.close()
        bootstrap.close()
