#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly STATE_ROOT="${WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT:?set the prepared PILOT-00 state root}"
readonly INNER_STATE_ROOT="/workstream-state"
readonly CONTAINER="${WORKSTREAM_TRIAL_QUALIFICATION_CONTAINER:?set the owned qualification container}"
readonly RUN_ID="${WORKSTREAM_TRIAL_QUALIFICATION_RUN_ID:?set the prepared PILOT-00 run ID}"
readonly PLATFORM_IDENTITY="${WORKSTREAM_TRIAL_PLATFORM_IDENTITY_SHA256:?set the exact trusted Docker/runsc platform identity digest}"
readonly EXPECTED_HEAD="${WORKSTREAM_TRIAL_QUALIFICATION_EXPECTED_HEAD:?set the exact source commit}"
readonly EXPECTED_TREE="${WORKSTREAM_TRIAL_QUALIFICATION_EXPECTED_TREE:?set the exact source tree}"
readonly INVOCATION_NONCE="${WORKSTREAM_TRIAL_QUALIFICATION_INVOCATION_NONCE:?set a unique qualification nonce}"
readonly EVIDENCE_PREFIX="${WORKSTREAM_TRIAL_QUALIFICATION_EVIDENCE_PREFIX:?set an absolute fresh evidence prefix}"
readonly RESULT_LOG="${EVIDENCE_PREFIX}.log"
readonly EXIT_SIDECAR="${EVIDENCE_PREFIX}.exit"
readonly RESULT_JSON="${EVIDENCE_PREFIX}.json"
readonly RAW_RESULT="${STATE_ROOT}/results/trial-docker-qualification.json"
readonly LEGACY_RESULT_LOG="${STATE_ROOT}/results/trial-docker-qualification.log"
readonly LEGACY_CACHE_LOG="${STATE_ROOT}/results/trial-cache-recheck.log"

BUILD_MESSAGES=""
LAUNCHER_MESSAGES=""
LAUNCHER_PROGRAM_HEADERS=""
LAUNCHER_DYNAMIC=""
INNER_READY=0
CLEANUP_COMPLETE=0
SUMMARY_PUBLICATION_STARTED=0

source_identity_matches() {
  local actual_head actual_tree worktree_status
  actual_head="$(git -C "${REPOSITORY_ROOT}" rev-parse HEAD)" || return 1
  actual_tree="$(git -C "${REPOSITORY_ROOT}" rev-parse 'HEAD^{tree}')" || return 1
  worktree_status="$(git -C "${REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all)" || return 1
  if [[ "${actual_head}" != "${EXPECTED_HEAD}" ]]; then
    echo "qualification source commit differs from the expected commit" >&2
    return 1
  fi
  if [[ "${actual_tree}" != "${EXPECTED_TREE}" ]]; then
    echo "qualification source tree differs from the expected tree" >&2
    return 1
  fi
  if [[ -n "${worktree_status}" ]]; then
    echo "qualification source worktree is not clean" >&2
    return 1
  fi
}

cleanup_owned_resources() {
  [[ "${INNER_READY}" == 1 ]] || return 0
  timeout --kill-after=5s 30s docker exec "${CONTAINER}" sh -ceu '
    run_root="$1"
    ids="$(docker container ls -aq --filter label=workstream.trial.deployment-owner=qualification)"
    for id in ${ids}; do
      attempt="$(docker inspect --format "{{index .Config.Labels \"workstream.trial.attempt-id\"}}" "${id}")"
      request="$(docker inspect --format "{{index .Config.Labels \"workstream.trial.request-digest\"}}" "${id}")"
      owner="$(docker inspect --format "{{index .Config.Labels \"workstream.trial.owner-id\"}}" "${id}")"
      case "${attempt}|${request}|${owner}" in
        "018f6f49-66b8-7d2a-bf4d-0e2eeaa00026|sha256:9999999999999999999999999999999999999999999999999999999999999999|trial_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"|\
        "018f6f49-66b8-7d2a-bf4d-0e2eeaa00027|sha256:8888888888888888888888888888888888888888888888888888888888888888|trial_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb") ;;
        *) echo "refusing to clean a trial container with different custody" >&2; exit 1 ;;
      esac
      docker container rm --force "${id}" >/dev/null
    done
    if docker image inspect workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa >/dev/null 2>&1; then
      docker image rm workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa >/dev/null
    fi
    rm -rf -- "${run_root}"
    test -z "$(docker container ls -aq --filter label=workstream.trial.deployment-owner=qualification)"
    test -z "$(docker images -q workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)"
    test ! -e "${run_root}"
  ' sh "${INNER_STATE_ROOT}/trial-scratch/engine-qualification"
}

finish() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "${CLEANUP_COMPLETE}" != 1 ]]; then
    if ! cleanup_owned_resources; then
      echo "qualification cleanup failed" >&2
      status=1
    fi
  fi
  if ! source_identity_matches; then
    status=1
  fi
  if [[ "${INNER_READY}" == 1 ]]; then
    if ! timeout --kill-after=5s 30s docker exec "${CONTAINER}" \
      rm -f -- "${INNER_STATE_ROOT}/results/trial-docker-qualification.json"; then
      echo "qualification could not remove its transient inner result" >&2
      status=1
    fi
  elif [[ -e "${RAW_RESULT}" || -L "${RAW_RESULT}" ]]; then
    echo "qualification found an inner result without owning the runtime" >&2
    status=1
  fi
  if ! python3 - "${EXIT_SIDECAR}" "${status}" <<'PY'
import os
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0))
try:
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        raise SystemExit("qualification exit sidecar is not regular")
    os.write(descriptor, (sys.argv[2] + "\n").encode())
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  then
    echo "qualification could not write its exit sidecar" >&2
    status=1
  fi
  if [[ "${SUMMARY_PUBLICATION_STARTED}" == 1 && "${status}" != 0 ]]; then
    if ! python3 - "${RESULT_JSON}" <<'PY'
import os
import sys

try:
    os.unlink(sys.argv[1])
except FileNotFoundError:
    pass
PY
    then
      echo "qualification could not retract its failed summary" >&2
      status=1
    fi
  fi
  for temporary in "${BUILD_MESSAGES}" "${LAUNCHER_MESSAGES}" "${LAUNCHER_PROGRAM_HEADERS}" "${LAUNCHER_DYNAMIC}"; do
    if [[ -n "${temporary}" ]]; then
      rm -f -- "${temporary}"
    fi
  done
  exec 1>&3 2>&4
  cat -- "${RESULT_LOG}"
  if [[ "${status}" != 0 ]]; then
    echo "qualification failed; retained log=${RESULT_LOG} exit=${EXIT_SIDECAR}" >&2
  fi
  exit "${status}"
}

[[ "${STATE_ROOT}" == /* ]]
[[ "${RUN_ID}" =~ ^[a-z0-9][a-z0-9-]{0,30}$ ]]
[[ "${PLATFORM_IDENTITY}" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "${EXPECTED_HEAD}" =~ ^[0-9a-f]{40}$ ]]
[[ "${EXPECTED_TREE}" =~ ^[0-9a-f]{40}$ ]]
[[ "${INVOCATION_NONCE}" =~ ^[a-z0-9][a-z0-9-]{0,63}$ ]]
[[ "${EVIDENCE_PREFIX}" == /* ]]
python3 - "${RESULT_LOG}" "${EXIT_SIDECAR}" "${RESULT_JSON}" <<'PY'
import os
from pathlib import Path
import sys

log_path, exit_path, result_path = map(Path, sys.argv[1:])
parents = {path.parent for path in (log_path, exit_path, result_path)}
if len(parents) != 1:
    raise SystemExit("qualification evidence files must share one directory")
parent = parents.pop()
if parent.resolve(strict=True) != parent:
    raise SystemExit("qualification evidence directory must be canonical")
parent_stat = parent.stat()
if parent_stat.st_uid != os.geteuid() or parent_stat.st_mode & 0o077:
    raise SystemExit("qualification evidence directory must be private and caller-owned")
if any(os.path.lexists(path) for path in (log_path, exit_path, result_path)):
    raise SystemExit("qualification evidence prefix already exists")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
created = []
try:
    for path in (log_path, exit_path):
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)
        created.append(path)
except BaseException:
    for path in created:
        path.unlink(missing_ok=True)
    raise
PY
exec 3>&1 4>&2
exec >>"${RESULT_LOG}" 2>&1
trap 'exit 130' INT
trap 'exit 143' TERM
trap finish EXIT
source_identity_matches
for retained in "${RAW_RESULT}" "${LEGACY_RESULT_LOG}" "${LEGACY_CACHE_LOG}"; do
  if [[ -e "${retained}" || -L "${retained}" ]]; then
    echo "qualification retained result path already exists: ${retained}" >&2
    exit 1
  fi
done

BUILD_MESSAGES="$(mktemp /tmp/workstream-trial-build.XXXXXX.jsonl)"
LAUNCHER_MESSAGES="$(mktemp /tmp/workstream-trial-launcher-build.XXXXXX.jsonl)"
LAUNCHER_PROGRAM_HEADERS="$(mktemp /tmp/workstream-trial-launcher.XXXXXX.phdr)"
LAUNCHER_DYNAMIC="$(mktemp /tmp/workstream-trial-launcher.XXXXXX.dynamic)"
python3 - "${CONTAINER}" "${RUN_ID}" "${STATE_ROOT}" "${INNER_STATE_ROOT}" <<'PY'
import json
import subprocess
import sys

value = json.loads(subprocess.check_output(["docker", "inspect", sys.argv[1]], text=True))[0]
if value["Config"]["Labels"].get("org.workstream.pilot00.run") != sys.argv[2]:
    raise SystemExit("qualification container has the wrong run label")
if not value["State"]["Running"]:
    raise SystemExit("qualification container is not running")
sources = [mount["Source"] for mount in value["Mounts"] if mount["Destination"] == sys.argv[4]]
if sources != [sys.argv[3]]:
    raise SystemExit("qualification container has the wrong state mount")
PY
docker exec "${CONTAINER}" chmod 0711 "${INNER_STATE_ROOT}"

docker exec "${CONTAINER}" sh -ceu '
  test -z "$(docker container ls -aq --filter label=workstream.trial.deployment-owner=qualification)"
  test -z "$(docker images -q workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)"
  rm -rf -- /workstream-state/trial-scratch/engine-qualification
'
INNER_READY=1

python3 - "${STATE_ROOT}/prepared-assets.json" "${RUN_ID}" "${STATE_ROOT}" \
  "${REPOSITORY_ROOT}/experiments/pilot00_gvisor_offline/tool-inputs.env" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    value = json.load(stream)
declared = {}
with open(sys.argv[4], encoding="utf-8") as stream:
    for line in stream:
        key, separator, item = line.strip().partition("=")
        if separator:
            declared[key] = item
expected = {
    "run_id": sys.argv[2],
    "shared_state_path": sys.argv[3],
    "docker_state_path": f"{sys.argv[3]}/dind-state",
    "scratch_path": f"{sys.argv[3]}/trial-scratch",
    "cache_path": f"{sys.argv[3]}/cache/content",
    "cache_manifest_path": f"{sys.argv[3]}/cache/cache.sha256",
    "runtime_configuration_path": f"{sys.argv[3]}/daemon.json",
    "protected_role_path": f"{sys.argv[3]}/protected-role",
    "cache_manifest_sha256": "sha256:0d7c48edceae685051d2f60497b0df7f55a0f3f8dd6d29c5e82b9c0cd75a40e1",
    "runtime_configuration_sha256": "sha256:46429fe1ec5b135d7214c1090c28c75a3175169307ae2981c502015152c3d330",
    "runsc_binary_sha256": "sha256:88a87d5d6d06160d4c144f51f95ec6dd6fe0fc6b02697eb877876683c5b57a91",
    "runsc_version": f"runsc version {declared['GVISOR_VERSION']}\nspec: 1.2.1",
    "builder_image_id": declared["KANIKO_IMAGE_ID"],
    "builder_manifest": declared["KANIKO_IMAGE"],
    "base_manifest": declared["BASE_PLATFORM_IMAGE"],
}
for key, expected_value in expected.items():
    if value.get(key) != expected_value:
        raise SystemExit(f"prepared qualification identity differs: {key}")
PY

docker exec "${CONTAINER}" sh -ceu '
  test "$(sha256sum /opt/gvisor/runsc | cut -d" " -f1)" = 88a87d5d6d06160d4c144f51f95ec6dd6fe0fc6b02697eb877876683c5b57a91
  test "$(sha256sum /etc/docker/pilot-daemon.json | cut -d" " -f1)" = 46429fe1ec5b135d7214c1090c28c75a3175169307ae2981c502015152c3d330
  test "$(docker image inspect --format "{{.Id}}" sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3)" = sha256:b8c743a43e82f0cef9956ea09eae79c2d56b51d359b65a736c171624a9fc95e3
'

(
  cd "${REPOSITORY_ROOT}"
  CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 RUST_MIN_STACK=67108864 cargo build \
    --manifest-path external_checkers/workstream-checker-service/Cargo.toml \
    --bin qualify-trial-docker --features trial-docker-qualification \
    --message-format=json-render-diagnostics >"${BUILD_MESSAGES}"
)
readonly QUALIFICATION_BINARY="$(python3 - "${BUILD_MESSAGES}" <<'PY'
import json
import sys

executables = []
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        value = json.loads(line)
        if (
            value.get("reason") == "compiler-artifact"
            and value["target"]["name"] == "qualify-trial-docker"
            and "bin" in value["target"]["kind"]
            and value.get("executable")
        ):
            executables.append(value["executable"])
if len(executables) != 1:
    raise SystemExit("cargo did not report exactly one qualification executable")
print(executables[0])
PY
)"
[[ -x "${QUALIFICATION_BINARY}" ]]

(
  cd "${REPOSITORY_ROOT}"
  CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo rustc \
    --manifest-path external_checkers/workstream-checker-service/Cargo.toml \
    --bin workstream-trial-launcher --message-format=json-render-diagnostics \
    -- -C target-feature=+crt-static >"${LAUNCHER_MESSAGES}"
)
readonly LAUNCHER_BINARY="$(python3 - "${LAUNCHER_MESSAGES}" <<'PY'
import json
import sys

executables = []
with open(sys.argv[1], encoding="utf-8") as stream:
    for line in stream:
        value = json.loads(line)
        if (
            value.get("reason") == "compiler-artifact"
            and value["target"]["name"] == "workstream-trial-launcher"
            and "bin" in value["target"]["kind"]
            and value.get("executable")
        ):
            executables.append(value["executable"])
if len(executables) != 1:
    raise SystemExit("cargo did not report exactly one launcher executable")
print(executables[0])
PY
)"
[[ -x "${LAUNCHER_BINARY}" ]]
readelf -l "${LAUNCHER_BINARY}" >"${LAUNCHER_PROGRAM_HEADERS}"
readelf -d "${LAUNCHER_BINARY}" >"${LAUNCHER_DYNAMIC}"
! grep -q INTERP "${LAUNCHER_PROGRAM_HEADERS}"
! grep -q NEEDED "${LAUNCHER_DYNAMIC}"
readonly LAUNCHER_SHA256="sha256:$(sha256sum "${LAUNCHER_BINARY}" | cut -d' ' -f1)"

docker exec -e QUALIFICATION_ROOT="${INNER_STATE_ROOT}" "${CONTAINER}" sh -ceu '
  chmod 0711 "${QUALIFICATION_ROOT}"
  chown 65532:65532 "${QUALIFICATION_ROOT}/trial-scratch"
  chmod 0700 "${QUALIFICATION_ROOT}/trial-scratch"
  mkdir -p "${QUALIFICATION_ROOT}/qualification-bin" "${QUALIFICATION_ROOT}/results"
  chown 65532:65532 "${QUALIFICATION_ROOT}/results"
  chmod 0755 "${QUALIFICATION_ROOT}/qualification-bin" "${QUALIFICATION_ROOT}/results"
  chgrp 65532 /var/run/docker.sock
  chmod 0660 /var/run/docker.sock
'
docker cp "${QUALIFICATION_BINARY}" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/qualify-trial-docker"
docker cp "${LAUNCHER_BINARY}" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/workstream-trial-launcher"
docker cp "$(readlink -f /lib64/ld-linux-x86-64.so.2)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/ld-linux-x86-64.so.2"
docker cp "$(readlink -f /lib/x86_64-linux-gnu/libgcc_s.so.1)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/libgcc_s.so.1"
docker cp "$(readlink -f /lib/x86_64-linux-gnu/libm.so.6)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/libm.so.6"
docker cp "$(readlink -f /lib/x86_64-linux-gnu/libc.so.6)" "${CONTAINER}:${INNER_STATE_ROOT}/qualification-bin/libc.so.6"
docker exec "${CONTAINER}" chmod 0555 \
  "${INNER_STATE_ROOT}/qualification-bin/qualify-trial-docker" \
  "${INNER_STATE_ROOT}/qualification-bin/workstream-trial-launcher" \
  "${INNER_STATE_ROOT}/qualification-bin/ld-linux-x86-64.so.2" \
  "${INNER_STATE_ROOT}/qualification-bin/libgcc_s.so.1" \
  "${INNER_STATE_ROOT}/qualification-bin/libm.so.6" \
  "${INNER_STATE_ROOT}/qualification-bin/libc.so.6"

docker exec --user 65532:65532 \
  -e WORKSTREAM_TRIAL_QUALIFICATION_ROOT="${INNER_STATE_ROOT}" \
  -e WORKSTREAM_TRIAL_PLATFORM_IDENTITY_SHA256="${PLATFORM_IDENTITY}" \
  -e WORKSTREAM_TRIAL_LAUNCHER_PATH="${INNER_STATE_ROOT}/qualification-bin/workstream-trial-launcher" \
  -e WORKSTREAM_TRIAL_LAUNCHER_SHA256="${LAUNCHER_SHA256}" \
  "${CONTAINER}" \
  "${INNER_STATE_ROOT}/qualification-bin/ld-linux-x86-64.so.2" \
  --library-path "${INNER_STATE_ROOT}/qualification-bin" \
  "${INNER_STATE_ROOT}/qualification-bin/qualify-trial-docker" \
  2>&1

docker exec -e QUALIFICATION_ROOT="${INNER_STATE_ROOT}" "${CONTAINER}" sh -ceu '
  cd "${QUALIFICATION_ROOT}/cache/content"
  sha256sum -c ../cache.sha256
  test -z "$(docker ps -aq --filter label=workstream.trial=true)"
  test -z "$(docker images -q workstream-trial:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)"
  test -z "$(find "${QUALIFICATION_ROOT}/trial-scratch/engine-qualification/runtime" -name ".trial-owner-*.json" -print -quit)"
  test -s "${QUALIFICATION_ROOT}/results/trial-docker-qualification.json"
'
cleanup_owned_resources
CLEANUP_COMPLETE=1
source_identity_matches

SUMMARY_PUBLICATION_STARTED=1
python3 - \
  "${RESULT_JSON}" \
  "${INVOCATION_NONCE}" \
  "${EXPECTED_HEAD}" \
  "${EXPECTED_TREE}" \
  "${PLATFORM_IDENTITY}" \
  "${LAUNCHER_SHA256}" \
  "${STATE_ROOT}/prepared-assets.json" \
  "${RAW_RESULT}" \
  "${RESULT_LOG}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys

(
    result_path,
    nonce,
    head,
    tree,
    platform_identity,
    launcher_sha256,
    prepared_path,
    raw_path,
    log_path,
) = sys.argv[1:]

def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

prepared_bytes = Path(prepared_path).read_bytes()
raw_bytes = Path(raw_path).read_bytes()
log_bytes = Path(log_path).read_bytes()
prepared = json.loads(prepared_bytes)
qualification = json.loads(raw_bytes)
identity_keys = (
    "run_id",
    "cache_manifest_sha256",
    "runtime_configuration_sha256",
    "runsc_binary_sha256",
    "runsc_version",
    "builder_image_id",
    "builder_manifest",
    "base_manifest",
)
identities = {key: prepared[key] for key in identity_keys}
summary = {
    "schema_version": "workstream.trial_docker_qualification_evidence.v1",
    "invocation_nonce": nonce,
    "source": {"head": head, "tree": tree},
    "platform_identity_sha256": platform_identity,
    "trusted_launcher_sha256": launcher_sha256,
    "prepared_assets_sha256": digest(prepared_bytes),
    "prepared_identities": identities,
    "qualification_result_sha256": digest(raw_bytes),
    "qualification_log_sha256": digest(log_bytes),
    "cleanup_confirmed": True,
    "qualification": qualification,
}
encoded = (json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n").encode()
target = Path(result_path)
temporary = target.with_name(target.name + f".{nonce}.tmp")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(temporary, flags, 0o600)
try:
    os.write(descriptor, encoded)
    os.fsync(descriptor)
finally:
    os.close(descriptor)
try:
    os.link(temporary, target, follow_symlinks=False)
finally:
    os.unlink(temporary)
directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
