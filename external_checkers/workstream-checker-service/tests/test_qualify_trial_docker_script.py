"""Focused fail-closed evidence tests for the standalone trial qualifier."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "external_checkers/workstream-checker-service/scripts/qualify_trial_docker.sh"
TOOLS = ROOT / "experiments/pilot00_gvisor_offline/tool-inputs.env"


def _source_identity() -> tuple[str, str]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    return head, tree


def _environment(
    *, state: Path, prefix: Path, head: str, tree: str, path: str | None = None
) -> dict[str, str]:
    result = os.environ.copy()
    result.update(
        {
            "WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT": str(state),
            "WORKSTREAM_TRIAL_QUALIFICATION_CONTAINER": "qualification-container",
            "WORKSTREAM_TRIAL_QUALIFICATION_RUN_ID": "qualification-test",
            "WORKSTREAM_TRIAL_PLATFORM_IDENTITY_SHA256": "sha256:" + "7" * 64,
            "WORKSTREAM_TRIAL_QUALIFICATION_EXPECTED_HEAD": head,
            "WORKSTREAM_TRIAL_QUALIFICATION_EXPECTED_TREE": tree,
            "WORKSTREAM_TRIAL_QUALIFICATION_INVOCATION_NONCE": "wrapper-test",
            "WORKSTREAM_TRIAL_QUALIFICATION_EVIDENCE_PREFIX": str(prefix),
        }
    )
    if path is not None:
        result["PATH"] = path
    return result


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _prepare_state(state: Path) -> None:
    declared = {}
    for line in TOOLS.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            declared[key] = value
    (state / "results").mkdir(parents=True)
    value = {
        "run_id": "qualification-test",
        "shared_state_path": str(state),
        "docker_state_path": str(state / "dind-state"),
        "scratch_path": str(state / "trial-scratch"),
        "cache_path": str(state / "cache/content"),
        "cache_manifest_path": str(state / "cache/cache.sha256"),
        "runtime_configuration_path": str(state / "daemon.json"),
        "protected_role_path": str(state / "protected-role"),
        "cache_manifest_sha256": "sha256:0d7c48edceae685051d2f60497b0df7f55a0f3f8dd6d29c5e82b9c0cd75a40e1",
        "runtime_configuration_sha256": "sha256:46429fe1ec5b135d7214c1090c28c75a3175169307ae2981c502015152c3d330",
        "runsc_binary_sha256": "sha256:88a87d5d6d06160d4c144f51f95ec6dd6fe0fc6b02697eb877876683c5b57a91",
        "runsc_version": f"runsc version {declared['GVISOR_VERSION']}\nspec: 1.2.1",
        "builder_image_id": declared["KANIKO_IMAGE_ID"],
        "builder_manifest": declared["KANIKO_IMAGE"],
        "base_manifest": declared["BASE_PLATFORM_IMAGE"],
    }
    (state / "prepared-assets.json").write_text(json.dumps(value), encoding="utf-8")


def _install_success_fakes(root: Path) -> Path:
    fake_bin = root / "bin"
    fake_bin.mkdir()
    qualifier = root / "qualify-trial-docker"
    launcher = root / "workstream-trial-launcher"
    _write_executable(qualifier, "#!/bin/sh\nexit 0\n")
    _write_executable(launcher, "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "cargo",
        f"""#!/bin/sh
case "$*" in
  *"--bin qualify-trial-docker"*) executable={qualifier} ;;
  *"--bin workstream-trial-launcher"*) executable={launcher} ;;
  *) exit 91 ;;
esac
printf '{{"reason":"compiler-artifact","target":{{"name":"%s","kind":["bin"]}},"executable":"%s"}}\n' "$(basename "$executable")" "$executable"
""",
    )
    _write_executable(fake_bin / "readelf", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "docker",
        """#!/bin/sh
if [ "$1" = inspect ]; then
  printf '[{"Config":{"Labels":{"org.workstream.pilot00.run":"qualification-test"}},"State":{"Running":true},"Mounts":[{"Destination":"/workstream-state","Source":"%s"}]}]\n' "$WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT"
  exit 0
fi
case "$*" in
  *"qualification-bin/qualify-trial-docker"*)
    mkdir -p "$WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT/results"
    printf '{"schema_version":"workstream.trial_docker_qualification.v1"}\n' > "$WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT/results/trial-docker-qualification.json"
    ;;
  *"rm -f -- /workstream-state/results/trial-docker-qualification.json"*)
    rm -f "$WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT/results/trial-docker-qualification.json"
    ;;
esac
exit 0
""",
    )
    return fake_bin


def _install_python_failure_injector(fake_bin: Path) -> None:
    _write_executable(
        fake_bin / "python3",
        """#!/bin/sh
program="$(mktemp)"
trap 'rm -f "$program"' EXIT
cat > "$program"
if [ "$1" = - ] && [ "${2:-}" = "${FAIL_AFTER_LINK_RESULT:-}" ]; then
  printf '\nraise SystemExit("injected-post-link-failure")\n' >> "$program"
fi
"$REAL_PYTHON" "$@" < "$program"
""",
    )


class TrialQualifierWrapperTest(unittest.TestCase):
    def test_source_substitution_retains_failure_and_never_publishes_success(self) -> None:
        head, tree = _source_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "wrong-source"
            result = subprocess.run(
                [SCRIPT],
                env=_environment(state=root / "state", prefix=prefix, head="0" * 40, tree=tree),
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("source commit differs", prefix.with_suffix(".log").read_text())
            self.assertNotEqual(prefix.with_suffix(".exit").read_text().strip(), "0")
            self.assertFalse(prefix.with_suffix(".json").exists())
            self.assertEqual(head, _source_identity()[0])

    def test_preexisting_success_is_refused_without_overwrite(self) -> None:
        head, tree = _source_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prefix = root / "stale"
            retained = prefix.with_suffix(".json")
            retained.write_text('{"retained":"old"}\n', encoding="utf-8")
            result = subprocess.run(
                [SCRIPT],
                env=_environment(state=root / "state", prefix=prefix, head=head, tree=tree),
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(retained.read_text(), '{"retained":"old"}\n')
            self.assertFalse(prefix.with_suffix(".log").exists())
            self.assertFalse(prefix.with_suffix(".exit").exists())

    def test_preexisting_inner_result_is_retained_but_cannot_become_current(self) -> None:
        head, tree = _source_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            prefix = root / "inner-stale"
            retained = state / "results/trial-docker-qualification.json"
            retained.parent.mkdir(parents=True)
            retained.write_text('{"retained":"old"}\n', encoding="utf-8")
            result = subprocess.run(
                [SCRIPT],
                env=_environment(state=state, prefix=prefix, head=head, tree=tree),
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(retained.read_text(), '{"retained":"old"}\n')
            self.assertIn("retained result path already exists", prefix.with_suffix(".log").read_text())
            self.assertNotEqual(prefix.with_suffix(".exit").read_text().strip(), "0")
            self.assertFalse(prefix.with_suffix(".json").exists())

    def test_tool_failure_retains_log_exit_and_no_success_json(self) -> None:
        head, tree = _source_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            prefix = root / "tool-failure"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            _prepare_state(state)
            _write_executable(
                fake_bin / "docker",
                """#!/bin/sh
if [ "$1" = inspect ]; then
  printf '[{"Config":{"Labels":{"org.workstream.pilot00.run":"qualification-test"}},"State":{"Running":true},"Mounts":[{"Destination":"/workstream-state","Source":"%s"}]}]\n' "$WORKSTREAM_TRIAL_QUALIFICATION_STATE_ROOT"
fi
exit 0
""",
            )
            _write_executable(
                fake_bin / "cargo",
                "#!/bin/sh\necho simulated-cargo-failure >&2\nexit 23\n",
            )
            path = f"{fake_bin}:{os.environ['PATH']}"
            result = subprocess.run(
                [SCRIPT],
                env=_environment(state=state, prefix=prefix, head=head, tree=tree, path=path),
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
            self.assertIn("simulated-cargo-failure", prefix.with_suffix(".log").read_text())
            self.assertEqual(prefix.with_suffix(".exit").read_text(), "23\n")
            self.assertFalse(prefix.with_suffix(".json").exists())
            self.assertFalse((state / "results/trial-docker-qualification.json").exists())

    def test_success_publishes_exact_bound_summary_after_cleanup(self) -> None:
        head, tree = _source_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            prefix = root / "success"
            _prepare_state(state)
            fake_bin = _install_success_fakes(root)
            result = subprocess.run(
                [SCRIPT],
                env=_environment(
                    state=state,
                    prefix=prefix,
                    head=head,
                    tree=tree,
                    path=f"{fake_bin}:{os.environ['PATH']}",
                ),
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(prefix.with_suffix(".exit").read_text(), "0\n")
            summary = json.loads(prefix.with_suffix(".json").read_text())
            self.assertEqual(summary["source"], {"head": head, "tree": tree})
            self.assertEqual(summary["invocation_nonce"], "wrapper-test")
            self.assertTrue(summary["cleanup_confirmed"])
            self.assertEqual(
                summary["qualification"]["schema_version"],
                "workstream.trial_docker_qualification.v1",
            )
            self.assertFalse((state / "results/trial-docker-qualification.json").exists())

    def test_failure_after_atomic_link_retracts_success_json(self) -> None:
        head, tree = _source_identity()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            prefix = root / "post-link-failure"
            _prepare_state(state)
            fake_bin = _install_success_fakes(root)
            _install_python_failure_injector(fake_bin)
            environment = _environment(
                state=state,
                prefix=prefix,
                head=head,
                tree=tree,
                path=f"{fake_bin}:{os.environ['PATH']}",
            )
            environment["REAL_PYTHON"] = sys.executable
            environment["FAIL_AFTER_LINK_RESULT"] = str(prefix.with_suffix(".json"))
            result = subprocess.run(
                [SCRIPT],
                env=environment,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("injected-post-link-failure", prefix.with_suffix(".log").read_text())
            self.assertNotEqual(prefix.with_suffix(".exit").read_text().strip(), "0")
            self.assertFalse(prefix.with_suffix(".json").exists())
            self.assertFalse((state / "results/trial-docker-qualification.json").exists())


if __name__ == "__main__":
    unittest.main()
