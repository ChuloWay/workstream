#!/usr/bin/env bash
set -euo pipefail

# Explicit qualification runner for the production service + project image +
# generic trial engine. This mutates only the named, stopped PILOT-00 DIND
# harness and restores its daemon configuration byte-for-byte on every exit.

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPOSITORY_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly STATE_ROOT="${WORKSTREAM_TS_RUNSC_STATE_ROOT:?set the prepared PILOT-00 state root}"
readonly CONTAINER="${WORKSTREAM_TS_RUNSC_CONTAINER:?set the owned DIND container}"
readonly RUN_ID="${WORKSTREAM_TS_RUNSC_RUN_ID:?set the prepared PILOT-00 run ID}"
readonly CHECKER_IMAGE="${WORKSTREAM_TS_RUNSC_CHECKER_IMAGE:-ws-terminal-systems-post:qualification}"
readonly REGISTRY_IMAGE="${WORKSTREAM_TS_RUNSC_REGISTRY_IMAGE:-registry:2}"
readonly INNER_ROOT="/workstream-state"
readonly COMPOSITION_ROOT="${STATE_ROOT}/terminal-systems-runsc-composition"
readonly INNER_COMPOSITION_ROOT="${INNER_ROOT}/terminal-systems-runsc-composition"
readonly ORIGINAL_CONFIG="$(mktemp /tmp/ws493-runsc-daemon.XXXXXX.json)"
readonly ORIGINAL_CONFIG_MODE="$(stat -c '%a' "${STATE_ROOT}/daemon.json")"
readonly BUILD_MESSAGES="$(mktemp /tmp/ws493-runsc-build.XXXXXX.jsonl)"
readonly METADATA="${WORKSTREAM_TS_RUNSC_METADATA:-/tmp/ws493-terminal-systems-runsc.json}"
readonly RESULT_LOG="${WORKSTREAM_TS_RUNSC_LOG:-/tmp/ws493-terminal-systems-runsc.log}"
readonly EXIT_SIDECAR="${WORKSTREAM_TS_RUNSC_EXIT:-/tmp/ws493-terminal-systems-runsc.exit}"
readonly EXTRACT_CONTAINER="ws493-runsc-registry-extract-${RUN_ID}"

STARTED=0
CONFIG_REPLACED=0

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "${STARTED}" == 1 ]]; then
    docker exec "${CONTAINER}" sh -ceu '
      if test -s /workstream-state/terminal-systems-runsc-composition/registry.pid; then
        kill "$(cat /workstream-state/terminal-systems-runsc-composition/registry.pid)" 2>/dev/null || true
      fi
      docker container ls -aq --filter label=workstream.external-checker=true | xargs -r docker rm -f >/dev/null
      docker container ls -aq --filter label=workstream.trial.deployment=terminal-systems-runsc-qualification | xargs -r docker rm -f >/dev/null
      docker images --format "{{.Repository}}:{{.Tag}}" --filter reference="workstream-trial:*" \
        | xargs -r docker image rm >/dev/null
    '
    docker exec "${CONTAINER}" docker image rm \
      127.0.0.1:5000/terminal-systems-post:qualification \
      "${CHECKER_IMAGE}" \
      >/dev/null 2>&1 || true
    if [[ -n "${WORKSTREAM_TS_RUNSC_CHECKER_DIGEST:-}" ]]; then
      docker exec "${CONTAINER}" docker image rm \
        "127.0.0.1:5000/terminal-systems-post@${WORKSTREAM_TS_RUNSC_CHECKER_DIGEST}" \
        >/dev/null 2>&1 || true
    fi
    docker stop --time 15 "${CONTAINER}" >/dev/null 2>&1 || status=1
  fi
  docker rm -f "${EXTRACT_CONTAINER}" >/dev/null 2>&1 || true
  if [[ "${CONFIG_REPLACED}" == 1 ]]; then
    cp -- "${ORIGINAL_CONFIG}" "${STATE_ROOT}/daemon.json"
    chmod "${ORIGINAL_CONFIG_MODE}" "${STATE_ROOT}/daemon.json"
    if ! cmp -s -- "${ORIGINAL_CONFIG}" "${STATE_ROOT}/daemon.json"; then
      status=1
    fi
  fi
  rm -f -- "${ORIGINAL_CONFIG}" "${BUILD_MESSAGES}"
  printf '%s\n' "${status}" >"${EXIT_SIDECAR}"
  exit "${status}"
}
trap cleanup EXIT INT TERM

[[ "${STATE_ROOT}" == /* ]]
[[ "${RUN_ID}" =~ ^[a-z0-9][a-z0-9-]{0,30}$ ]]
[[ "${CONTAINER}" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]
[[ -n "${WORKSTREAM_TEST_ADMIN_DATABASE_URL:-}" ]]
[[ -n "${WORKSTREAM_TEST_MINIO_ENDPOINT:-}" ]]

python3 - "${STATE_ROOT}/prepared-assets.json" "${STATE_ROOT}" "${RUN_ID}" "${CONTAINER}" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

manifest_path, root, run_id, container = sys.argv[1:]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
expected = {
    "run_id": run_id,
    "container": container,
    "shared_state_path": root,
    "runtime_configuration_path": f"{root}/daemon.json",
}
for key, value in expected.items():
    if manifest.get(key) != value:
        raise SystemExit(f"prepared qualification identity differs: {key}")
inspection = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
if inspection["Config"]["Labels"].get("org.workstream.pilot00.run") != run_id:
    raise SystemExit("qualification container has the wrong owner label")
if inspection["State"]["Running"]:
    raise SystemExit("qualification requires the owned DIND container to be stopped")
mounts = [item["Source"] for item in inspection["Mounts"] if item["Destination"] == "/workstream-state"]
if mounts != [root]:
    raise SystemExit("qualification container has the wrong shared-state mount")
PY

cp -- "${STATE_ROOT}/daemon.json" "${ORIGINAL_CONFIG}"
python3 - "${STATE_ROOT}/prepared-assets.json" "${ORIGINAL_CONFIG}" "${STATE_ROOT}/daemon.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
source = Path(sys.argv[2]).read_bytes()
actual = "sha256:" + hashlib.sha256(source).hexdigest()
if actual != manifest["runtime_configuration_sha256"]:
    raise SystemExit("prepared daemon configuration digest differs")
value = json.loads(source)
if set(value.get("runtimes", {})) != {"runsc"}:
    raise SystemExit("prepared daemon configuration runtime set differs")
child = value["runtimes"]["runsc"]
arguments = child.get("runtimeArgs")
if not isinstance(arguments, list) or arguments.count("--host-uds=none") != 1:
    raise SystemExit("prepared child runtime host UDS policy differs")
outer = json.loads(json.dumps(child))
outer["runtimeArgs"] = ["--host-uds=open" if item == "--host-uds=none" else item for item in arguments]
value["runtimes"] = {"runsc": outer, "runsc-trial": child}
encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
temporary = Path(sys.argv[3] + ".ws493-new")
temporary.write_bytes(encoded)
temporary.chmod(0o644)
temporary.replace(sys.argv[3])
print("sha256:" + hashlib.sha256(encoded).hexdigest())
PY
CONFIG_REPLACED=1
readonly DUAL_RUNTIME_DIGEST="$(sha256sum "${STATE_ROOT}/daemon.json" | awk '{print "sha256:" $1}')"

rm -rf -- "${COMPOSITION_ROOT}"
mkdir -p -- "${COMPOSITION_ROOT}/bin" "${COMPOSITION_ROOT}/input" "${COMPOSITION_ROOT}/registry-data"
chmod 0700 "${COMPOSITION_ROOT}" "${COMPOSITION_ROOT}/bin" "${COMPOSITION_ROOT}/input" "${COMPOSITION_ROOT}/registry-data"

(
  cd "${REPOSITORY_ROOT}"
  CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=1 RUST_MIN_STACK=67108864 cargo build \
    --locked -p workstream-checker-service --bin workstream-checker-service \
    --message-format=json-render-diagnostics >"${BUILD_MESSAGES}"
)
readonly SERVICE_BINARY="$(python3 - "${BUILD_MESSAGES}" <<'PY'
import json
import sys

values = []
for line in open(sys.argv[1], encoding="utf-8"):
    item = json.loads(line)
    if (
        item.get("reason") == "compiler-artifact"
        and item["target"]["name"] == "workstream-checker-service"
        and "bin" in item["target"]["kind"]
        and item.get("executable")
    ):
        values.append(item["executable"])
if len(values) != 1:
    raise SystemExit("cargo did not report exactly one service executable")
print(values[0])
PY
)"
[[ -x "${SERVICE_BINARY}" ]]
cp -- "${SERVICE_BINARY}" "${COMPOSITION_ROOT}/bin/workstream-checker-service"
cp -- "$(readlink -f /lib64/ld-linux-x86-64.so.2)" "${COMPOSITION_ROOT}/bin/ld-linux-x86-64.so.2"
cp -- "$(readlink -f /lib/x86_64-linux-gnu/libgcc_s.so.1)" "${COMPOSITION_ROOT}/bin/libgcc_s.so.1"
cp -- "$(readlink -f /lib/x86_64-linux-gnu/libm.so.6)" "${COMPOSITION_ROOT}/bin/libm.so.6"
cp -- "$(readlink -f /lib/x86_64-linux-gnu/libc.so.6)" "${COMPOSITION_ROOT}/bin/libc.so.6"
chmod 0555 "${COMPOSITION_ROOT}/bin/"*

docker build --pull=false --network=none --tag "${CHECKER_IMAGE}" \
  --file "${REPOSITORY_ROOT}/pilots/terminal_systems/checkers/post/model/Dockerfile" \
  "${REPOSITORY_ROOT}/pilots/terminal_systems/checkers/post/model" >/dev/null
docker image inspect "${CHECKER_IMAGE}" >/dev/null
docker image inspect "${REGISTRY_IMAGE}" >/dev/null
docker save --output "${COMPOSITION_ROOT}/input/checker-image.tar" "${CHECKER_IMAGE}"
docker create --name "${EXTRACT_CONTAINER}" "${REGISTRY_IMAGE}" >/dev/null
docker cp "${EXTRACT_CONTAINER}:/bin/registry" "${COMPOSITION_ROOT}/bin/registry"
docker rm "${EXTRACT_CONTAINER}" >/dev/null
chmod 0555 "${COMPOSITION_ROOT}/bin/registry"
cat >"${COMPOSITION_ROOT}/registry.yml" <<'YAML'
version: 0.1
log:
  level: error
storage:
  filesystem:
    rootdirectory: /workstream-state/terminal-systems-runsc-composition/registry-data
http:
  addr: 127.0.0.1:5000
YAML
chmod 0444 "${COMPOSITION_ROOT}/registry.yml"

docker start "${CONTAINER}" >/dev/null
STARTED=1
for _attempt in $(seq 1 45); do
  if docker exec "${CONTAINER}" docker info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "${CONTAINER}" docker info >/dev/null
if docker exec "${CONTAINER}" docker image inspect "${CHECKER_IMAGE}" >/dev/null 2>&1; then
  echo "qualification checker image unexpectedly preexists in owned DIND" >&2
  exit 1
fi
test -z "$(docker exec "${CONTAINER}" docker images -q --filter reference='workstream-trial:*')"
docker exec "${CONTAINER}" sh -ceu '
  chgrp 1000 /var/run/docker.sock
  chmod 0660 /var/run/docker.sock
  chown -R 1000:1000 /workstream-state/terminal-systems-runsc-composition
  chmod 0711 /workstream-state
  nohup /workstream-state/terminal-systems-runsc-composition/bin/registry serve \
    /workstream-state/terminal-systems-runsc-composition/registry.yml \
    >/workstream-state/terminal-systems-runsc-composition/registry.log 2>&1 &
  echo $! >/workstream-state/terminal-systems-runsc-composition/registry.pid
'
for _attempt in $(seq 1 30); do
  if docker exec "${CONTAINER}" sh -ceu 'wget -q -O /dev/null http://127.0.0.1:5000/v2/'; then
    break
  fi
  sleep 0.2
done
docker exec "${CONTAINER}" sh -ceu 'wget -q -O /dev/null http://127.0.0.1:5000/v2/'
python3 - "${CONTAINER}" <<'PY'
import json
import subprocess
import sys

value = json.loads(
    subprocess.check_output(
        ["docker", "exec", sys.argv[1], "cat", "/etc/docker/pilot-daemon.json"]
    )
)
runtimes = value.get("runtimes", {})
if set(runtimes) != {"runsc", "runsc-trial"}:
    raise SystemExit("qualification runtime keys differ")
outer = runtimes["runsc"].get("runtimeArgs", [])
child = runtimes["runsc-trial"].get("runtimeArgs", [])
if "--host-uds=open" not in outer or any(
    item.startswith("--host-uds=") and item != "--host-uds=open" for item in outer
):
    raise SystemExit("outer host UDS policy differs")
if "--host-uds=none" not in child or any(
    item.startswith("--host-uds=") and item != "--host-uds=none" for item in child
):
    raise SystemExit("child host UDS policy differs")
PY
docker exec "${CONTAINER}" docker load --input "${INNER_COMPOSITION_ROOT}/input/checker-image.tar" >/dev/null
docker exec "${CONTAINER}" docker tag "${CHECKER_IMAGE}" \
  127.0.0.1:5000/terminal-systems-post:qualification
docker exec "${CONTAINER}" docker push \
  127.0.0.1:5000/terminal-systems-post:qualification >/dev/null

readonly CHECKER_INSPECTION="$(docker exec "${CONTAINER}" docker image inspect 127.0.0.1:5000/terminal-systems-post:qualification)"
readonly CHECKER_DIGEST="$(python3 -c 'import json,sys; v=json.load(sys.stdin)[0]; print(next(x.split("@",1)[1] for x in v["RepoDigests"] if x.startswith("127.0.0.1:5000/terminal-systems-post@")))' <<<"${CHECKER_INSPECTION}")"
readonly CHECKER_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["Id"])' <<<"${CHECKER_INSPECTION}")"
readonly PLATFORM_IDENTITY="$(docker exec "${CONTAINER}" docker info --format '{{json .}}' | python3 -c '
import hashlib,json,sys
v=json.load(sys.stdin); key="runsc-trial"; runtime=v["Runtimes"][key]
facts={"architecture":v.get("Architecture"),"cgroup_driver":v.get("CgroupDriver"),"cgroup_version":v.get("CgroupVersion"),"driver":v.get("Driver"),"kernel_version":v.get("KernelVersion"),"operating_system":v.get("OperatingSystem"),"os_type":v.get("OSType"),"runtime":{"path":runtime.get("path"),"runtime_args":runtime.get("runtimeArgs")}}
b=json.dumps(facts,sort_keys=True,separators=(",", ":")).encode(); print("sha256:"+hashlib.sha256(b).hexdigest())
')"

export WORKSTREAM_TS_RUNSC_INNER_ROOT="${INNER_ROOT}"
export WORKSTREAM_TS_RUNSC_COMPOSITION_ROOT="${COMPOSITION_ROOT}"
export WORKSTREAM_TS_RUNSC_INNER_COMPOSITION_ROOT="${INNER_COMPOSITION_ROOT}"
export WORKSTREAM_TS_RUNSC_CONTAINER="${CONTAINER}"
export WORKSTREAM_TS_RUNSC_DAEMON_DIGEST="${DUAL_RUNTIME_DIGEST}"
export WORKSTREAM_TS_RUNSC_PLATFORM_IDENTITY="${PLATFORM_IDENTITY}"
export WORKSTREAM_TS_RUNSC_CHECKER_REPOSITORY="127.0.0.1:5000/terminal-systems-post"
export WORKSTREAM_TS_RUNSC_CHECKER_DIGEST="${CHECKER_DIGEST}"
export WORKSTREAM_TS_RUNSC_CHECKER_ID="${CHECKER_ID}"
export WORKSTREAM_TS_RUNSC_BUILDER_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["builder_image_id"])' "${STATE_ROOT}/prepared-assets.json")"
export WORKSTREAM_TS_RUNSC_BUILDER_MANIFEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["builder_manifest"])' "${STATE_ROOT}/prepared-assets.json")"
export WORKSTREAM_TS_RUNSC_CACHE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["cache_manifest_sha256"])' "${STATE_ROOT}/prepared-assets.json")"
export WORKSTREAM_TS_RUNSC_ENGINE_DIGEST="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["runsc_binary_sha256"])' "${STATE_ROOT}/prepared-assets.json")"

cd "${REPOSITORY_ROOT}/backend"
set +e
.venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json "${METADATA}" --timeout-seconds 900 --lane trial_composition -- \
  env PYTHONPATH=.:tests .venv/bin/pytest -vv -x -p conftest -o faulthandler_timeout=120 \
  ../external_checkers/workstream-checker-service/tests/terminal_systems_runsc_composition.py \
  >"${RESULT_LOG}" 2>&1
readonly TEST_STATUS=$?
set -e
cat "${RESULT_LOG}"
exit "${TEST_STATUS}"
