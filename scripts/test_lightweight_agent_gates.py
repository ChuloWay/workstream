"""Focused regression tests for the lightweight repository checks."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.check_markdown_links import local_target
from scripts.check_markdown_links import should_check_links
from scripts.check_stale_artifact_contracts import phase_index
from scripts.check_stale_artifact_contracts import scan_text as scan_artifact_text
from scripts.check_stale_authorization_docs import scan_text as scan_authorization_text
from scripts.check_stale_workstream_wording import FORBIDDEN_PATTERNS
from scripts.check_stale_workstream_wording import forbidden_path_failures


class LightweightAgentGateTests(unittest.TestCase):
    """Keep the retained checks executable and cover their core parsing rules."""

    def test_cli_full_contract_preserves_failure_and_timeout_exits(self) -> None:
        workflow = Path(".github/workflows/cli.yml").read_text(encoding="utf-8")
        names = (
            "Exercise built CLI against task HTTP and local file boundaries",
            "Exercise existing guide HTTP contracts",
            "Exercise existing native guide API callers",
            "Exercise existing native CLI self-service caller",
            "Exercise complete native CLI batch journey",
        )
        scripts = []
        for name in names:
            step = workflow.split("      - name: " + name + "\n", 1)[1].split("\n      - ", 1)[0]
            script = textwrap.dedent(step.split("        run: |\n", 1)[1])
            self.assertIn("--timeout-seconds 300", script)
            self.assertIn("python scripts/run_isolated_tests.py", script)
            self.assertNotIn("|| true", script)
            scripts.append(script)
            for exit_code in (0, 1, 124):
                with self.subTest(step=name, exit_code=exit_code):
                    result = subprocess.run(
                        ["bash", "-e", "-c", f"python() {{ return {exit_code}; }}\n" + script],
                        cwd="backend",
                        env=os.environ | {"RUNNER_TEMP": tempfile.gettempdir()},
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(result.returncode, exit_code, result.stderr)
        self.assertEqual(
            shlex.split(scripts[0].replace("\\\n", ""), comments=True),
            [
                "set", "-euo", "pipefail", "python", "scripts/run_isolated_tests.py",
                "--metadata-json", "${RUNNER_TEMP}/workstream-cli-isolation.json",
                "--timeout-seconds", "300", "--", "python", "-m", "pytest", "-q",
                "../cli/tests/integration",
                "--ignore-glob=../cli/tests/integration/*_public_api.py",
                "--ignore-glob=../cli/tests/integration/test_guide*.py",
                "--ignore=../cli/tests/integration/test_public_self_service.py",
            ],
        )
        self.assertNotIn("continue-on-error", workflow)
        self.assertIn("timeout-minutes: 15", workflow)
        self.assertIn("--ignore=../cli/tests/integration/test_public_self_service.py", scripts[0])
        self.assertIn("test_task_batch_public_api.py", scripts[2])
        self.assertIn("test_public_self_service.py", scripts[3])
        self.assertIn("test_task_batch_public_api.py", scripts[4])

    def test_backend_redis_services_use_the_exact_official_image(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        images = re.findall(r"(?m)^      redis:\n        image: (\S+)$", workflow)
        self.assertEqual(
            images,
            [
                "docker.io/library/redis:7-alpine@sha256:"
                "520775a41a63e77e06c73e35d2fd9cc15921a609516818796b4ecbb813078bc7"
            ]
            * 2,
        )

    def test_markdown_link_target_classification(self) -> None:
        self.assertEqual(local_target("docs/guide.md#start"), "docs/guide.md")
        self.assertEqual(local_target("<docs/a file.md>"), "docs/a file.md")
        self.assertIsNone(local_target("https://example.com"))
        self.assertIsNone(local_target("#local-heading"))

    def test_exact_pre_cutover_records_are_not_rewritten_for_old_links(self) -> None:
        self.assertFalse(
            should_check_links(Path(".commitrail/initiatives/WS-AUTH-001/pre-cutover/STATUS.md"))
        )
        self.assertTrue(should_check_links(Path(".commitrail/initiatives/WS-AUTH-001/OVERVIEW.md")))

    def test_tool_specific_agent_paths_are_rejected(self) -> None:
        failures = forbidden_path_failures([Path(".claude/settings.json"), Path("docs/guide.md")])
        self.assertEqual(len(failures), 1)
        self.assertIn(".claude/settings.json", failures[0])

    def test_stale_wording_pattern_rejects_legacy_name(self) -> None:
        self.assertTrue(
            any(
                pattern.search("task-production control " + "plane")
                for pattern in FORBIDDEN_PATTERNS
            )
        )

    def test_stale_authorization_rejects_noncanonical_api_prefix(self) -> None:
        failures = scan_authorization_text("docs/new-guide.md", "Call /v1/tasks.")
        self.assertIn("docs/new-guide.md:1: NON_CANONICAL_API_PREFIX", failures)

    def test_stale_authorization_allows_exact_compose_worker_service(self) -> None:
        commands = (
            "docker compose --profile backend exec -T worker "
            "celery -A app.workers.celery_app inspect ping",
            "docker compose --profile backend logs -f backend worker beat",
            "Inspect `docker compose --profile backend logs --since 10m worker beat`.",
            "docker compose --profile backend run --rm --no-deps "
            "-e WORKSTREAM_ARTIFACT_STORE_BACKEND=disabled worker python -c 'pass'",
            "docker compose --profile backend kill -s KILL worker",
            "docker compose --profile backend up -d --wait worker",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(scan_authorization_text("docs/new-guide.md", command), [])

    def test_stale_authorization_rejects_human_worker_vocabulary(self) -> None:
        examples = (
            "The worker can approve project work.",
            "# docker compose --profile backend exec -T worker",
            "docker compose --profile backend exec -T backend echo worker",
            "docker compose --profile backend logs --since worker",
            "Use docker compose when the worker approves.",
            "docker compose --profile backend exec -T worker_id echo ok",
        )
        for example in examples:
            with self.subTest(example=example):
                failures = scan_authorization_text("docs/new-guide.md", example)
                self.assertTrue(
                    any(
                        code in failure
                        for failure in failures
                        for code in (
                            "HUMAN_WORKER_VOCABULARY",
                            "HUMAN_WORKER_IDENTIFIER",
                        )
                    )
                )

    def test_stale_artifact_rejects_reached_phase_term(self) -> None:
        failures = scan_artifact_text(
            "README.md", "Use S3" + "ArtifactStore.", "artifact_store_cutover"
        )
        self.assertIn("README.md:1: AMBIGUOUS_S3_ADAPTER_NAME", failures)

    def test_stale_artifact_rejects_legacy_guide_content_identity(self) -> None:
        failures = scan_artifact_text(
            "backend/app/modules/projects/example.py",
            "Caller supplied content_" + "cid.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/modules/projects/example.py:1: LEGACY_GUIDE_CONTENT_CID",
            failures,
        )

    def test_stale_artifact_rejects_legacy_guide_durable_ref(self) -> None:
        failures = scan_artifact_text(
            "backend/app/modules/projects/example.py",
            "Caller supplied durable_" + "ref.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/modules/projects/example.py:1: LEGACY_GUIDE_DURABLE_REF",
            failures,
        )
        interface_failures = scan_artifact_text(
            "backend/app/interfaces/project_agents.py",
            "Caller supplied durable_" + "ref.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/interfaces/project_agents.py:1: LEGACY_GUIDE_DURABLE_REF",
            interface_failures,
        )

    def test_stale_artifact_rejects_legacy_guide_content_hash(self) -> None:
        failures = scan_artifact_text(
            "backend/app/modules/projects/example.py",
            "Caller supplied content_" + "hash.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/modules/projects/example.py:1: LEGACY_GUIDE_CONTENT_HASH",
            failures,
        )
        interface_failures = scan_artifact_text(
            "backend/app/interfaces/project_agents.py",
            "Caller supplied content_" + "hash.",
            "guide_source_cutover",
        )
        self.assertIn(
            "backend/app/interfaces/project_agents.py:1: LEGACY_GUIDE_CONTENT_HASH",
            interface_failures,
        )

    def test_stale_artifact_rejects_unknown_phase(self) -> None:
        with self.assertRaises(ValueError):
            phase_index("unknown")

    def test_backend_uses_distributed_semantic_lanes_and_stable_fan_in(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        agent_gates = Path(".github/workflows/agent-gates.yml").read_text(encoding="utf-8")
        gate_requirements = Path(".github/requirements/agent-gates.txt").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("pull_request_review:", workflow)
        self.assertIn(
            "types: [opened, synchronize, reopened, ready_for_review, converted_to_draft]",
            workflow,
        )
        self.assertIn("cancel-in-progress: true", workflow)
        scope_job = workflow.split("\n  scope:\n", 1)[1].split(
            "\n  minio-image:\n", 1
        )[0]
        self.assertIn("fetch-depth: 0", scope_job)
        self.assertIn("python backend/scripts/select_ci_scope.py", scope_job)
        self.assertIn("BASE_SHA: ${{ github.event.pull_request.base.sha || github.event.before }}", scope_job)
        self.assertIn("PR_DRAFT: ${{ github.event_name == 'pull_request' && github.event.pull_request.draft || false }}", scope_job)
        self.assertIn("lane_matrix: ${{ steps.select.outputs.lane_matrix }}", scope_job)
        self.assertEqual(
            workflow.count(
                "matrix: ${{ fromJSON(needs.scope.outputs.lane_matrix) }}"
            ),
            1,
        )
        self.assertIn(
            "  full-suite:\n    if: >-\n"
            "      ${{ always() && needs.scope.result == 'success' &&\n"
            "          needs.scope.outputs.full_suite == 'true' }}\n"
            "    needs: [scope, auth-boundary-preflight, external-checker-runtime, "
            "lanes, minio-image, cli-public-contract]",
            workflow,
        )
        self.assertIn(
            "  test:\n    if: ${{ always() }}\n"
            "    needs: [scope, auth-boundary-preflight, external-checker-runtime, "
            "lanes, minio-image, cli-public-contract, full-suite]",
            workflow,
        )
        self.assertIn("Require preflight, every semantic lane and CLI public contract", workflow)
        self.assertIn("Require the selected draft scope or complete merge proof", workflow)
        cli_job = workflow.split("\n  cli-public-contract:\n", 1)[1].split(
            "\n  full-suite:\n", 1
        )[0]
        self.assertIn("    uses: ./.github/workflows/cli.yml\n", cli_job)
        self.assertIn("    needs: [scope, minio-image]\n", cli_job)
        self.assertIn("      minio_artifact: ${{ needs.minio-image.outputs.artifact }}\n", cli_job)
        self.assertIn("python -m scripts.merge_test_lane_evidence", workflow)
        self.assertIn("scripts/validate_test_lane_evidence.py", workflow)
        self.assertIn(
            "WORKSTREAM_TEST_MINIO_ENDPOINT: http://127.0.0.1:9000",
            workflow,
        )
        self.assertIn("include-hidden-files: true", workflow)
        self.assertIn("coverage report --precision=2", workflow)
        self.assertNotIn("fail-under", workflow)
        self.assertNotIn("pull_request_review:", agent_gates)
        self.assertNotIn("--require-pr-approval", agent_gates)
        self.assertNotIn("pull-requests:", agent_gates)
        self.assertNotIn("types: [opened, synchronize, reopened, edited]", agent_gates)
        self.assertIn("types: [opened, synchronize, reopened]", agent_gates)
        self.assertIn("group: agent-gates-${{ github.event.pull_request.number }}", agent_gates)
        self.assertIn("cancel-in-progress: true", agent_gates)
        self.assertIn("ref: ${{ github.event.pull_request.head.sha }}", agent_gates)
        self.assertNotIn("check_guide_extractor_dependencies.py", agent_gates)
        self.assertIn("python3 scripts/check_commitrail_records.py", agent_gates)
        self.assertNotIn("python3 scripts/check_chunk_state_sync.py", agent_gates)
        self.assertIn("scripts.test_commitrail_contracts", agent_gates)
        self.assertIn("scripts.test_commitrail_contribution_paths", agent_gates)
        self.assertIn('WORKSTREAM_BASE_SHA: ${{ github.event.pull_request.base.sha }}', agent_gates)
        self.assertNotIn("scripts.test_chunk_state_sync", agent_gates)
        self.assertIn("--require-hashes", agent_gates)
        self.assertIn("-r .github/requirements/agent-gates.txt", agent_gates)
        for package in (
            "attrs",
            "jsonschema",
            "jsonschema-specifications",
            "referencing",
            "rpds-py",
            "typing-extensions",
        ):
            with self.subTest(package=package):
                self.assertRegex(
                    gate_requirements,
                    rf"(?m)^{package}==[^ ]+ \\\n    --hash=sha256:[0-9a-f]{{64}}$",
                )

    def test_minio_source_image_is_built_once_and_shared_without_bypassing_lanes(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        image_job = workflow.split("\n  minio-image:\n", 1)[1].split("\n  auth-boundary-preflight:\n", 1)[0]
        self.assertEqual(workflow.count('docker build --tag "${MINIO_IMAGE}" docker/minio'), 1)
        self.assertNotIn("quay.io/minio", workflow)
        self.assertEqual(
            image_job.count("hashFiles('docker/minio/**', '.github/workflows/backend.yml')"),
            2,
        )
        self.assertIn(
            "key: minio-source-v2-${{ runner.os }}-${{ runner.arch }}-",
            image_job,
        )
        cache_step = image_job.split(
            "      - name: Restore exact source image from trusted cache\n", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn(
            "uses: actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830",
            cache_step,
        )
        self.assertNotIn("github.sha", cache_step)
        self.assertNotIn("restore-keys:", image_job)
        save_step = image_job.split(
            "      - name: Save verified source image to trusted cache\n", 1
        )[1].split("\n      - uses:", 1)[0]
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main' "
            "&& steps.cache.outputs.cache-hit != 'true'",
            save_step,
        )
        self.assertIn(
            "uses: actions/cache/save@0057852bfaa89a56745cba8c7296529d2fc39830",
            save_step,
        )
        self.assertLess(
            image_job.index("      - name: Verify the cached or freshly built provider"),
            image_job.index("      - name: Save verified source image to trusted cache"),
        )
        self.assertIn("minio-source-${GITHUB_SHA}-${GITHUB_RUN_ATTEMPT}", image_job)
        self.assertIn("artifact: ${{ steps.identity.outputs.artifact }}", image_job)
        self.assertIn("sha256sum minio.tar > minio.tar.sha256", image_job)
        self.assertIn("/minio/health/live", image_job)
        self.assertIn("if-no-files-found: error", image_job)
        self.assertNotIn("continue-on-error", image_job)
        for name, end in (("lanes", "cli-public-contract"), ("full-suite", "test")):
            job = workflow.split(f"\n  {name}:\n", 1)[1]
            if end:
                job = job.split(f"\n  {end}:\n", 1)[0]
            self.assertIn("name: ${{ needs.minio-image.outputs.artifact }}", job)
            self.assertIn("sha256sum --check minio.tar.sha256", job)
            self.assertIn('docker load --input "${RUNNER_TEMP}/minio-image/minio.tar"', job)
            self.assertIn('"${MINIO_IMAGE}" server /data --address :9000', job)

    def test_backend_uv_cache_keeps_fresh_frozen_installs_and_exact_inputs(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")

        key = (
            "backend-uv-v1-${{ runner.os }}-${{ runner.arch }}-py312-"
            "${{ hashFiles('backend/uv.lock', '.github/workflows/backend.yml') }}"
        )
        self.assertEqual(workflow.count("Restore exact backend uv downloads from trusted cache"), 3)
        self.assertEqual(workflow.count(f"key: {key}"), 4)
        self.assertEqual(
            workflow.count(
                "uses: actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830"
            ),
            4,
        )
        self.assertEqual(
            workflow.count("uses: actions/cache/save@0057852bfaa89a56745cba8c7296529d2fc39830"),
            2,
        )
        tool_install = 'python -m pip install "uv==0.10.7"'
        frozen_install = "uv sync --frozen --all-extras"
        cache_env = 'echo "UV_CACHE_DIR=${RUNNER_TEMP}/backend-uv-cache" >> "${GITHUB_ENV}"'
        job_blocks = (
            workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split("\n  lanes:\n", 1)[0],
            workflow.split("\n  lanes:\n", 1)[1].split("\n  cli-public-contract:\n", 1)[0],
            workflow.split("\n  full-suite:\n", 1)[1].split("\n  test:\n", 1)[0],
        )
        for job in job_blocks:
            self.assertEqual(job.count("Restore exact backend uv downloads from trusted cache"), 1)
            self.assertEqual(job.count(tool_install), 1)
            self.assertEqual(job.count(frozen_install), 1)
            self.assertEqual(job.count(cache_env), 1)
            self.assertLess(job.index("Restore exact backend uv downloads"), job.index(cache_env))
            self.assertLess(job.index(cache_env), job.index(tool_install))
            self.assertLess(job.index(tool_install), job.index(frozen_install))
        self.assertEqual(workflow.count(tool_install), 3)
        self.assertEqual(workflow.count(frozen_install), 3)
        self.assertEqual(workflow.count(cache_env), 3)
        self.assertNotIn('python -m pip install -e ".[dev,agents]"', workflow)
        root_env = workflow.split("\nenv:\n", 1)[1].split("\njobs:\n", 1)[0]
        self.assertNotIn("runner.", root_env)
        uv_save = workflow.split(
            "      - name: Save verified backend uv downloads to trusted cache\n", 1
        )[1].split("\n  lanes:\n", 1)[0]
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main' "
            "&& steps.uv-cache.outputs.cache-hit != 'true'",
            uv_save,
        )
        preflight = workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split(
            "\n  lanes:\n", 1
        )[0]
        self.assertLess(
            preflight.index("      - name: Validate module, AUTH, and test boundaries"),
            preflight.index("      - name: Save verified backend uv downloads to trusted cache"),
        )
        self.assertNotIn("restore-keys:", workflow)
        self.assertNotIn(".venv", workflow)

    def test_backend_python_commands_stay_in_the_frozen_uv_environment(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        preflight = workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split(
            "\n  external-checker-runtime:\n", 1
        )[0]
        lanes = workflow.split("\n  lanes:\n", 1)[1].split(
            "\n  cli-public-contract:\n", 1
        )[0]
        full_suite = workflow.split("\n  full-suite:\n", 1)[1].split(
            "\n  test:\n", 1
        )[0]

        for command in (
            "uv run --frozen ruff check",
            "uv run --frozen python -m scripts.module_boundaries validate",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --frozen python -m pytest -q",
            "uv run --frozen python -m scripts.authorization_boundary validate",
            "uv run --frozen python -m scripts.test_structure_boundary validate",
            "uv run --frozen python -m scripts.behavior_ownership validate",
            "uv run --frozen docstr-coverage --config .docstr.yaml",
        ):
            self.assertIn(command, preflight)
        self.assertIn("uv run --frozen python scripts/run_test_lanes.py", lanes)
        for command in (
            "uv run --frozen python -m scripts.merge_test_lane_evidence",
            "uv run --frozen python scripts/validate_test_lane_evidence.py",
            "uv run --frozen coverage combine",
            "uv run --frozen python scripts/run_isolated_tests.py",
            "-- uv run --frozen python scripts/api_contract_e2e.py",
            "uv run --frozen coverage report --precision=2",
            "uv run --frozen coverage json",
            "uv run --frozen python - <<'PY'",
        ):
            self.assertIn(command, full_suite)

        for escaped in (
            "\n          ruff check ",
            "\n          python -m scripts.module_boundaries",
            "\n          PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest",
            "\n          python scripts/run_test_lanes.py",
            "\n          python -m scripts.merge_test_lane_evidence",
            "\n          python scripts/validate_test_lane_evidence.py",
            "\n          coverage combine",
            "\n          python scripts/run_isolated_tests.py",
            "\n          -- python scripts/api_contract_e2e.py",
            "\n        run: coverage report",
            "\n          coverage json",
            "\n          python - <<'PY'",
        ):
            self.assertNotIn(escaped, workflow)

    def test_source_wide_static_checks_run_once_outside_semantic_lanes(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        preflight = workflow.split("\n  auth-boundary-preflight:\n", 1)[1].split(
            "\n  external-checker-runtime:\n", 1
        )[0]
        lanes = workflow.split("\n  lanes:\n", 1)[1].split(
            "\n  cli-public-contract:\n", 1
        )[0]

        self.assertEqual(workflow.count("ruff check app tests scripts"), 1)
        self.assertEqual(workflow.count("docstr-coverage --config .docstr.yaml"), 1)
        self.assertIn("Lint and check docstring coverage once", preflight)
        self.assertNotIn("ruff check app tests scripts", lanes)
        self.assertNotIn("docstr-coverage", lanes)

    def test_parallel_preflight_and_lanes_fail_closed_at_fan_in(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        lanes = workflow.split("\n  lanes:\n", 1)[1].split(
            "\n  cli-public-contract:\n", 1
        )[0]
        self.assertRegex(lanes, r"(?m)^    needs: \[scope, minio-image\]$")
        self.assertNotIn("needs: auth-boundary-preflight", lanes)
        step = workflow.split(
            "      - name: Require preflight, every semantic lane and CLI public contract\n", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("if: ${{ always() }}", step)
        self.assertIn("PREFLIGHT_RESULT: ${{ needs.auth-boundary-preflight.result }}", step)
        self.assertIn(
            "EXTERNAL_CHECKER_RESULT: ${{ needs.external-checker-runtime.result }}",
            step,
        )
        self.assertIn("LANES_RESULT: ${{ needs.lanes.result }}", step)
        self.assertIn("CLI_RESULT: ${{ needs.cli-public-contract.result }}", step)
        guard = re.search(r"(?m)^        run: (.+)$", step)
        self.assertIsNotNone(guard)
        for preflight in ("success", "failure", "cancelled", "skipped", "", "unknown"):
            for lanes_result in ("success", "failure", "cancelled", "skipped", "", "unknown"):
                with self.subTest(preflight=preflight, lanes=lanes_result):
                    result = subprocess.run(
                        ["bash", "-e", "-c", guard[1]],
                        env={
                            "PREFLIGHT_RESULT": preflight,
                            "EXTERNAL_CHECKER_RESULT": "success",
                            "LANES_RESULT": lanes_result,
                            "CLI_RESULT": "success",
                        },
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode == 0,
                        preflight == lanes_result == "success",
                    )
        for external_checker in (
            "failure",
            "cancelled",
            "skipped",
            "",
            "unknown",
        ):
            with self.subTest(external_checker=external_checker):
                result = subprocess.run(
                    ["bash", "-e", "-c", guard[1]],
                    env={
                        "PREFLIGHT_RESULT": "success",
                        "EXTERNAL_CHECKER_RESULT": external_checker,
                        "LANES_RESULT": "success",
                        "CLI_RESULT": "success",
                    },
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
        for cli_result in ("failure", "cancelled", "skipped", "", "unknown"):
            with self.subTest(cli=cli_result):
                result = subprocess.run(
                    ["bash", "-e", "-c", guard[1]],
                    env={
                        "PREFLIGHT_RESULT": "success",
                        "EXTERNAL_CHECKER_RESULT": "success",
                        "LANES_RESULT": "success",
                        "CLI_RESULT": cli_result,
                    },
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)

    def test_required_backend_status_accepts_only_the_exact_selected_scope(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        step = workflow.split(
            "      - name: Require the selected draft scope or complete merge proof\n", 1
        )[1]
        guard = textwrap.dedent(step.split("        run: |\n", 1)[1])

        def run_guard(**values: str) -> subprocess.CompletedProcess[bytes]:
            defaults = {
                "SCOPE_RESULT": "success",
                "FULL_SUITE": "false",
                "PREFLIGHT_EXPECTED": "false",
                "PREFLIGHT_RESULT": "skipped",
                "EXTERNAL_EXPECTED": "false",
                "EXTERNAL_RESULT": "skipped",
                "LANES_EXPECTED": "false",
                "LANES_RESULT": "skipped",
                "MINIO_EXPECTED": "false",
                "MINIO_RESULT": "skipped",
                "CLI_EXPECTED": "false",
                "CLI_RESULT": "skipped",
                "FULL_RESULT": "skipped",
            }
            return subprocess.run(
                ["bash", "-e", "-c", guard],
                env=defaults | values,
                capture_output=True,
                check=False,
            )

        self.assertEqual(run_guard().returncode, 0)
        self.assertEqual(
            run_guard(
                LANES_EXPECTED="true",
                LANES_RESULT="success",
                MINIO_EXPECTED="true",
                MINIO_RESULT="success",
            ).returncode,
            0,
        )
        self.assertEqual(
            run_guard(FULL_SUITE="true", FULL_RESULT="success").returncode,
            0,
        )
        component_pairs = (
            ("PREFLIGHT_EXPECTED", "PREFLIGHT_RESULT"),
            ("EXTERNAL_EXPECTED", "EXTERNAL_RESULT"),
            ("LANES_EXPECTED", "LANES_RESULT"),
            ("MINIO_EXPECTED", "MINIO_RESULT"),
            ("CLI_EXPECTED", "CLI_RESULT"),
        )
        for expected_key, result_key in component_pairs:
            with self.subTest(component=result_key, outcome="success"):
                self.assertEqual(
                    run_guard(
                        **{expected_key: "true", result_key: "success"}
                    ).returncode,
                    0,
                )
            with self.subTest(component=result_key, outcome="unexpected_success"):
                self.assertNotEqual(
                    run_guard(**{result_key: "success"}).returncode,
                    0,
                )
            for bad_result in ("failure", "cancelled", "skipped", "", "unknown"):
                with self.subTest(component=result_key, outcome=bad_result):
                    self.assertNotEqual(
                        run_guard(
                            **{expected_key: "true", result_key: bad_result}
                        ).returncode,
                        0,
                    )
        for values in (
            {"SCOPE_RESULT": "failure"},
            {"LANES_EXPECTED": "true", "LANES_RESULT": "skipped"},
            {"LANES_EXPECTED": "false", "LANES_RESULT": "success"},
            {"MINIO_EXPECTED": "true", "MINIO_RESULT": "failure"},
            {"FULL_SUITE": "true", "FULL_RESULT": "failure"},
            {"FULL_RESULT": "success"},
        ):
            with self.subTest(values=values):
                self.assertNotEqual(run_guard(**values).returncode, 0)

    def test_postgres_storage_is_bounded_and_disk_contracts_remain(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        lane_service = workflow.split("\n  lanes:\n", 1)[1].split("\n    steps:", 1)[0]
        aggregate_service = workflow.split("\n  full-suite:\n", 1)[1].split(
            "\n    steps:", 1
        )[0]
        self.assertIn(
            "${{ matrix.lane != 'schema_contracts' && "
            "'--tmpfs /var/lib/postgresql/data:rw,nosuid,nodev,noexec,size=2147483648' || '' }}",
            lane_service,
        )
        self.assertNotIn("--tmpfs", aggregate_service)
        self.assertLess(
            workflow.index("- name: Verify PostgreSQL CI storage and write settings"),
            workflow.index("- name: Execute semantic lane"),
        )

    def test_postgres_storage_guard_rejects_wrong_mounts_and_write_settings(self) -> None:
        workflow = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")
        step = workflow.split(
            "      - name: Verify PostgreSQL CI storage and write settings\n", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("POSTGRES_CONTAINER: ${{ job.services.postgres.id }}", step)
        self.assertIn(
            "EXPECTED_PG_STORAGE: ${{ matrix.lane == 'schema_contracts' && 'disk' || 'tmpfs' }}",
            step,
        )
        guard = textwrap.dedent(step.split("        run: |\n", 1)[1])
        settings = "on|on|on|/var/lib/postgresql/data"
        memory = "tmpfs 524288 4096"
        disk = "ext2/ext3 524288 4096"
        cases = [
            ("tmpfs", memory, settings, "0", True),
            ("disk", disk, settings, "0", True),
            ("tmpfs", disk, settings, "0", False),
            ("disk", memory, settings, "0", False),
            ("tmpfs", "tmpfs 524287 4096", settings, "0", False),
            ("tmpfs", "tmpfs 524289 4096", settings, "0", False),
            ("tmpfs", "", settings, "0", False),
            ("tmpfs", memory, settings.replace("/data", "/elsewhere"), "0", False),
            ("unknown", memory, settings, "0", False),
            ("tmpfs", memory, settings, "1", False),
        ]
        for index in range(3):
            values = settings.split("|")
            values[index] = "off"
            cases.append(("tmpfs", memory, "|".join(values), "0", False))
        with tempfile.TemporaryDirectory() as directory:
            docker = Path(directory) / "docker"
            docker.write_text(
                '#!/bin/sh\n[ "$TEST_DOCKER_STATUS" = 0 ] || exit 1\n'
                '[ "$1" = exec ] && [ "$2" = probe ] || exit 2\n'
                'case "$3" in\nstat) printf "%s\\n" "$TEST_STAT";;\n'
                'psql) printf "%s\\n" "$TEST_SETTINGS";;\n*) exit 2;;\nesac\n',
                encoding="utf-8",
            )
            docker.chmod(0o755)
            for mode, stat, configuration, status, allowed in cases:
                with self.subTest(mode=mode, stat=stat, configuration=configuration, status=status):
                    result = subprocess.run(
                        ["bash", "-e", "-c", guard],
                        env={
                            "PATH": directory + os.pathsep + os.defpath,
                            "POSTGRES_CONTAINER": "probe",
                            "EXPECTED_PG_STORAGE": mode,
                            "TEST_STAT": stat,
                            "TEST_SETTINGS": configuration,
                            "TEST_DOCKER_STATUS": status,
                        },
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode == 0, allowed, result.stderr.decode())

    def test_retired_behavior_mutation_gate_stays_out_of_required_ci(self) -> None:
        backend = Path(".github/workflows/backend.yml").read_text(encoding="utf-8")

        self.assertFalse(Path(".github/workflows/mutation-pilot.yml").exists())
        self.assertNotIn("mutation-pilot", backend)

if __name__ == "__main__":
    unittest.main()
