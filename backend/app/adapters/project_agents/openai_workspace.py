"""Historical exact-ID cleanup for retained OpenAI guide-runtime resources."""

from __future__ import annotations

import asyncio
import os


_OPENAI_BASE_URL = "https://api.openai.com/v1"
_CLEANUP_TIMEOUT_SECONDS = 30


async def cleanup_recorded_openai_guide_resources(client, custody) -> bool:
    """Delete recorded OpenAI resources only; never discover or create provider IDs."""
    from openai import NotFoundError

    try:
        recorded = await custody.cleanup_resources()
    except Exception:
        return False
    removed_containers: set[str] = set()
    for kind in ("container", "attachment", "file"):
        for item in recorded:
            if item.kind != kind:
                continue
            try:
                if kind == "attachment":
                    if item.parent_provider_id not in removed_containers:
                        try:
                            await client.containers.retrieve(item.parent_provider_id)
                        except NotFoundError:
                            removed_containers.add(item.parent_provider_id)
                        else:
                            raise RuntimeError("parent container cleanup is unresolved")
                elif kind == "container":
                    try:
                        await client.containers.delete(item.provider_id)
                    except NotFoundError:
                        pass
                    try:
                        await client.containers.retrieve(item.provider_id)
                    except NotFoundError:
                        removed_containers.add(item.provider_id)
                    else:
                        raise RuntimeError("guide container deletion is unresolved")
                else:
                    try:
                        deletion = await client.files.delete(item.provider_id)
                        if deletion.id != item.provider_id or deletion.deleted is not True:
                            raise RuntimeError("guide file deletion is unresolved")
                    except NotFoundError:
                        pass
                    try:
                        await client.files.retrieve(item.provider_id)
                    except NotFoundError:
                        pass
                    else:
                        raise RuntimeError("guide file deletion is unresolved")
                await custody.record_deleted(item.allocation_id)
            except Exception:
                try:
                    await custody.record_cleanup_failed(item.allocation_id)
                except Exception:
                    pass
    try:
        return not await custody.cleanup_resources()
    except Exception:
        return False


async def cleanup_retained_openai_guide_resources(custody) -> bool:
    """Clean retained OpenAI facts with a dedicated OpenAI-origin credential only."""
    from openai import AsyncOpenAI, DefaultAsyncHttpx2Client

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return False
    try:
        async with asyncio.timeout(_CLEANUP_TIMEOUT_SECONDS):
            async with AsyncOpenAI(
                api_key=api_key,
                base_url=_OPENAI_BASE_URL,
                http_client=DefaultAsyncHttpx2Client(
                    trust_env=False,
                    follow_redirects=False,
                ),
                max_retries=0,
                timeout=_CLEANUP_TIMEOUT_SECONDS,
            ) as client:
                return await cleanup_recorded_openai_guide_resources(client, custody)
    except Exception:
        return False


__all__ = (
    "cleanup_recorded_openai_guide_resources",
    "cleanup_retained_openai_guide_resources",
)
