"""Qualified OpenRouter request controls shared by guide runtime adapters."""


def openrouter_request_options() -> dict[str, object]:
    """Request fixed routing and disable plugins that accept request overrides.

    Alignment currently rejects an ``enabled`` key, even when false. All account
    plugins must therefore be disabled operationally before private guide use;
    enforced account settings can also override these per-request controls.
    ``data_collection=deny`` is not a zero-data-retention guarantee.
    """
    return {
        "provider": {"allow_fallbacks": False, "data_collection": "deny"},
        "plugins": [
            {"id": plugin, "enabled": False}
            for plugin in (
                "web", "file-parser", "response-healing", "armor",
                "pareto-router", "context-compression",
            )
        ],
    }
