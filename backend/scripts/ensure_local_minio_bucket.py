"""Create and verify the checkout-local MinIO bucket before API startup."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import sys
from urllib.parse import urlsplit

from aiobotocore.session import AioSession
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings


def _validate_local_minio(settings: Settings) -> None:
    """Reject every non-local or non-MinIO target before a provider mutation."""
    endpoint = urlsplit(settings.artifact_s3_endpoint_url or "")
    if (
        settings.environment != "local"
        or settings.artifact_store_backend != "s3_compatible"
        or settings.artifact_s3_provider_profile != "minio"
        or endpoint.scheme != "http"
        or endpoint.hostname != "minio"
        or endpoint.port != 9000
        or endpoint.path not in {"", "/"}
        or endpoint.query
        or endpoint.fragment
    ):
        raise RuntimeError("local MinIO bucket provisioning is not configured")


async def ensure_local_minio_bucket(
    settings: Settings,
    *,
    session_factory: Callable[[], AioSession] = AioSession,
) -> str:
    """Idempotently create and verify the configured local MinIO bucket."""
    _validate_local_minio(settings)
    access_key = settings.artifact_s3_access_key_id
    secret_key = settings.artifact_s3_secret_access_key
    bucket = settings.artifact_s3_bucket
    if access_key is None or secret_key is None or bucket is None:
        raise RuntimeError("local MinIO bucket provisioning is incomplete")

    for attempt in range(1, 11):
        session = session_factory()
        session.set_credentials(access_key.get_secret_value(), secret_key.get_secret_value())
        try:
            async with session.create_client(
                "s3",
                endpoint_url=settings.artifact_s3_endpoint_url,
                region_name=settings.artifact_s3_region,
            ) as client:
                try:
                    await client.create_bucket(Bucket=bucket)
                except ClientError as error:
                    code = str(error.response.get("Error", {}).get("Code", ""))
                    if code != "BucketAlreadyOwnedByYou":
                        raise
                await client.head_bucket(Bucket=bucket)
            break
        except Exception:
            if attempt == 10:
                raise RuntimeError("local MinIO bucket provisioning failed") from None
            await asyncio.sleep(1)
    return bucket


def main() -> int:
    """Provision the bucket without printing credentials or provider errors."""
    try:
        bucket = asyncio.run(ensure_local_minio_bucket(get_settings()))
    except Exception as error:
        message = (
            str(error)
            if isinstance(error, RuntimeError)
            else "local MinIO provisioning failed"
        )
        print(message, file=sys.stderr)
        return 1
    print(f"local MinIO bucket ready: {bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
