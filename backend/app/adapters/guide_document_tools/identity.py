"""Fail-closed Linux identity transitions for the isolated parser broker and children."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os


BROKER_UID = 10_002
BROKER_GID = 10_001
HEALTHCHECK_UID = 10_001
HEALTHCHECK_GID = 10_001

CAP_KILL = 5
CAP_SETGID = 6
CAP_SETUID = 7
BROKER_CAPABILITY_MASK = sum(1 << capability for capability in (CAP_KILL, CAP_SETGID, CAP_SETUID))

PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4
PR_SET_KEEPCAPS = 8
PR_GET_NO_NEW_PRIVS = 39
PR_CAP_AMBIENT = 47
PR_CAP_AMBIENT_CLEAR_ALL = 4
_LINUX_CAPABILITY_VERSION_3 = 0x20080522


@dataclass(frozen=True, slots=True)
class ChildIdentity:
    """One closed per-slot kernel identity."""

    uid: int
    gid: int


CHILD_IDENTITIES = (ChildIdentity(10_003, 10_003), ChildIdentity(10_004, 10_004))


class _CapabilityHeader(ctypes.Structure):
    _fields_ = (("version", ctypes.c_uint32), ("pid", ctypes.c_int))


class _CapabilityData(ctypes.Structure):
    _fields_ = (
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    )


_LIBC = ctypes.CDLL(None, use_errno=True)
_LIBC.prctl.argtypes = (
    ctypes.c_int,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_ulong,
    ctypes.c_ulong,
)
_LIBC.prctl.restype = ctypes.c_int
_LIBC.capget.argtypes = (
    ctypes.POINTER(_CapabilityHeader),
    ctypes.POINTER(_CapabilityData),
)
_LIBC.capget.restype = ctypes.c_int
_LIBC.capset.argtypes = (
    ctypes.POINTER(_CapabilityHeader),
    ctypes.POINTER(_CapabilityData),
)
_LIBC.capset.restype = ctypes.c_int


def _checked(result: int, operation: str) -> int:
    if result == -1:
        error = ctypes.get_errno()
        raise RuntimeError(f"guide parser identity operation failed: {operation}:{error}")
    return result


def _prctl(option: int, argument: int = 0) -> int:
    return _checked(_LIBC.prctl(option, argument, 0, 0, 0), "prctl")


def _capability_masks() -> tuple[int, int, int]:
    header = _CapabilityHeader(_LINUX_CAPABILITY_VERSION_3, 0)
    data = (_CapabilityData * 2)()
    _checked(_LIBC.capget(ctypes.byref(header), data), "capget")
    effective = data[0].effective | data[1].effective << 32
    permitted = data[0].permitted | data[1].permitted << 32
    inheritable = data[0].inheritable | data[1].inheritable << 32
    return effective, permitted, inheritable


def _set_capability_masks(*, effective: int, permitted: int, inheritable: int) -> None:
    header = _CapabilityHeader(_LINUX_CAPABILITY_VERSION_3, 0)
    data = (_CapabilityData * 2)()
    for index, shift in enumerate((0, 32)):
        data[index].effective = effective >> shift & 0xFFFFFFFF
        data[index].permitted = permitted >> shift & 0xFFFFFFFF
        data[index].inheritable = inheritable >> shift & 0xFFFFFFFF
    _checked(_LIBC.capset(ctypes.byref(header), data), "capset")


def _ambient_capability_mask() -> int:
    value = _status_fields().get("CapAmb")
    if value is None:
        raise RuntimeError("guide parser ambient capability state is unavailable")
    return int(value, 16)


def _status_fields() -> dict[str, str]:
    values: dict[str, str] = {}
    with open("/proc/self/status", encoding="ascii") as status:
        for line in status:
            name, separator, value = line.partition(":")
            if separator:
                values[name] = value.strip()
    return values


def _require_no_new_privileges() -> None:
    if _prctl(PR_GET_NO_NEW_PRIVS) != 1:
        raise RuntimeError("guide parser no-new-privileges state is invalid")


def _require_ids(uid: int, gid: int) -> None:
    if os.getresuid() != (uid, uid, uid) or os.getresgid() != (gid, gid, gid):
        raise RuntimeError("guide parser process identity is invalid")
    if os.getgroups():
        raise RuntimeError("guide parser supplementary groups are not empty")


def _require_capabilities(mask: int) -> None:
    effective, permitted, inheritable = _capability_masks()
    if (
        effective != mask
        or permitted != mask
        or inheritable != 0
        or _ambient_capability_mask() != 0
    ):
        raise RuntimeError("guide parser process capabilities are invalid")


def _require_dumpable_zero() -> None:
    if _prctl(PR_GET_DUMPABLE) != 0:
        raise RuntimeError("guide parser dumpable state is invalid")


def _clear_ambient_capabilities() -> None:
    _prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL)


def _require_privileged_bootstrap() -> None:
    _require_no_new_privileges()
    if os.getresuid() != (0, 0, 0) or os.getresgid() != (0, 0, 0):
        raise RuntimeError("guide parser privileged bootstrap identity is invalid")
    if set(os.getgroups()) - {0}:
        raise RuntimeError("guide parser privileged bootstrap groups are invalid")
    _require_capabilities(BROKER_CAPABILITY_MASK)


def bootstrap_broker_identity() -> None:
    """Drop root while retaining only the broker's three required capabilities."""
    _require_privileged_bootstrap()
    _prctl(PR_SET_KEEPCAPS, 1)
    os.setgroups([])
    os.setresgid(BROKER_GID, BROKER_GID, BROKER_GID)
    os.setresuid(BROKER_UID, BROKER_UID, BROKER_UID)
    _set_capability_masks(
        effective=BROKER_CAPABILITY_MASK,
        permitted=BROKER_CAPABILITY_MASK,
        inheritable=0,
    )
    _clear_ambient_capabilities()
    _prctl(PR_SET_DUMPABLE, 0)
    verify_broker_identity()


def verify_broker_identity() -> None:
    """Require the exact long-lived broker identity."""
    _require_no_new_privileges()
    _require_ids(BROKER_UID, BROKER_GID)
    _require_capabilities(BROKER_CAPABILITY_MASK)
    _require_dumpable_zero()


def prepare_child_identity(identity: ChildIdentity) -> None:
    """Enter one slot identity and clear all capabilities before exec."""
    if identity not in CHILD_IDENTITIES:
        raise RuntimeError("guide parser child slot identity is invalid")
    verify_broker_identity()
    os.setgroups([])
    os.setresgid(identity.gid, identity.gid, identity.gid)
    os.setresuid(identity.uid, identity.uid, identity.uid)
    _set_capability_masks(effective=0, permitted=0, inheritable=0)
    _clear_ambient_capabilities()
    _prctl(PR_SET_KEEPCAPS, 0)
    _prctl(PR_SET_DUMPABLE, 0)
    verify_child_identity(identity)


def verify_child_identity(identity: ChildIdentity) -> None:
    """Require an exact capability-free child state."""
    if identity not in CHILD_IDENTITIES:
        raise RuntimeError("guide parser child slot identity is invalid")
    _require_no_new_privileges()
    _require_ids(identity.uid, identity.gid)
    _require_capabilities(0)
    _require_dumpable_zero()


def child_identity_from_environment() -> ChildIdentity:
    """Reapply post-exec hardening, then verify the broker-issued slot."""
    try:
        identity = ChildIdentity(
            uid=int(os.environ["WORKSTREAM_GUIDE_PARSER_CHILD_UID"]),
            gid=int(os.environ["WORKSTREAM_GUIDE_PARSER_CHILD_GID"]),
        )
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("guide parser child slot environment is invalid") from None
    # Linux resets dumpable across exec for an ordinary executable. Restore the
    # required value before parser imports or framed source reads.
    _prctl(PR_SET_DUMPABLE, 0)
    verify_child_identity(identity)
    return identity


def drop_healthcheck_identity() -> None:
    """Drop a healthcheck exec directly to the capability-free socket client."""
    _require_privileged_bootstrap()
    os.setgroups([])
    os.setresgid(HEALTHCHECK_GID, HEALTHCHECK_GID, HEALTHCHECK_GID)
    os.setresuid(HEALTHCHECK_UID, HEALTHCHECK_UID, HEALTHCHECK_UID)
    _set_capability_masks(effective=0, permitted=0, inheritable=0)
    _clear_ambient_capabilities()
    _prctl(PR_SET_DUMPABLE, 0)
    _require_no_new_privileges()
    _require_ids(HEALTHCHECK_UID, HEALTHCHECK_GID)
    _require_capabilities(0)
    _require_dumpable_zero()


def security_state() -> dict[str, object]:
    """Return non-secret kernel identity evidence for container regressions."""
    effective, permitted, inheritable = _capability_masks()
    status = _status_fields()
    return {
        "uids": os.getresuid(),
        "gids": os.getresgid(),
        "groups": tuple(os.getgroups()),
        "cap_effective": effective,
        "cap_permitted": permitted,
        "cap_inheritable": inheritable,
        "cap_ambient": int(status.get("CapAmb", "-1"), 16),
        "cap_bounding": int(status.get("CapBnd", "-1"), 16),
        "no_new_privileges": _prctl(PR_GET_NO_NEW_PRIVS),
        "dumpable": _prctl(PR_GET_DUMPABLE),
    }


__all__ = (
    "BROKER_CAPABILITY_MASK",
    "BROKER_GID",
    "BROKER_UID",
    "CHILD_IDENTITIES",
    "HEALTHCHECK_GID",
    "HEALTHCHECK_UID",
    "ChildIdentity",
    "bootstrap_broker_identity",
    "child_identity_from_environment",
    "drop_healthcheck_identity",
    "prepare_child_identity",
    "security_state",
    "verify_broker_identity",
    "verify_child_identity",
)
