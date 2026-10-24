"""Singleton private model-proxy process; durable effects live in CHECKERS and ART."""

import asyncio
import signal

from app.adapters.checkers.model_runtime import configured_model_proxy_runtime
from app.core.config import get_settings
from app.db.session import dispose_engine, get_session_factory


async def serve() -> None:
    """Serve the configured private socket until termination, then drain admitted work."""
    settings = get_settings()
    if settings.checker_model_proxy_socket is None:
        raise RuntimeError("checker model proxy socket is required")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for signum in signals:
        loop.add_signal_handler(signum, stop.set)
    try:
        async with configured_model_proxy_runtime(settings, get_session_factory()):
            await stop.wait()
    finally:
        for signum in signals:
            loop.remove_signal_handler(signum)
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(serve())
