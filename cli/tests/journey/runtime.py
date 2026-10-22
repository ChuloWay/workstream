"""Owned local Redis, real checker service and prefork workers for the drill."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time


@contextmanager
def durable_runtime(root: Path, directory: Path, environment: dict):
    processes, logs = [], []

    def start(arguments, label):
        log = (directory / (label + ".log")).open("wb")
        logs.append(log)
        process = subprocess.Popen(
            arguments,
            cwd=root / "backend",
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        processes.append(process)
        return process

    scratch = directory / "scratch"
    scratch.mkdir(mode=0o700)
    checker_socket = directory / "checker.sock"
    configuration = json.loads(
        (root / ".local-agent-loop/checker-service.json").read_text()
    )
    configuration.update(
        socket_path=str(checker_socket),
        material_root=str(scratch),
        docker_binary=str(Path(shutil.which("docker")).resolve(strict=True)),
        sandbox_uid=os.getuid(),
        sandbox_gid=os.getgid(),
    )
    config_file = directory / "checker.json"
    config_file.write_text(json.dumps(configuration))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        redis_port = sock.getsockname()[1]
    environment.update(
        WORKSTREAM_CELERY_BROKER_URL=f"redis://127.0.0.1:{redis_port}/0",
        WORKSTREAM_CELERY_RESULT_BACKEND_URL=f"redis://127.0.0.1:{redis_port}/1",
        WORKSTREAM_CELERY_TASK_ALWAYS_EAGER="false",
        WORKSTREAM_ARTIFACT_STORE_BACKEND="s3_compatible",
        WORKSTREAM_ARTIFACT_SCRATCH_ROOT=str(scratch),
        WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT=str(scratch),
        WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET=str(checker_socket),
        WORKSTREAM_ARTIFACT_S3_PROVIDER_PROFILE="minio",
        WORKSTREAM_ARTIFACT_S3_REGION="us-east-1",
        WORKSTREAM_ARTIFACT_S3_ENDPOINT_URL=environment[
            "WORKSTREAM_TEST_MINIO_ENDPOINT"
        ],
        WORKSTREAM_ARTIFACT_S3_BUCKET=environment["WORKSTREAM_TEST_MINIO_BUCKET"],
        WORKSTREAM_ARTIFACT_S3_PRIVATE_PREFIX=environment[
            "WORKSTREAM_TEST_MINIO_PREFIX"
        ],
        WORKSTREAM_ARTIFACT_S3_ADDRESSING_STYLE="path",
        WORKSTREAM_ARTIFACT_S3_CREDENTIAL_MODE="local_static",
        WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID="workstream-minio",
        WORKSTREAM_ARTIFACT_S3_SECRET_ACCESS_KEY="workstream-minio-secret-key",
        WORKSTREAM_ARTIFACT_ADMISSION_DEPLOYMENT_MAXIMUM_BYTES="268435456",
        WORKSTREAM_ARTIFACT_ADMISSION_PROJECT_MAXIMUM_BYTES="134217728",
        WORKSTREAM_ARTIFACT_ADMISSION_PRODUCER_MAXIMUM_BYTES="67108864",
        WORKSTREAM_ARTIFACT_ADMISSION_TASK_MAXIMUM_BYTES="67108864",
        WORKSTREAM_ARTIFACT_PENDING_WORK_SCAN_INTERVAL_SECONDS="2",
    )
    try:
        redis = start(
            [
                shutil.which("redis-server"),
                "--bind",
                "127.0.0.1",
                "--port",
                str(redis_port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--dir",
                str(directory),
            ],
            "redis",
        )
        checker = start(
            [
                os.environ.get(
                    "WORKSTREAM_CLI_JOURNEY_CHECKER_EXECUTABLE",
                    str(
                        root
                        / "external_checkers/target/release/workstream-checker-service"
                    ),
                ),
                str(config_file),
            ],
            "checker",
        )
        deadline = time.monotonic() + 30
        while not checker_socket.exists():
            if (
                checker.poll() is not None
                or redis.poll() is not None
                or time.monotonic() > deadline
            ):
                raise RuntimeError("local checker/Redis startup failed")
            time.sleep(0.1)

        def start_workers():
            # Provision their public identities before scheduling any work.
            start(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "app.workers.celery_app",
                    "worker",
                    "--pool=prefork",
                    "--concurrency=2",
                    "--hostname=cli-journey@localhost",
                    "--loglevel=WARNING",
                ],
                "worker",
            )
            start(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "app.workers.celery_app",
                    "beat",
                    "--schedule",
                    str(directory / "beat-schedule"),
                    "--loglevel=WARNING",
                ],
                "beat",
            )

        yield start_workers
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        for log in logs:
            log.close()
