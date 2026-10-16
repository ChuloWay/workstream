#!/usr/bin/env bash
set -uo pipefail

readonly REAL_DOCKER="${WS493_REAL_DOCKER:?}"
readonly DIND_NAME="${WS493_DIND_NAME:?}"
readonly RAW_DIR="${WS493_RAW_DIR:?}"
readonly WORK_DIR="${WS493_WRAPPER_WORK_DIR:?}"
readonly SERVICE_PID_FILE="${WS493_SERVICE_PID_FILE:?}"
readonly SERVICE_BINARY="${WS493_SERVICE_BINARY:?}"
readonly BARRIER_ENABLE="${WS493_BARRIER_ENABLE:?}"
readonly BARRIER_READY="${WS493_BARRIER_READY:?}"
readonly BARRIER_RELEASE="${WS493_BARRIER_RELEASE:?}"
readonly BARRIER_TOKEN="${WS493_BARRIER_TOKEN:?}"
readonly SANDBOX_USER="${WS493_SANDBOX_USER:?}"
readonly ART_ROOT="${WS493_ART_ROOT:?}"
readonly CACHE_ROOT="${WS493_CACHE_ROOT:?}"
readonly LOCK_FILE="${WORK_DIR}/evidence.lock"

[[ "${REAL_DOCKER}" == /* && "${RAW_DIR}" == /* && "${WORK_DIR}" == /* ]] || exit 64
[[ "${ART_ROOT}" == /* && "${CACHE_ROOT}" == /* ]] || exit 64
[[ "${DIND_NAME}" =~ ^ws-pilot00-[a-z0-9-]+-dind$ ]] || exit 64
umask 077

append_json() {
  local destination="$1"
  shift
  (
    flock -x 9
    python3 - "${destination}" "$@" <<'PY'
import json
import os
import sys

path = sys.argv[1]
value = {"argv": sys.argv[2:]}
with open(path, "a", encoding="utf-8") as stream:
    stream.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
  ) 9>>"${LOCK_FILE}"
}

append_result() {
  local status="$1"
  shift
  (
    flock -x 9
    python3 - "${RAW_DIR}/command-results.ndjson" "${status}" "$@" <<'PY'
import json
import os
import sys

value = {"status": int(sys.argv[2]), "argv": sys.argv[3:]}
with open(sys.argv[1], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
  ) 9>>"${LOCK_FILE}"
}

append_json "${RAW_DIR}/argv.ndjson" "$@" || exit 70
"${REAL_DOCKER}" exec "${DIND_NAME}" docker "$@"
status=$?
append_result "${status}" "$@" || exit 70

if [[ "${status}" -eq 0 && "${1:-}" == create ]]; then
  name=
  previous=
  for argument in "$@"; do
    if [[ "${previous}" == --name ]]; then
      name="${argument}"
      break
    fi
    previous="${argument}"
  done
  if [[ -n "${name}" ]]; then
    inspect_file="$(mktemp "${WORK_DIR}/inspect.XXXXXX")" || exit 70
    trap 'rm -f "${inspect_file}"' EXIT
    if ! "${REAL_DOCKER}" exec "${DIND_NAME}" docker container inspect "${name}" >"${inspect_file}"; then
      exit 70
    fi
    launch_kind="$(python3 - "${inspect_file}" "${RAW_DIR}/launches.ndjson" \
      "${SANDBOX_USER}" "${ART_ROOT}" "${CACHE_ROOT}" <<'PY'
import json
import os
from pathlib import Path
import re
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    values = json.load(stream)
if not isinstance(values, list) or len(values) != 1:
    raise SystemExit(70)
item = values[0]
labels = item.get("Config", {}).get("Labels") or {}
terminal_owned = labels.get("workstream.owner") == "terminal-benchmark-checker-service-v1"
checker_owned = labels.get("workstream.external-checker") == "true"
if not terminal_owned and not checker_owned:
    print("unowned")
    raise SystemExit(0)
name = str(item.get("Name", "")).removeprefix("/")
if terminal_owned:
    kind = labels.get("workstream.resource-kind")
    attempt = labels.get("workstream.attempt")
    expected = {
        "builder": f"ws-terminal-builder-{attempt}",
        "candidate": f"ws-terminal-candidate-{attempt}",
    }
    if kind == "reference":
        valid_name = any(name == f"ws-terminal-reference-{attempt}-{index}" for index in range(3))
    else:
        valid_name = expected.get(kind) == name
else:
    kind = "checker"
    attempt = labels.get("workstream.external-checker-attempt")
    valid_name = bool(re.fullmatch(r"ws-checker-[0-9a-f]{1,32}", name)) and attempt == name.removeprefix("ws-checker-")
host = item.get("HostConfig", {})
config = item.get("Config", {})
mounts = item.get("Mounts", [])
destinations = sorted(mount.get("Destination") for mount in mounts)
read_write = {mount.get("Destination"): mount.get("RW") for mount in mounts}
sources = {mount.get("Destination"): mount.get("Source") for mount in mounts}
security = set(host.get("SecurityOpt") or [])

def canonical(path: Path) -> bool:
    try:
        return path.is_absolute() and path.resolve(strict=True) == path
    except OSError:
        return False

art_root = Path(sys.argv[4])
cache_root = Path(sys.argv[5])
source_paths = {destination: Path(str(source)) for destination, source in sources.items()}
source_identity = {}
source_valid = (
    canonical(art_root)
    and canonical(cache_root)
    and len(mounts) == len(destinations) == len(read_write) == len(sources)
    and all(mount.get("Type") == "bind" for mount in mounts)
    and all(canonical(path) for path in source_paths.values())
)

if kind == "checker" and source_valid:
    source = source_paths.get("/work/input")
    try:
        relative = source.relative_to(art_root) if source is not None else None
    except ValueError:
        relative = None
    source_valid = (
        relative is not None
        and len(relative.parts) == 3
        and relative.parts[0] == "workspaces"
        and re.fullmatch(r"extract_[0-9a-f]{32}", relative.parts[1]) is not None
        and relative.parts[2] == "workspace"
    )
    source_identity = {"/work/input": "art_workspace"}
elif terminal_owned and source_valid:
    grant_id = labels.get("workstream.grant-id")
    source_valid = (
        isinstance(grant_id, str)
        and re.fullmatch(r"extract_[0-9a-f]{32}", grant_id) is not None
    )
    grant_root = art_root / "workspaces" / str(grant_id)
    expected_sources = {
        "builder": {
            "/cache": cache_root,
            "/out/candidate.tar": grant_root / "runtime" / "candidate.tar",
            "/project": grant_root / "runtime" / "build-context",
        },
        "candidate": {"/tests": grant_root / "workspace" / "tests"},
        "reference": {
            "/tests": grant_root / "workspace" / "tests",
            "/workspace/program.py": grant_root / "workspace" / "solution" / "program.py",
        },
    }
    identities = {
        "builder": {
            "/cache": "sealed_cache",
            "/out/candidate.tar": "art_runtime_candidate_tar",
            "/project": "art_runtime_build_context",
        },
        "candidate": {"/tests": "art_workspace_tests"},
        "reference": {
            "/tests": "art_workspace_tests",
            "/workspace/program.py": "art_workspace_reference_solution",
        },
    }
    source_valid = source_valid and source_paths == expected_sources.get(kind)
    source_identity = identities.get(kind, {})
else:
    source_valid = False

common = (
    valid_name
    and source_valid
    and host.get("Runtime") == "runsc"
    and host.get("NetworkMode") == "none"
    and host.get("CapDrop") == ["ALL"]
    and bool({"no-new-privileges", "no-new-privileges:true"} & security)
    and not any(destination in {"/var/run/docker.sock", "/run/docker.sock"} for destination in destinations)
    and not ({"/var/run/docker.sock", "/run/docker.sock"} & set(sources.values()))
)
if kind == "builder":
    valid = (
        common
        and config.get("User") == "0:0"
        and sorted(host.get("CapAdd") or []) == ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SYS_CHROOT"]
        and destinations == ["/cache", "/out/candidate.tar", "/project"]
        and read_write == {"/cache": False, "/out/candidate.tar": True, "/project": False}
        and host.get("ReadonlyRootfs") is False
        and host.get("PidsLimit") == 128
        and host.get("Memory") == 536870912
        and host.get("NanoCpus") == 1000000000
        and host.get("StorageOpt") == {"size": "402653184"}
    )
elif kind in {"candidate", "reference"}:
    expected_mounts = ["/tests"] if kind == "candidate" else ["/tests", "/workspace/program.py"]
    valid = (
        common
        and config.get("User") == "65532:65532"
        and not (host.get("CapAdd") or [])
        and destinations == expected_mounts
        and all(read_write[destination] is False for destination in expected_mounts)
        and host.get("ReadonlyRootfs") is True
        and host.get("PidsLimit") == 32
        and host.get("Memory") == 536870912
        and host.get("NanoCpus") == 1000000000
        and "/tmp" in (host.get("Tmpfs") or {})
    )
elif kind == "checker":
    valid = (
        common
        and config.get("User") == sys.argv[3]
        and not (host.get("CapAdd") or [])
        and destinations == ["/work/input"]
        and read_write == {"/work/input": False}
        and host.get("ReadonlyRootfs") is True
        and host.get("PidsLimit") == 32
        and host.get("Memory") == 536870912
        and host.get("NanoCpus") == 1000000000
        and "/tmp" in (host.get("Tmpfs") or {})
    )
else:
    raise SystemExit(70)
if not valid:
    raise SystemExit(70)
record = {
    "attempt": attempt,
    "cap_add": sorted(host.get("CapAdd") or []),
    "container_id": item.get("Id"),
    "kind": kind,
    "mount_destinations": destinations,
    "mount_source_identities": source_identity,
    "name": name,
    "network": host.get("NetworkMode"),
    "read_only_root": host.get("ReadonlyRootfs"),
    "runtime": host.get("Runtime"),
    "user": config.get("User"),
}
with open(sys.argv[2], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
print(kind)
PY
)" || exit $?
    if [[ "${launch_kind}" == builder && -f "${BARRIER_ENABLE}" && ! -L "${BARRIER_ENABLE}" ]]; then
      service_pid="$(cat "${SERVICE_PID_FILE}")" || exit 70
      [[ "${service_pid}" =~ ^[1-9][0-9]*$ ]] || exit 70
      [[ "$(readlink -f "/proc/${service_pid}/exe")" == "$(readlink -f "${SERVICE_BINARY}")" ]] || exit 70
      marker_tmp="${BARRIER_READY}.tmp.$$"
      python3 - "${marker_tmp}" "${name}" "$$" "${service_pid}" "${BARRIER_TOKEN}" <<'PY'
import json
import os
import sys

value = {
    "builder_name": sys.argv[2],
    "wrapper_pid": int(sys.argv[3]),
    "service_pid": int(sys.argv[4]),
    "token": sys.argv[5],
}
with open(sys.argv[1], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
      [[ ! -e "${BARRIER_READY}" && ! -L "${BARRIER_READY}" ]] || exit 70
      mv -T "${marker_tmp}" "${BARRIER_READY}"
      released=0
      for _ in $(seq 1 600); do
        if [[ -f "${BARRIER_RELEASE}" && ! -L "${BARRIER_RELEASE}" ]] \
          && [[ "$(cat "${BARRIER_RELEASE}")" == "${BARRIER_TOKEN}" ]]; then
          rm -f "${BARRIER_RELEASE}"
          released=1
          break
        fi
        sleep 0.2
      done
      [[ "${released}" -eq 1 ]] || exit 70
    fi
  fi
fi

exit "${status}"
