#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=inputs.env
source "${SCRIPT_DIR}/inputs.env"

readonly ACTION="${1:-}"
readonly EXPECTED_HEAD="${WS493_EXPECTED_HEAD:?}"
readonly RUN_ID="${WS493_RUN_ID:?}"
readonly RUNNER_TEMP_ROOT="${RUNNER_TEMP:?}"
[[ "${EXPECTED_HEAD}" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid proof head" >&2; exit 64; }
[[ "${RUN_ID}" =~ ^[0-9]+-[0-9]+$ ]] || { echo "invalid proof run ID" >&2; exit 64; }
[[ "${RUNNER_TEMP_ROOT}" == /* ]] || { echo "RUNNER_TEMP must be absolute" >&2; exit 64; }

readonly OWNER_UID=65532
readonly DOCKER_GID="$(stat -c %g /var/run/docker.sock)"
readonly PROOF_PREFIX="ws493-${RUN_ID}"
readonly PILOT_RUN_ID="pc-${RUN_ID}"
readonly DIND_NAME="ws-pilot00-${PILOT_RUN_ID}-dind"
readonly OUTER_OWNER_LABEL="org.workstream.pilot00.run=${PILOT_RUN_ID}"
readonly RAW_DEVICE_FILE="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}.xfs"
readonly LOOP_RECORD="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}.loop"
readonly MOUNT_ROOT="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}-mount"
readonly STATE_ROOT="${MOUNT_ROOT}/state"
readonly DIND_STATE="${STATE_ROOT}/dind"
readonly CACHE_ROOT="${STATE_ROOT}/cache/content"
readonly RAW_DIR="${STATE_ROOT}/evidence/raw"
readonly ART_ROOT="${STATE_ROOT}/art"
readonly SERVICE_ROOT="${STATE_ROOT}/service"
readonly SOCKET_PATH="${SERVICE_ROOT}/checker.sock"
readonly WRAPPER_WORK="${STATE_ROOT}/wrapper"
readonly SERVICE_BINARY="${STATE_ROOT}/bin/workstream-checker-service"
readonly SERVICE_CONFIG="${SERVICE_ROOT}/config.json"
readonly SERVICE_PID_FILE="${WRAPPER_WORK}/service.pid"
readonly BARRIER_ENABLE="${WRAPPER_WORK}/barrier.enable"
readonly BARRIER_READY="${WRAPPER_WORK}/barrier.ready.json"
readonly BARRIER_RELEASE="${WRAPPER_WORK}/barrier.release"
readonly BARRIER_TOKEN="${EXPECTED_HEAD}-${RUN_ID}"
readonly STAGING_DIR="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}-staging"
readonly CLEANUP_RECEIPT="${RUNNER_TEMP_ROOT}/${PROOF_PREFIX}-cleanup-receipt.json"
readonly BACKEND_PYTHON="${REPOSITORY_ROOT}/backend/.venv/bin/python"
readonly REAL_DOCKER="$(readlink -f "$(command -v docker)")"
readonly DOCKER_WRAPPER="$(readlink -f "${SCRIPT_DIR}/docker-wrapper.sh")"
readonly PILOT_PROBE="${REPOSITORY_ROOT}/experiments/pilot00_gvisor_offline/probe.sh"
readonly PACKAGE="${REPOSITORY_ROOT}/pilots/terminal_benchmark/packages/ledger-reconcile"

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 69; }
}

inner_docker() {
  "${REAL_DOCKER}" exec "${DIND_NAME}" docker "$@"
}

pilot() {
  PILOT00_RUN_ID="${PILOT_RUN_ID}" \
  PILOT00_STATE_DIR="${STATE_ROOT}" \
  PILOT00_DIND_STATE_DIR="${DIND_STATE}" \
  PILOT00_SHARED_STATE_PATH="${STATE_ROOT}" \
  PILOT00_RUNTIME_KEY=runsc \
  PILOT00_HARNESS_ONLY=1 \
    "${PILOT_PROBE}" "$@"
}

write_owned_json() {
  local destination="$1"
  shift
  python3 - "${destination}" "$@" <<'PY'
import json
import os
import sys

destination = sys.argv[1]
value = json.loads(sys.argv[2])
payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
try:
    os.write(descriptor, payload)
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${destination}"
}

assert_source_head() {
  local -a git_command=(git -c "safe.directory=${REPOSITORY_ROOT}" -C "${REPOSITORY_ROOT}")
  [[ "$("${git_command[@]}" rev-parse HEAD)" == "${EXPECTED_HEAD}" ]]
  [[ -z "$("${git_command[@]}" status --porcelain=v1)" ]]
}

preflight() {
  local available_disk available_memory cpus
  available_disk="$(df --output=avail -B1 "${RUNNER_TEMP_ROOT}" | tail -1 | tr -d ' ')"
  available_memory="$(awk '/^MemAvailable:/ {print $2 * 1024}' /proc/meminfo)"
  cpus="$(nproc)"
  (( available_disk >= 10 * 1024 * 1024 * 1024 )) || { echo "less than 10 GiB available" >&2; exit 69; }
  (( available_memory >= 6 * 1024 * 1024 * 1024 )) || { echo "less than 6 GiB memory available" >&2; exit 69; }
  (( cpus >= 2 )) || { echo "fewer than 2 CPUs available" >&2; exit 69; }
}

manifest_raw() {
  local reference="$1" output="$2"
  docker buildx imagetools inspect --raw "${reference}" >"${output}"
}

prepare_filesystem() {
  [[ "$(id -u)" -eq 0 ]] || { echo "proof preparation requires root" >&2; exit 77; }
  [[ ! -e "${RAW_DEVICE_FILE}" && ! -e "${LOOP_RECORD}" && ! -e "${MOUNT_ROOT}" ]]
  truncate -s 6G "${RAW_DEVICE_FILE}"
  local loop_device
  loop_device="$(losetup --find --show "${RAW_DEVICE_FILE}")"
  printf '%s\n' "${loop_device}" >"${LOOP_RECORD}"
  chmod 0600 "${LOOP_RECORD}"
  mkfs.xfs -f -n ftype=1 "${loop_device}" >/dev/null
  mkdir -m 0755 "${MOUNT_ROOT}"
  mount -o pquota "${loop_device}" "${MOUNT_ROOT}"
  [[ "$(findmnt -n -o SOURCE --target "${MOUNT_ROOT}")" == "${loop_device}" ]]
  [[ "$(findmnt -n -o FSTYPE --target "${MOUNT_ROOT}")" == xfs ]]
  findmnt -n -o OPTIONS --target "${MOUNT_ROOT}" | grep -Eq '(^|,)(pquota|prjquota)(,|$)'
  xfs_quota -x -c 'state -p' "${MOUNT_ROOT}" | grep -F 'Project quota state' >/dev/null
}

prepare_images() {
  local work="${STATE_ROOT}/work"
  install -d -m 0700 "${work}"
  manifest_raw "${KANIKO_INDEX}" "${work}/kaniko-index.json"
  local kaniko_index_digest="${KANIKO_INDEX##*@}"
  local kaniko_child
  kaniko_child="$(python3 "${SCRIPT_DIR}/image_facts.py" select-child "${work}/kaniko-index.json" "${kaniko_index_digest}")"
  local kaniko_repository="${KANIKO_INDEX%@*}"
  local kaniko_reference="${kaniko_repository}@${kaniko_child}"
  local kaniko_transfer="ws493-kaniko:${EXPECTED_HEAD}"
  manifest_raw "${kaniko_reference}" "${work}/kaniko-manifest.json"
  python3 "${SCRIPT_DIR}/image_facts.py" manifest-fact \
    "${work}/kaniko-manifest.json" "${kaniko_child}" "${kaniko_repository}" >"${work}/upstream-builder-fact.json"
  manifest_raw "${BASE_PLATFORM_IMAGE}" "${work}/base-manifest.json"

  docker pull "${kaniko_reference}" >/dev/null
  docker pull "${BASE_PLATFORM_IMAGE}" >/dev/null
  docker pull "${REGISTRY_IMAGE}" >/dev/null
  docker pull "${CHECKER_BUILD_IMAGE}" >/dev/null
  docker pull "${CHECKER_FINAL_IMAGE}" >/dev/null
  docker build --pull=false --tag "ws493-checker:${EXPECTED_HEAD}" \
    --file "${REPOSITORY_ROOT}/external_checkers/workstream-terminal-benchmark-checker/Dockerfile" \
    "${REPOSITORY_ROOT}/external_checkers" >/dev/null

  mkdir -p "${CACHE_ROOT}"
  docker run --rm \
    --name "${PROOF_PREFIX}-cache-warmer" \
    --label "org.workstream.ws493.run=${RUN_ID}" \
    --mount "type=bind,src=${CACHE_ROOT},dst=/cache" \
    --entrypoint /kaniko/warmer \
    "${kaniko_reference}" \
    --cache-dir=/cache --image="${BASE_PLATFORM_IMAGE}"
  chown -R "${OWNER_UID}:${DOCKER_GID}" "${CACHE_ROOT}"
  find "${CACHE_ROOT}" -type d -exec chmod 0555 {} +
  find "${CACHE_ROOT}" -type f -exec chmod 0444 {} +

  docker tag "${kaniko_reference}" "${kaniko_transfer}"
  docker save "${kaniko_transfer}" | "${REAL_DOCKER}" exec -i "${DIND_NAME}" docker load >/dev/null
  docker save "${BASE_PLATFORM_IMAGE}" | "${REAL_DOCKER}" exec -i "${DIND_NAME}" docker load >/dev/null
  docker save "${REGISTRY_IMAGE}" | "${REAL_DOCKER}" exec -i "${DIND_NAME}" docker load >/dev/null
  docker save "ws493-checker:${EXPECTED_HEAD}" | "${REAL_DOCKER}" exec -i "${DIND_NAME}" docker load >/dev/null
  inner_docker image inspect "${kaniko_transfer}" >/dev/null
  inner_docker image inspect "${BASE_PLATFORM_IMAGE}" >/dev/null

  inner_docker run -d --name "${PROOF_PREFIX}-registry" \
    --label "org.workstream.ws493.run=${RUN_ID}" --network host \
    "${REGISTRY_IMAGE}" >/dev/null
  for _ in $(seq 1 60); do
    if "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO- http://127.0.0.1:5000/v2/ >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO- http://127.0.0.1:5000/v2/ >/dev/null
  local builder_repository=127.0.0.1:5000/workstream/builder
  local builder_tag="${builder_repository}:${EXPECTED_HEAD}"
  inner_docker tag "${kaniko_transfer}" "${builder_tag}"
  inner_docker push "${builder_tag}" >/dev/null
  local builder_reference builder_digest
  builder_reference="$(inner_docker image inspect "${builder_tag}" --format '{{json .RepoDigests}}' | \
    python3 -c 'import json,sys; matches=[value for value in json.load(sys.stdin) if value.startswith(sys.argv[1]+"@")]; len(matches) == 1 or sys.exit(1); print(matches[0])' "${builder_repository}")"
  builder_digest="${builder_reference##*@}"
  [[ "${builder_reference}" == "${builder_repository}@${builder_digest}" ]]
  [[ "${builder_digest}" == "${kaniko_child}" ]]
  "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO "${work}/builder-manifest.json" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "http://127.0.0.1:5000/v2/workstream/builder/manifests/${builder_digest}"
  local checker_repository=127.0.0.1:5000/workstream/checker
  local checker_tag="${checker_repository}:${EXPECTED_HEAD}"
  inner_docker tag "ws493-checker:${EXPECTED_HEAD}" "${checker_tag}"
  inner_docker push "${checker_tag}" >/dev/null
  local checker_reference checker_digest
  checker_reference="$(inner_docker image inspect "${checker_tag}" --format '{{index .RepoDigests 0}}')"
  checker_digest="${checker_reference##*@}"
  [[ "${checker_reference}" == "${checker_repository}@${checker_digest}" ]]
  "${REAL_DOCKER}" exec "${DIND_NAME}" wget -qO "${work}/checker-manifest.json" \
    --header 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    "http://127.0.0.1:5000/v2/workstream/checker/manifests/${checker_digest}"

  python3 "${SCRIPT_DIR}/image_facts.py" manifest-fact \
    "${work}/builder-manifest.json" "${builder_digest}" "${builder_repository}" >"${work}/builder-fact.json"
  python3 "${SCRIPT_DIR}/image_facts.py" manifest-fact \
    "${work}/base-manifest.json" "${BASE_PLATFORM_IMAGE##*@}" "${BASE_PLATFORM_IMAGE%@*}" >"${work}/base-fact.json"
  python3 "${SCRIPT_DIR}/image_facts.py" manifest-fact \
    "${work}/checker-manifest.json" "${checker_digest}" "${checker_repository}" >"${work}/checker-fact.json"
  python3 - "${work}" "${RAW_DIR}/image-facts.json" <<'PY'
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
value = {
    "approved_base": json.loads((root / "base-fact.json").read_text()),
    "builder": json.loads((root / "builder-fact.json").read_text()),
    "checker": json.loads((root / "checker-fact.json").read_text()),
}
with open(sys.argv[2], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/image-facts.json"
  chmod 0600 "${RAW_DIR}/image-facts.json"
}

quota_and_boundaries() {
  local base="${BASE_PLATFORM_IMAGE}" work="${STATE_ROOT}/work"
  local below="${PROOF_PREFIX}-quota-below" above="${PROOF_PREFIX}-quota-above"
  inner_docker create --pull=never --name "${below}" --runtime runsc --network none \
    --storage-opt size=402653184 "${base}" python -c \
    'import os; f=open("/quota.bin","wb",buffering=0); [f.write(b"x"*(1024*1024)) for _ in range(320)]; os.fsync(f.fileno())' >/dev/null
  inner_docker start --attach "${below}" >"${work}/quota-below.log" 2>&1
  [[ "$(inner_docker inspect "${below}" --format '{{.State.ExitCode}}')" == 0 ]]
  inner_docker rm -v "${below}" >/dev/null

  inner_docker create --pull=never --name "${above}" --runtime runsc --network none \
    --storage-opt size=402653184 "${base}" python -c \
    'import os; f=open("/quota.bin","wb",buffering=0); [f.write(b"x"*(1024*1024)) for _ in range(400)]; os.fsync(f.fileno())' >/dev/null
  set +e
  inner_docker start --attach "${above}" >"${work}/quota-above.log" 2>&1
  local above_status=$?
  set -e
  [[ "${above_status}" -ne 0 ]]
  [[ "$(inner_docker inspect "${above}" --format '{{.State.ExitCode}}')" != 0 ]]
  inner_docker rm -v "${above}" >/dev/null

  inner_docker info --format '{{json .}}' >"${work}/docker-info.json"
  xfs_quota -x -c 'state -p' "${MOUNT_ROOT}" >"${work}/xfs-quota.txt"
  python3 - "${work}/docker-info.json" "${work}/xfs-quota.txt" "${RAW_DIR}/quota.json" <<'PY'
import json
import os
import sys

info = json.load(open(sys.argv[1], encoding="utf-8"))
driver = dict(info.get("DriverStatus") or [])
quota = open(sys.argv[2], encoding="utf-8").read().lower()
value = {
    "backing_filesystem": str(driver.get("Backing Filesystem", "")).lower(),
    "d_type": str(driver.get("Supports d_type", "")).lower() == "true",
    "inner_driver": info.get("Driver"),
    "project_quota": "accounting: on" in quota and "enforcement: on" in quota,
    "storage_opt_bytes": 402653184,
    "below_limit_bytes": 335544320,
    "below_limit_succeeded": True,
    "above_limit_bytes": 419430400,
    "above_limit_failed": True,
}

if value != {
    "backing_filesystem": "xfs", "d_type": True, "inner_driver": "overlay2",
    "project_quota": True, "storage_opt_bytes": 402653184,
    "below_limit_bytes": 335544320, "below_limit_succeeded": True,
    "above_limit_bytes": 419430400, "above_limit_failed": True,
}:
    raise SystemExit("quota facts differ")
with open(sys.argv[3], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush(); os.fsync(stream.fileno())
PY

  local kaniko_digest
  kaniko_digest="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["builder"]["platform_manifest_digest"])' "${RAW_DIR}/image-facts.json")"
  local kaniko_repo="${KANIKO_INDEX%@*}"
  inner_docker run --rm --pull=never --runtime runsc --network none --user 0:0 \
    --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER --cap-add SYS_CHROOT \
    --security-opt no-new-privileges --entrypoint /busybox/sh "${kaniko_repo}@${kaniko_digest}" -ceu '
      test -e /proc/gvisor/kernel_is_gvisor
      test ! -e /var/run/docker.sock && test ! -e /run/docker.sock
      test "$(awk "NR > 2 { count += 1 } END { print count + 0 }" /proc/net/dev)" -eq 1
      grep -Eq "^[[:space:]]*lo:" /proc/net/dev
      printf "builder_runtime=gvisor\nbuilder_network=loopback-only\nbuilder_host_socket=absent\n"
    ' >"${RAW_DIR}/builder-boundary.log"
  inner_docker run --rm --pull=never --runtime runsc --network none --read-only \
    --user 65532:65532 --cap-drop ALL --security-opt no-new-privileges \
    "${base}" python -c '
import pathlib
assert pathlib.Path("/proc/gvisor/kernel_is_gvisor").exists()
assert not pathlib.Path("/var/run/docker.sock").exists()
assert not pathlib.Path("/run/docker.sock").exists()
interfaces=[line.split(":",1)[0].strip() for line in pathlib.Path("/proc/net/dev").read_text().splitlines()[2:]]
assert interfaces == ["lo"]
print("oracle_runtime=gvisor\noracle_network=loopback-only\noracle_host_socket=absent")
' >"${RAW_DIR}/base-boundary.log"
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/quota.json" "${RAW_DIR}/builder-boundary.log" "${RAW_DIR}/base-boundary.log"
  chmod 0600 "${RAW_DIR}/quota.json" "${RAW_DIR}/builder-boundary.log" "${RAW_DIR}/base-boundary.log"
}

capture_harness_boundary() {
  install -d -m 0700 "${STATE_ROOT}/work"
  docker inspect "${DIND_NAME}" >"${STATE_ROOT}/work/dind-inspect.json"
  inner_docker info --format '{{json .Runtimes}}' >"${STATE_ROOT}/work/dind-runtimes.json"
  python3 - "${STATE_ROOT}/work/dind-inspect.json" "${STATE_ROOT}/work/dind-runtimes.json" \
    "${RAW_DIR}/harness.json" "${STATE_ROOT}" "${DIND_STATE}" "${RUN_ID}" <<'PY'
import json
import os
import sys

[item] = json.load(open(sys.argv[1], encoding="utf-8"))
runtimes = json.load(open(sys.argv[2], encoding="utf-8"))
host = item["HostConfig"]
mounts = {mount["Destination"]: mount["Source"] for mount in item["Mounts"]}
if item.get("Config", {}).get("Labels", {}).get("org.workstream.pilot00.run") != f"pc-{sys.argv[6]}":
    raise SystemExit("DIND owner differs")
value = {
    "cpu_nanos": host.get("NanoCpus"),
    "external_network": host.get("NetworkMode"),
    "memory_bytes": host.get("Memory"),
    "pids_limit": host.get("PidsLimit"),
    "privileged": host.get("Privileged"),
    "runtime_key": "runsc" if "runsc" in runtimes else None,
    "same_absolute_state_mount": mounts.get(sys.argv[4]) == sys.argv[4],
    "xfs_docker_state_mount": mounts.get("/var/lib/docker") == sys.argv[5],
}
expected = {
    "cpu_nanos": 2_000_000_000,
    "external_network": "none",
    "memory_bytes": 4_294_967_296,
    "pids_limit": 768,
    "privileged": True,
    "runtime_key": "runsc",
    "same_absolute_state_mount": True,
    "xfs_docker_state_mount": True,
}
if value != expected:
    raise SystemExit("DIND boundary differs")
with open(sys.argv[3], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/harness.json"
  chmod 0600 "${RAW_DIR}/harness.json"
}

prepare_contract() {
  install -d -m 0700 -o "${OWNER_UID}" -g "${DOCKER_GID}" "${ART_ROOT}" "${SERVICE_ROOT}" "${WRAPPER_WORK}"
  install -d -m 0755 "$(dirname "${SERVICE_BINARY}")"
  install -m 0555 "${REPOSITORY_ROOT}/external_checkers/target/release/workstream-checker-service" "${SERVICE_BINARY}"
  "${BACKEND_PYTHON}" "${SCRIPT_DIR}/prepare_contract.py" \
    --facts "${RAW_DIR}/image-facts.json" --cache-root "${CACHE_ROOT}" \
    --material-root "${ART_ROOT}" --socket "${SOCKET_PATH}" \
    --docker-wrapper "${DOCKER_WRAPPER}" --service-config "${SERVICE_CONFIG}" \
    --contract "${RAW_DIR}/contract.json" --inventory "${RAW_DIR}/cache-inventory.json" \
    --sandbox-uid "${OWNER_UID}" --sandbox-gid "${DOCKER_GID}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${SERVICE_CONFIG}" "${RAW_DIR}/contract.json" "${RAW_DIR}/cache-inventory.json"
  chmod 0400 "${SERVICE_CONFIG}"
  chmod 0600 "${RAW_DIR}/contract.json" "${RAW_DIR}/cache-inventory.json"
}

prepare_tool_evidence() {
  local xfs_package
  xfs_package="$(find "${RUNNER_TEMP_ROOT}" -maxdepth 1 -type f -name "xfsprogs_${XFS_PROGS_VERSION}_amd64.deb" -print -quit)"
  [[ -n "${xfs_package}" ]]
  XFS_PACKAGE_SHA="$(sha256sum "${xfs_package}" | cut -d' ' -f1)" \
  XFS_INSTALLED="$(dpkg-query -W -f='${Version}' xfsprogs)" \
  DOCKER_VERSION="$(docker version --format '{{.Client.Version}}/{{.Server.Version}}')" \
  RUNSC_VERSION="$("${STATE_ROOT}/tools/runsc" --version | head -1)" \
  RUSTC_VERSION="$(rustc --version)" CARGO_VERSION="$(cargo --version)" \
  python3 - "${RAW_DIR}/tool-versions.json" <<'PY'
import json
import os
import platform
import subprocess
import sys

value = {
    "cargo": os.environ["CARGO_VERSION"],
    "docker": os.environ["DOCKER_VERSION"],
    "findmnt": subprocess.check_output(["findmnt", "--version"], text=True).splitlines()[0],
    "kernel": platform.release(),
    "losetup": subprocess.check_output(["losetup", "--version"], text=True).strip(),
    "mkfs_xfs": subprocess.check_output(["mkfs.xfs", "-V"], text=True, stderr=subprocess.STDOUT).strip(),
    "runsc": os.environ["RUNSC_VERSION"],
    "rustc": os.environ["RUSTC_VERSION"],
    "xfs_package_sha256": os.environ["XFS_PACKAGE_SHA"],
    "xfsprogs_package": os.environ["XFS_INSTALLED"],
    "xfs_quota": subprocess.check_output(["xfs_quota", "-V"], text=True, stderr=subprocess.STDOUT).strip(),
}
with open(sys.argv[1], "x", encoding="utf-8") as stream:
    json.dump(value, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
PY
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/tool-versions.json"
  chmod 0600 "${RAW_DIR}/tool-versions.json"
}

prepare() {
  for command in docker git python3 cargo rustc truncate losetup mkfs.xfs mount findmnt mountpoint xfs_quota setpriv flock timeout; do
    require_command "${command}"
  done
  assert_source_head
  preflight
  prepare_filesystem
  install -d -m 0755 "${STATE_ROOT}"
  install -d -m 0700 -o "${OWNER_UID}" -g "${DOCKER_GID}" "${RAW_DIR}"
  pilot prepare
  capture_harness_boundary
  prepare_images
  quota_and_boundaries
  cargo build --locked --release --manifest-path "${REPOSITORY_ROOT}/external_checkers/Cargo.toml" \
    --package workstream-checker-service
  prepare_contract
  prepare_tool_evidence
  printf '%s\n' "${EXPECTED_HEAD}" >"${RAW_DIR}/proof-head.txt"
  chown "${OWNER_UID}:${DOCKER_GID}" "${RAW_DIR}/proof-head.txt"
  chmod 0600 "${RAW_DIR}/proof-head.txt"
  for name in argv.ndjson command-results.ndjson launches.ndjson service-interrupt.log service-complete.log; do
    install -m 0600 -o "${OWNER_UID}" -g "${DOCKER_GID}" /dev/null "${RAW_DIR}/${name}"
  done
  PYTHONPATH="${SCRIPT_DIR}" python3 -m unittest -q \
    test_verify_evidence test_runtime_proof
  write_owned_json "${RAW_DIR}/verifier-tests.json" \
    '{"passed":true,"suites":["test_verify_evidence","test_runtime_proof"]}'
}

service_environment() {
  env -i \
    PATH="${PATH}" HOME="${STATE_ROOT}" \
    WS493_REAL_DOCKER="${REAL_DOCKER}" WS493_DIND_NAME="${DIND_NAME}" \
    WS493_RAW_DIR="${RAW_DIR}" WS493_WRAPPER_WORK_DIR="${WRAPPER_WORK}" \
    WS493_SERVICE_PID_FILE="${SERVICE_PID_FILE}" WS493_SERVICE_BINARY="${SERVICE_BINARY}" \
    WS493_BARRIER_ENABLE="${BARRIER_ENABLE}" WS493_BARRIER_READY="${BARRIER_READY}" \
    WS493_BARRIER_RELEASE="${BARRIER_RELEASE}" WS493_BARRIER_TOKEN="${BARRIER_TOKEN}" \
    WS493_SANDBOX_USER="${OWNER_UID}:${DOCKER_GID}" WS493_ART_ROOT="${ART_ROOT}" \
    WS493_CACHE_ROOT="${CACHE_ROOT}" \
    "$@"
}

start_service() {
  local log="$1"
  rm -f "${SERVICE_PID_FILE}"
  printf 'service_start_head=%s\n' "${EXPECTED_HEAD}" >"${log}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${log}"
  chmod 0600 "${log}"
  service_environment setpriv --reuid "${OWNER_UID}" --regid "${DOCKER_GID}" --clear-groups \
    sh -c 'printf "%s\n" "$$" >"$1"; exec "$2" "$3"' sh \
    "${SERVICE_PID_FILE}" "${SERVICE_BINARY}" "${SERVICE_CONFIG}" >>"${log}" 2>&1 &
  SERVICE_JOB_PID=$!
  for _ in $(seq 1 300); do
    [[ -S "${SOCKET_PATH}" ]] && return 0
    kill -0 "${SERVICE_JOB_PID}" 2>/dev/null || { wait "${SERVICE_JOB_PID}"; return 1; }
    sleep 0.2
  done
  return 1
}

run_as_owner() {
  setpriv --reuid "${OWNER_UID}" --regid "${DOCKER_GID}" --clear-groups \
    env HOME="${STATE_ROOT}" PYTHONPATH="${REPOSITORY_ROOT}/backend" "$@"
}

positive_owned_absence() {
  local containers images
  containers="$(inner_docker ps -aq --no-trunc --filter 'label=workstream.owner=terminal-benchmark-checker-service-v1')"
  images="$(inner_docker image ls --no-trunc --quiet 'workstream.local/terminal-benchmark-candidate:*')"
  [[ -z "${containers}" && -z "${images}" ]]
}

run_matrix() {
  [[ "$(id -u)" -eq 0 ]]
  assert_source_head
  local event_since
  event_since="$(date +%s)"
  local control="${PROOF_PREFIX}-unowned-control"
  inner_docker create --pull=never --name "${control}" --runtime runsc --network none \
    --label "org.workstream.ws493.control=${RUN_ID}" "${BASE_PLATFORM_IMAGE}" true >/dev/null
  printf '%s\n' enabled >"${BARRIER_ENABLE}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${BARRIER_ENABLE}"
  chmod 0600 "${BARRIER_ENABLE}"
  start_service "${RAW_DIR}/service-interrupt.log"
  local first_service_job="${SERVICE_JOB_PID}"
  run_as_owner "${BACKEND_PYTHON}" "${SCRIPT_DIR}/execute_post.py" \
    --contract "${RAW_DIR}/contract.json" --package "${PACKAGE}" --scratch "${ART_ROOT}" \
    --socket "${SOCKET_PATH}" --expect interrupted --output "${RAW_DIR}/interrupt.json" \
    --art-output "${RAW_DIR}/art-interrupt.json" &
  local executor_pid=$!
  for _ in $(seq 1 600); do
    [[ -f "${BARRIER_READY}" && ! -L "${BARRIER_READY}" ]] && break
    kill -0 "${executor_pid}" 2>/dev/null || { wait "${executor_pid}"; return 1; }
    sleep 0.2
  done
  [[ -f "${BARRIER_READY}" && ! -L "${BARRIER_READY}" ]]
  local service_pid wrapper_pid
  read -r service_pid wrapper_pid < <(python3 - "${BARRIER_READY}" "${BARRIER_TOKEN}" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
if value.get("token") != sys.argv[2]: raise SystemExit(1)
print(value["service_pid"], value["wrapper_pid"])
PY
)
  [[ "${service_pid}" == "$(cat "${SERVICE_PID_FILE}")" ]]
  [[ "$(readlink -f "/proc/${service_pid}/exe")" == "$(readlink -f "${SERVICE_BINARY}")" ]]
  kill -KILL "${service_pid}"
  wait "${first_service_job}" || true
  wait "${executor_pid}"
  [[ -s "${RAW_DIR}/art-interrupt.json" ]]
  printf '%s\n' "${BARRIER_TOKEN}" >"${BARRIER_RELEASE}"
  chown "${OWNER_UID}:${DOCKER_GID}" "${BARRIER_RELEASE}"
  chmod 0600 "${BARRIER_RELEASE}"
  for _ in $(seq 1 150); do
    kill -0 "${wrapper_pid}" 2>/dev/null || break
    sleep 0.2
  done
  ! kill -0 "${wrapper_pid}" 2>/dev/null
  rm -f "${BARRIER_ENABLE}" "${BARRIER_READY}" "${BARRIER_RELEASE}"

  start_service "${RAW_DIR}/service-complete.log"
  local second_service_job="${SERVICE_JOB_PID}"
  positive_owned_absence
  [[ "$(inner_docker inspect "${control}" --format '{{index .Config.Labels "org.workstream.ws493.control"}}')" == "${RUN_ID}" ]]
  write_owned_json "${RAW_DIR}/restart-cleanup.json" \
    '{"owned_containers_absent":true,"owned_images_absent":true,"unowned_control_preserved":true}'
  run_as_owner "${BACKEND_PYTHON}" "${SCRIPT_DIR}/execute_post.py" \
    --contract "${RAW_DIR}/contract.json" --package "${PACKAGE}" --scratch "${ART_ROOT}" \
    --socket "${SOCKET_PATH}" --expect complete --output "${RAW_DIR}/complete-result.json" \
    --art-output "${RAW_DIR}/art-complete.json"
  positive_owned_absence
  [[ "$(inner_docker inspect "${control}" --format '{{index .Config.Labels "org.workstream.ws493.control"}}')" == "${RUN_ID}" ]]
  inner_docker rm -f -v "${control}" >/dev/null
  kill -TERM "$(cat "${SERVICE_PID_FILE}")"
  wait "${second_service_job}" || true

  timeout 15 "${REAL_DOCKER}" exec "${DIND_NAME}" docker events \
    --since "${event_since}" --until "$(date +%s)" \
    --filter 'label=workstream.owner=terminal-benchmark-checker-service-v1' \
    --format '{{json .}}' | head -c 262144 >"${RAW_DIR}/docker-events.ndjson"
  [[ -s "${RAW_DIR}/docker-events.ndjson" ]]
  run_as_owner python3 "${SCRIPT_DIR}/build_matrix.py" \
    --raw "${RAW_DIR}" --head "${EXPECTED_HEAD}" --output "${RAW_DIR}/matrix.json"
  find "${RAW_DIR}" -maxdepth 1 -type f -exec chmod 0600 {} +
  [[ -z "$(find "${RAW_DIR}" -mindepth 1 -maxdepth 1 ! -type f -print -quit)" ]]
}

stage_evidence() {
  python3 "${SCRIPT_DIR}/verify_evidence.py" stage \
    "${RAW_DIR}" "${STAGING_DIR}" "${EXPECTED_HEAD}" "${OWNER_UID}"
}

cleanup() {
  [[ "$(id -u)" -eq 0 ]]
  if [[ -f "${SERVICE_PID_FILE}" && ! -L "${SERVICE_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${SERVICE_PID_FILE}")"
    if [[ "${pid}" =~ ^[1-9][0-9]*$ ]] && [[ -e "/proc/${pid}/exe" ]] \
      && [[ "$(readlink -f "/proc/${pid}/exe")" == "$(readlink -f "${SERVICE_BINARY}")" ]]; then
      kill -TERM "${pid}" || true
    fi
  fi
  if [[ -d "${WRAPPER_WORK}" ]]; then
    printf '%s\n' "${BARRIER_TOKEN}" >"${BARRIER_RELEASE}" || true
    chown "${OWNER_UID}:${DOCKER_GID}" "${BARRIER_RELEASE}" 2>/dev/null || true
  fi
  if docker inspect "${DIND_NAME}" >/dev/null 2>&1; then
    pilot cleanup
  fi
  local outer_absent=false
  docker image rm -f "ws493-checker:${EXPECTED_HEAD}" "ws493-kaniko:${EXPECTED_HEAD}" >/dev/null 2>&1 || true
  if [[ -z "$(docker ps -aq --no-trunc --filter "label=${OUTER_OWNER_LABEL}")" ]] \
    && [[ -z "$(docker ps -aq --no-trunc --filter "label=org.workstream.ws493.run=${RUN_ID}")" ]] \
    && [[ -z "$(docker image ls --quiet "ws493-checker:${EXPECTED_HEAD}")" ]] \
    && [[ -z "$(docker image ls --quiet "ws493-kaniko:${EXPECTED_HEAD}")" ]]; then
    outer_absent=true
  fi
  local unmounted=false detached=false deleted=false
  if mountpoint -q "${MOUNT_ROOT}"; then
    umount "${MOUNT_ROOT}"
  fi
  if ! mountpoint -q "${MOUNT_ROOT}"; then unmounted=true; fi
  if [[ -f "${LOOP_RECORD}" && ! -L "${LOOP_RECORD}" ]]; then
    local loop_device
    loop_device="$(cat "${LOOP_RECORD}")"
    if losetup "${loop_device}" >/dev/null 2>&1; then losetup -d "${loop_device}"; fi
  fi
  if [[ ! -e "${RAW_DEVICE_FILE}" ]] || [[ -z "$(losetup -j "${RAW_DEVICE_FILE}")" ]]; then detached=true; fi
  rm -f "${RAW_DEVICE_FILE}" "${LOOP_RECORD}"
  rm -f "${RUNNER_TEMP_ROOT}/xfsprogs_${XFS_PROGS_VERSION}_amd64.deb"
  rmdir "${MOUNT_ROOT}" 2>/dev/null || true
  if [[ ! -e "${RAW_DEVICE_FILE}" && ! -e "${STATE_ROOT}" ]]; then deleted=true; fi
  rm -f "${CLEANUP_RECEIPT}"
  python3 - "${CLEANUP_RECEIPT}" "${EXPECTED_HEAD}" "${outer_absent}" "${unmounted}" "${detached}" "${deleted}" <<'PY'
import json, os, sys
truth = lambda value: value == "true"
body = {
    "schema_version": "workstream.terminal_benchmark_project_checker_proof.v1",
    "head_sha": sys.argv[2],
    "dind_absent": truth(sys.argv[3]),
    "registry_absent": truth(sys.argv[3]),
    "outer_owned_resources_absent": truth(sys.argv[3]),
    "xfs_unmounted": truth(sys.argv[4]),
    "loop_detached": truth(sys.argv[5]),
    "raw_state_deleted": truth(sys.argv[6]),
}
with open(sys.argv[1], "x", encoding="utf-8") as stream:
    json.dump(body, stream, separators=(",", ":"), sort_keys=True)
    stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
PY
  chmod 0600 "${CLEANUP_RECEIPT}"
  if [[ -d "${STAGING_DIR}" ]]; then
    python3 "${SCRIPT_DIR}/verify_evidence.py" add-cleanup \
      "${STAGING_DIR}" "${CLEANUP_RECEIPT}" "${EXPECTED_HEAD}" 0
  fi
  [[ "${outer_absent}" == true && "${unmounted}" == true && "${detached}" == true && "${deleted}" == true ]]
}

final_evidence() {
  python3 "${SCRIPT_DIR}/verify_evidence.py" final "${STAGING_DIR}" "${EXPECTED_HEAD}"
}

case "${ACTION}" in
  preflight) assert_source_head; preflight ;;
  prepare) prepare ;;
  run) run_matrix ;;
  stage) stage_evidence ;;
  cleanup) cleanup ;;
  final) final_evidence ;;
  *) echo "usage: $0 preflight|prepare|run|stage|cleanup|final" >&2; exit 64 ;;
esac
