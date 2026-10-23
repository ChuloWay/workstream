"""Isolated AWS IAM Roles Anywhere credentials for artifact workloads."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
from typing import Any, Literal

from aiobotocore.credentials import AioRefreshableCredentials
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID

from app.core.config import Settings
from app.interfaces.artifacts import ArtifactConfigurationError


_AWS_SIGNING_HELPER_PATH = Path("/usr/local/bin/aws_signing_helper")
_AWS_SIGNING_HELPER_SHA256_BY_MACHINE = {
    "x86_64": "beec9ed1c492d93db809890f16713e3556353294b823c2184ad4e891f1b2b54d",
    "aarch64": "3d131aa888cd56da446f9c6bb460b1f0569f6c7edc74eae6193a2fe3928883ba",
}
_HELPER_TIMEOUT_SECONDS = 15.0
_HELPER_TERMINATION_SECONDS = 1.0
_ISOLATION_PROOF_TIMEOUT_SECONDS = 65.0
_MAX_HELPER_STDOUT_BYTES = 32 * 1024
_MAX_HELPER_STDERR_BYTES = 16 * 1024
_MAX_CERTIFICATE_BYTES = 64 * 1024
_MAX_PRIVATE_KEY_BYTES = 64 * 1024
_MAX_SIGNING_HELPER_BYTES = 32 * 1024 * 1024
_ACCESS_DENIED_TOKEN = re.compile(
    rb"(?m)^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} "
    rb"operation error RolesAnywhere: CreateSession,"
    rb"(?: [^,\r\n]{1,512},)* AccessDeniedException:"
)
_ACCESS_KEY = re.compile(r"^[A-Z0-9]{16,128}$")


@dataclass(frozen=True, slots=True)
class RolesAnywhereRoleIsolationProof:
    """Bounded proof facts that contain no credential or certificate material."""

    initial_own_role_succeeded: bool
    other_roles_access_denied: bool
    final_own_role_succeeded: bool


@dataclass(frozen=True, slots=True)
class _ValidatedIdentity:
    certificate_fd: int
    private_key_fd: int


@dataclass(frozen=True, slots=True)
class _CredentialAttempt:
    outcome: Literal["success", "access-denied", "failure"]
    metadata: dict[str, str] | None = None


class _OutputOverflow(Exception):
    """Private control signal carrying no process output."""


class RolesAnywhereCredentialProvider:
    """One refreshable SDK provider backed only by the pinned signing helper."""

    METHOD = "roles-anywhere"

    def __init__(self, settings: Settings, *, role_arn: str) -> None:
        self._settings = settings
        self._role_arn = role_arn

    async def load(self) -> AioRefreshableCredentials:
        """Acquire the first session and install the same isolated refresh path."""
        metadata = await self._refresh()
        return AioRefreshableCredentials.create_from_metadata(
            metadata,
            refresh_using=self._refresh,
            method=self.METHOD,
        )

    async def _refresh(self) -> dict[str, str]:
        attempt = await _request_credentials(self._settings, role_arn=self._role_arn)
        if attempt.outcome != "success" or attempt.metadata is None:
            raise ArtifactConfigurationError(
                "Roles Anywhere credentials could not be resolved"
            ) from None
        return attempt.metadata


def create_roles_anywhere_credential_provider(
    settings: Settings,
    *,
    require_runtime_role: bool,
) -> RolesAnywhereCredentialProvider:
    """Construct one selected provider without invoking the helper."""
    if settings.artifact_s3_aws_workload_identity_method != "roles-anywhere":
        raise ArtifactConfigurationError("Roles Anywhere workload identity is not selected")
    role_arn = settings.artifact_s3_roles_anywhere_role_arn
    if role_arn is None:
        raise ArtifactConfigurationError("Roles Anywhere workload role is unavailable")
    if require_runtime_role and role_arn != settings.artifact_s3_runtime_role_arn:
        raise ArtifactConfigurationError(
            "Roles Anywhere runtime identity must select the runtime role"
        )
    return RolesAnywhereCredentialProvider(settings, role_arn=role_arn)


async def prove_roles_anywhere_role_isolation(
    settings: Settings,
) -> RolesAnywhereRoleIsolationProof:
    """Prove own, exact cross-role denial, then own credentials in one window."""
    provider = create_roles_anywhere_credential_provider(
        settings,
        require_runtime_role=False,
    )
    own_role = provider._role_arn
    roles = (
        settings.artifact_s3_runtime_role_arn,
        settings.artifact_s3_readiness_role_arn,
        settings.artifact_s3_negative_role_arn,
    )
    if any(role is None for role in roles) or own_role not in roles:
        raise ArtifactConfigurationError("Roles Anywhere workload roles are invalid")
    other_roles = tuple(role for role in roles if role != own_role)
    if len(other_roles) != 2:
        raise ArtifactConfigurationError("Roles Anywhere workload roles are invalid")

    try:
        async with asyncio.timeout(_ISOLATION_PROOF_TIMEOUT_SECONDS):
            initial = await _request_credentials(settings, role_arn=own_role)
            if initial.outcome != "success":
                raise ArtifactConfigurationError(
                    "Roles Anywhere own-role credential proof failed"
                ) from None
            denied = []
            for role_arn in other_roles:
                attempt = await _request_credentials(settings, role_arn=role_arn)
                denied.append(attempt.outcome == "access-denied")
            if not all(denied):
                raise ArtifactConfigurationError(
                    "Roles Anywhere cross-role denial proof failed"
                ) from None
            final = await _request_credentials(settings, role_arn=own_role)
            if final.outcome != "success":
                raise ArtifactConfigurationError(
                    "Roles Anywhere final own-role credential proof failed"
                ) from None
    except TimeoutError:
        raise ArtifactConfigurationError(
            "Roles Anywhere role isolation proof exceeded its deadline"
        ) from None

    return RolesAnywhereRoleIsolationProof(
        initial_own_role_succeeded=True,
        other_roles_access_denied=True,
        final_own_role_succeeded=True,
    )


async def _request_credentials(
    settings: Settings,
    *,
    role_arn: str,
) -> _CredentialAttempt:
    identity: _ValidatedIdentity | None = None
    try:
        identity = _open_and_validate_identity(settings)
        _validate_signing_helper()
        attempt = await _execute_signing_helper(
            settings,
            role_arn=role_arn,
            identity=identity,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ArtifactConfigurationError(
            "Roles Anywhere credential identity is invalid"
        ) from None
    finally:
        if identity is not None:
            _close_identity(identity)
    return attempt


def _open_and_validate_identity(settings: Settings) -> _ValidatedIdentity:
    certificate_path = settings.artifact_s3_roles_anywhere_certificate_file
    private_key_path = settings.artifact_s3_roles_anywhere_private_key_file
    selected_role = settings.artifact_s3_roles_anywhere_role_arn
    if certificate_path is None or private_key_path is None or selected_role is None:
        raise ValueError("incomplete identity")
    certificate_fd = _open_private_regular_file(certificate_path)
    try:
        private_key_fd = _open_private_regular_file(private_key_path)
    except Exception:
        os.close(certificate_fd)
        raise
    try:
        certificate_bytes = _read_bounded_file(
            certificate_fd,
            maximum_bytes=_MAX_CERTIFICATE_BYTES,
        )
        private_key_bytes = _read_bounded_file(
            private_key_fd,
            maximum_bytes=_MAX_PRIVATE_KEY_BYTES,
        )
        certificate = x509.load_pem_x509_certificate(certificate_bytes)
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
        certificate_bytes = b""
        private_key_bytes = b""
        certificate_public_key = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_public_key = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if certificate_public_key != private_public_key:
            raise ValueError("identity mismatch")
        now = datetime.datetime.now(datetime.UTC)
        if certificate.not_valid_before_utc > now or certificate.not_valid_after_utc <= now:
            raise ValueError("certificate validity")
        try:
            basic_constraints = certificate.extensions.get_extension_for_class(
                x509.BasicConstraints
            ).value
        except x509.ExtensionNotFound:
            basic_constraints = None
        if basic_constraints is not None and basic_constraints.ca:
            raise ValueError("CA certificate")
        common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        expected_common_name = selected_role.rsplit("/", 1)[-1]
        if len(common_names) != 1 or common_names[0].value != expected_common_name:
            raise ValueError("certificate subject")
        return _ValidatedIdentity(certificate_fd, private_key_fd)
    except Exception:
        os.close(certificate_fd)
        os.close(private_key_fd)
        raise


def _open_private_regular_file(path: Path) -> int:
    if not path.is_absolute():
        raise ValueError("identity path")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    file_descriptor = os.open(path, flags)
    try:
        file_stat = os.fstat(file_descriptor)
        mode = stat.S_IMODE(file_stat.st_mode)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("identity file type")
        if file_stat.st_uid != os.geteuid():
            raise ValueError("identity owner")
        if mode & 0o077 or not mode & 0o400:
            raise ValueError("identity mode")
        return file_descriptor
    except Exception:
        os.close(file_descriptor)
        raise


def _read_bounded_file(file_descriptor: int, *, maximum_bytes: int) -> bytes:
    value = os.pread(file_descriptor, maximum_bytes + 1, 0)
    if len(value) > maximum_bytes:
        value = b""
        raise ValueError("identity file size")
    return value


def _close_identity(identity: _ValidatedIdentity) -> None:
    for file_descriptor in (identity.certificate_fd, identity.private_key_fd):
        try:
            os.close(file_descriptor)
        except OSError:
            pass


def _validate_signing_helper() -> None:
    expected_hash = _AWS_SIGNING_HELPER_SHA256_BY_MACHINE.get(platform.machine())
    if expected_hash is None or platform.system() != "Linux":
        raise ValueError("unsupported helper platform")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    helper_fd = os.open(_AWS_SIGNING_HELPER_PATH, flags)
    try:
        helper_stat = os.fstat(helper_fd)
        helper_mode = stat.S_IMODE(helper_stat.st_mode)
        if (
            not stat.S_ISREG(helper_stat.st_mode)
            or not 1 <= helper_stat.st_size <= _MAX_SIGNING_HELPER_BYTES
            or helper_stat.st_uid not in {0, os.geteuid()}
            or helper_mode & 0o022
            or not helper_mode & 0o100
        ):
            raise ValueError("helper custody")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(helper_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError("helper digest")
    finally:
        os.close(helper_fd)


async def _execute_signing_helper(
    settings: Settings,
    *,
    role_arn: str,
    identity: _ValidatedIdentity,
) -> _CredentialAttempt:
    trust_anchor_arn = settings.artifact_s3_roles_anywhere_trust_anchor_arn
    profile_arn = settings.artifact_s3_roles_anywhere_profile_arn
    region = settings.artifact_s3_region
    if trust_anchor_arn is None or profile_arn is None or region is None:
        return _CredentialAttempt("failure")
    command = (
        str(_AWS_SIGNING_HELPER_PATH),
        "credential-process",
        "--certificate",
        f"/proc/self/fd/{identity.certificate_fd}",
        "--private-key",
        f"/proc/self/fd/{identity.private_key_fd}",
        "--trust-anchor-arn",
        trust_anchor_arn,
        "--profile-arn",
        profile_arn,
        "--role-arn",
        role_arn,
        "--region",
        region,
    )
    process: asyncio.subprocess.Process | None = None
    helper_tasks: list[asyncio.Task[Any]] = []
    stdout = b""
    stderr = b""
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"LANG": "C", "LC_ALL": "C"},
            start_new_session=True,
            pass_fds=(identity.certificate_fd, identity.private_key_fd),
        )
        assert process.stdout is not None and process.stderr is not None
        helper_tasks = [
            asyncio.create_task(
                _read_stream_bounded(
                    process.stdout,
                    maximum_bytes=_MAX_HELPER_STDOUT_BYTES,
                )
            ),
            asyncio.create_task(
                _read_stream_bounded(
                    process.stderr,
                    maximum_bytes=_MAX_HELPER_STDERR_BYTES,
                )
            ),
            asyncio.create_task(process.wait()),
        ]
        async with asyncio.timeout(_HELPER_TIMEOUT_SECONDS):
            stdout_result, stderr_result, return_code_result = await asyncio.gather(
                *helper_tasks
            )
        assert isinstance(stdout_result, bytes)
        assert isinstance(stderr_result, bytes)
        assert isinstance(return_code_result, int)
        stdout = stdout_result
        stderr = stderr_result
        return_code = return_code_result
    except asyncio.CancelledError:
        stdout = b""
        stderr = b""
        await _shielded_helper_cleanup(process, helper_tasks)
        raise
    except (TimeoutError, _OutputOverflow, OSError):
        stdout = b""
        stderr = b""
        await _shielded_helper_cleanup(process, helper_tasks)
        return _CredentialAttempt("failure")
    finally:
        await _shielded_helper_cleanup(process, helper_tasks)

    if return_code != 0:
        access_denied = _ACCESS_DENIED_TOKEN.search(stderr) is not None
        stdout = b""
        stderr = b""
        return _CredentialAttempt("access-denied" if access_denied else "failure")
    if stderr.strip():
        stdout = b""
        stderr = b""
        return _CredentialAttempt("failure")
    metadata = _parse_credential_process_output(stdout)
    stdout = b""
    stderr = b""
    if metadata is None:
        return _CredentialAttempt("failure")
    return _CredentialAttempt("success", metadata)


async def _read_stream_bounded(
    stream: asyncio.StreamReader,
    *,
    maximum_bytes: int,
) -> bytes:
    buffer = bytearray()
    try:
        while True:
            chunk = await stream.read(min(8192, maximum_bytes + 1 - len(buffer)))
            if not chunk:
                return bytes(buffer)
            buffer.extend(chunk)
            if len(buffer) > maximum_bytes:
                raise _OutputOverflow
    finally:
        buffer.clear()


async def _shielded_helper_cleanup(
    process: asyncio.subprocess.Process | None,
    tasks: list[asyncio.Task[Any]],
) -> None:
    cleanup = asyncio.create_task(_cleanup_helper(process, tasks))
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        await cleanup
        raise


async def _cleanup_helper(
    process: asyncio.subprocess.Process | None,
    tasks: list[asyncio.Task[Any]],
) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if process is not None:
        await _stop_process(process)


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        _close_process_pipe_transports(process)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=_HELPER_TERMINATION_SECONDS)
        return
    except TimeoutError:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _close_process_pipe_transports(process)
    try:
        await asyncio.wait_for(process.wait(), timeout=_HELPER_TERMINATION_SECONDS)
    except TimeoutError:
        return


def _close_process_pipe_transports(process: asyncio.subprocess.Process) -> None:
    """Release paused helper pipes after owned process termination."""
    process_transport = getattr(process, "_transport", None)
    get_pipe_transport = getattr(process_transport, "get_pipe_transport", None)
    if not callable(get_pipe_transport):
        return
    for file_descriptor in (1, 2):
        pipe_transport = get_pipe_transport(file_descriptor)
        if pipe_transport is not None:
            pipe_transport.close()


def _parse_credential_process_output(output: bytes) -> dict[str, str] | None:
    parsed: object = None
    try:
        parsed = json.loads(output)
        if not isinstance(parsed, Mapping) or set(parsed) != {
            "Version",
            "AccessKeyId",
            "SecretAccessKey",
            "SessionToken",
            "Expiration",
        }:
            return None
        version = parsed["Version"]
        access_key = parsed["AccessKeyId"]
        secret_key = parsed["SecretAccessKey"]
        session_token = parsed["SessionToken"]
        expiration = parsed["Expiration"]
        if (
            version != 1
            or not isinstance(access_key, str)
            or _ACCESS_KEY.fullmatch(access_key) is None
            or not isinstance(secret_key, str)
            or not 1 <= len(secret_key) <= 4096
            or not isinstance(session_token, str)
            or not 1 <= len(session_token) <= 16384
            or not isinstance(expiration, str)
            or len(expiration) > 64
        ):
            return None
        expires_at = datetime.datetime.fromisoformat(expiration.replace("Z", "+00:00"))
        if expires_at.tzinfo is None or expires_at <= datetime.datetime.now(datetime.UTC):
            return None
        return {
            "access_key": access_key,
            "secret_key": secret_key,
            "token": session_token,
            "expiry_time": expiration,
        }
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    finally:
        parsed = None
