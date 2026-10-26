"""Opt-in destructive recovery proof for an isolated Smol test node only.

Requires authority over the named systemd unit. Never target a shared production
node: this intentionally kills its controller and injects a deletion failure.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import stat
import struct
import subprocess
import time
import zipfile

from smol_runtime import Proof, canonical, exchange


def wait_until(predicate, description, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(description)


class NestedTrialRecovery:
    """Three opt-in owner failures using the composition's real trial custody."""

    CASES = {"caller_disconnect", "child_death", "controller_death"}
    MARKER = b"workstream-owned-nested-trial-ready-v1\n"

    def __init__(self, case):
        if case not in self.CASES:
            raise ValueError("unsupported nested recovery case")
        self.case = case
        self.completed = False
        self.replacement = None
        self.killed_controller = None

    def archive_factory(self, original):
        def archive(evidence_path, project_id):
            # Only this recovery submission changes. A finite wait gives the
            # observer a deterministic reached-workload boundary, then fails
            # closed if no fault is injected. No production image is modified.
            data = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(original(evidence_path, project_id))) as source:
                with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as target:
                    for entry in source.infolist():
                        body = source.read(entry.filename)
                        if entry.filename == "tools/qualification-status":
                            body = (
                                b"#!/bin/sh\nset -eu\n"
                                b"grep -Eq '^Seccomp:[[:space:]]+2$' /proc/self/status\n"
                                b"printf 'workstream-owned-nested-trial-ready-v1\\n' "
                                b"> /workspace/.trial-recovery-ready\n"
                                b"sleep 20\nexit 77\n"
                            )
                        target.writestr(entry, body)
            return data.getvalue()
        return archive

    def runtime(self, home, *arguments, check=True):
        return subprocess.run(
            [self.config["smol"]["binary"], *arguments], check=check,
            capture_output=True, timeout=5,
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        )

    @staticmethod
    def private_directory(path):
        identity = path.lstat()
        assert path.resolve() == path and stat.S_ISDIR(identity.st_mode)
        assert stat.S_IMODE(identity.st_mode) == 0o700
        assert (identity.st_uid, identity.st_gid) == (os.geteuid(), os.getegid())
        return {"device": identity.st_dev, "inode": identity.st_ino}

    @staticmethod
    def process_identity(pid, executable):
        assert type(pid) is int and pid > 1
        process = Path("/proc") / str(pid)
        assert (process / "exe").resolve(strict=True) == executable
        assert process.stat().st_uid == os.geteuid()
        # /proc stat's parenthesized comm may contain spaces or parentheses.
        start = int((process / "stat").read_text().rpartition(") ")[2].split()[19])
        return {"pid": pid, "start_ticks": start, "executable": str(executable)}

    def marker(self):
        if self.execution.done():
            raise AssertionError("execution ended before nested workload marker")
        owner = (self.service_root / ".workstream-checker-owner").read_text()
        assert len(owner) == 64 and all(c in "0123456789abcdef" for c in owner)
        leases = sorted(self.leases.iterdir())
        assert len(leases) <= 2, "unexpected additional active owner"
        for path in leases:
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                continue  # A prior ordinary/child operation finished between polls.
            with os.fdopen(descriptor, "rb") as source:
                identity = os.fstat(source.fileno())
                assert stat.S_ISREG(identity.st_mode) and identity.st_nlink == 1
                assert stat.S_IMODE(identity.st_mode) == 0o600
                assert (identity.st_uid, identity.st_gid) == (os.geteuid(), os.getegid())
                raw = source.read(65537)
                assert len(raw) <= 65536
            lease = json.loads(raw)
            assert lease["owner"] == owner and lease["root"] == str(self.leases)
            if lease["private_home_root"] is None:
                continue
            assert lease["private_home_root"] == str(self.child_root)
            name = lease["name"]
            assert len(name) == 35 and name.startswith("ws-")
            assert all(c in "0123456789abcdef" for c in name[3:])
            assert path == self.leases / (name + ".json")
            home = self.child_root / (name + ".home")
            assert lease["runtime"]["home"] == str(home)
            for key in ("binary", "binary_sha256", "guest_binary", "guest_sha256", "cgroup_root"):
                assert lease["runtime"][key] == self.config["smol"][key]
            try:
                home_identity = self.private_directory(home)
                rows = json.loads(self.runtime(home, "machine", "ls", "--json").stdout)
            except (FileNotFoundError, subprocess.CalledProcessError):
                if not path.exists():
                    continue  # Only an already-removed exact lease may disappear.
                raise
            assert len(rows) == 1 and rows[0]["name"] == name
            machine = rows[0]
            assert machine["labels"]["workstream.external-checker-owner"] == owner
            assert machine["network"] is False
            if machine["state"] != "running":
                continue
            # This is trusted observation of our exact VM, never an untrusted
            # management request. The marker is read through the live workload's
            # chroot, so launcher setup or mere VM startup cannot satisfy it.
            script = (
                "for p in $(cat /sys/fs/cgroup/workstream-trial/workload/cgroup.procs 2>/dev/null); do "
                "grep -Eq '^Seccomp:[[:space:]]+2$' /proc/$p/status 2>/dev/null || continue; "
                "f=/proc/$p/root/workspace/.trial-recovery-ready; "
                "test -r $f || continue; "
                "test \"$(cat $f)\" = workstream-owned-nested-trial-ready-v1 || exit 41; "
                "printf 'nested-workload-ready:%s\\n' $p; exit 0; done; exit 43"
            )
            observed = self.runtime(
                home, "machine", "exec", "--name", name, "--user", "0:0", "--",
                "/bin/sh", "-c", script, check=False,
            )
            if observed.returncode:
                continue
            assert observed.stdout.startswith(b"nested-workload-ready:")
            assert observed.stdout.endswith(b"\n") and not observed.stderr
            workload_pid = int(observed.stdout.strip().split(b":")[1])
            vmm = self.process_identity(machine["pid"], Path(self.config["smol"]["binary"]))
            group = self.groups / name
            assert (Path("/proc") / str(vmm["pid"]) / "cgroup").read_text().strip() == (
                "0::" + str(group).removeprefix("/sys/fs/cgroup")
            )
            self.reached = {
                "owner": owner, "lease_name": name,
                "lease_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "lease_device": identity.st_dev, "lease_inode": identity.st_ino,
                "child_home": str(home), "child_home_identity": home_identity,
                "vmm": vmm, "workload_pid_in_guest": workload_pid,
                "marker_sha256": "sha256:" + hashlib.sha256(self.MARKER).hexdigest(),
                "workload_seccomp_mode": 2,
            }
            return True
        return False

    def physical_clean(self):
        return (
            not list(self.leases.iterdir())
            and not list(self.groups.glob("ws-*"))
            and not list(self.child_root.glob("ws-*.home"))
            and not list((Path(self.config["smol"]["home"]) / ".cache/smolvm/vms").glob("*"))
        )

    async def exercise(self, *, executor, harness, controller, service_binary,
                       config_path, config, service_log, intake, observations, creates):
        from sqlalchemy import select
        from app.interfaces.trusted_submission_intake import TrustedIntakePreparation
        from app.modules.artifacts.api.submission_archive import SubmissionArchiveLimits
        from app.modules.artifacts.models import ArtifactBinding, ArtifactPutAttempt
        from app.modules.checkers.models import CheckerTrialEvidence
        from app.modules.model_usage.models import ModelUsageEffect

        self.config = config
        self.service_root = Path(config["socket_path"]).parent
        self.leases = self.service_root / "smol-leases"
        self.groups = Path(config["smol"]["cgroup_root"])
        self.child_root = Path(config["trial_runtime"]["child_home_root"])
        initial_child_identity = self.private_directory(self.child_root)
        controller_identity = self.process_identity(controller.pid, service_binary)
        self.controller = controller
        self.controller_identity = controller_identity
        self.execution = asyncio.create_task(executor.evaluate_post_submission(harness.request))
        result = None
        try:
            await asyncio.to_thread(wait_until, self.marker, "nested workload marker missing", 90)
            if self.case == "caller_disconnect":
                self.execution.cancel()  # Adapter finally closes its exact request socket.
            elif self.case == "child_death":
                victim = self.reached["vmm"]
                assert self.process_identity(victim["pid"], Path(victim["executable"])) == victim
                os.kill(victim["pid"], signal.SIGKILL)
            else:
                assert self.process_identity(controller.pid, service_binary) == controller_identity
                self.killed_controller = controller.pid
                os.kill(controller.pid, signal.SIGKILL)
            done, _ = await asyncio.wait({self.execution}, timeout=45)
            if not done:
                self.execution.cancel()
                await asyncio.to_thread(self.stop_owned_controller)
                await asyncio.wait({self.execution}, timeout=15)
                raise AssertionError("execution did not settle within recovery deadline")
            try:
                result = self.execution.result()
            except asyncio.CancelledError:
                assert self.case == "caller_disconnect"
            if result is not None:
                assert result.outcome != "completed", "fault produced a completed work verdict"
            await asyncio.to_thread(wait_until, self.physical_clean, "nested recovery retained physical resources", 30)
            if self.case == "controller_death":
                assert controller.wait(timeout=5) == -signal.SIGKILL
                self.replacement = subprocess.Popen(
                    [str(service_binary), str(config_path)], stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=service_log, text=True,
                )
                await asyncio.to_thread(wait_until, lambda: self.ready(), "restart did not reconcile", 30)
            else:
                assert controller.poll() is None
                assert self.process_identity(controller.pid, service_binary) == controller_identity

            # Two simultaneous real preparations fill this node's two slots.
            # A health response alone would not prove admission capacity reuse.
            assert config["smol"]["maximum_parallel"] == 2
            preparation = TrustedIntakePreparation(
                phase="post_submit", policy_sha256="sha256:" + "a" * 64,
                limits=SubmissionArchiveLimits(maximum_inspection_seconds=30), deadline_ms=30000,
            )
            sessions = []
            try:
                prepared = await asyncio.gather(
                    intake.prepare(preparation), intake.prepare(preparation), return_exceptions=True,
                )
                sessions = [session for session in prepared if not isinstance(session, BaseException)]
                assert len(sessions) == 2, "recovery did not release both admission slots"
                assert len(list(self.leases.iterdir())) == 2
            finally:
                await asyncio.gather(*(session.close() for session in sessions))
            await asyncio.to_thread(wait_until, self.physical_clean, "capacity reuse retained resources", 30)
            assert self.private_directory(self.child_root) == initial_child_identity
            assert not [item for item in observations if "receipt" in item]
            assert len(creates) == 1, "fault caused additional controlled model calls"
            async with harness.factory() as session:
                evidence = tuple(await session.scalars(select(CheckerTrialEvidence)))
                bindings = tuple(await session.scalars(select(ArtifactBinding).where(
                    ArtifactBinding.resource_type == "checker_trial_evidence"
                )))
                puts = tuple(await session.scalars(select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.checker_trial_evidence_id.is_not(None)
                )))
                effects = tuple(await session.scalars(select(ModelUsageEffect)))
                # Reservation is an authorized durable address, not a receipt.
                # Execution failure must never commit content or start ART I/O.
                assert len(evidence) == 1 and evidence[0].content_sha256 is None
                assert not bindings and not puts
                assert len(effects) == 1 and effects[0].state == "completed"
                effect_summary = [{"effect_id": item.id, "state": item.state,
                                   "settled_nanodollars": item.settled_nanodollars} for item in effects]
            summary = {
                "schema_version": "workstream.nested_trial_recovery.v1", "case": self.case,
                "provider_mode": "controlled", "real_provider_calls": 0,
                "controller_before": controller_identity, "reached": self.reached,
                "result_outcome": None if result is None else result.outcome,
                "trial_receipts": 0, "trial_artifact_bindings": 0,
                "reserved_trial_addresses": 1, "trial_artifact_put_attempts": 0,
                "model_effects": effect_summary, "capacity_reuse_simultaneous_intakes": 2,
                "physical_cleanup_confirmed": True, "child_root_identity_unchanged": True,
                "controller_restarted": self.replacement is not None,
            }
            path = Path(os.environ["WORKSTREAM_TS_SMOL_ROOT"]) / "recovery-summary.json"
            path.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
            path.chmod(0o400)
            self.completed = True
        finally:
            if not self.execution.done():
                self.execution.cancel()
                done, _ = await asyncio.wait({self.execution}, timeout=5)
                if not done:
                    await asyncio.to_thread(self.stop_owned_controller)
                    done, _ = await asyncio.wait({self.execution}, timeout=15)
                    assert done, "task did not drain after exact-owned controller teardown"

    def stop_owned_controller(self):
        if self.controller.poll() is None:
            expected = self.controller_identity
            assert self.process_identity(expected["pid"], Path(expected["executable"])) == expected
            self.controller.terminate()
            try:
                self.controller.wait(timeout=5)
            except subprocess.TimeoutExpired:
                assert self.process_identity(expected["pid"], Path(expected["executable"])) == expected
                self.controller.kill()
                self.controller.wait(timeout=5)

    def ready(self):
        try:
            return exchange(self.config["socket_path"], {
                "protocol_version": "external_checker_service.v1", "operation": "health",
            })["status"] == "ready"
        except (OSError, EOFError):
            return False

    def expected_controller_exit(self, controller):
        return self.killed_controller == controller.pid and controller.returncode == -signal.SIGKILL

    def close(self):
        if self.replacement is not None and self.replacement.poll() is None:
            self.replacement.terminate()
            try:
                self.replacement.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.replacement.kill()
                self.replacement.wait(timeout=15)


class Recovery:
    def __init__(self, config_path, fixtures, unit):
        self.path = config_path
        self.original = config_path.read_bytes()
        self.config = json.loads(self.original)
        self.unit = unit
        self.proof = Proof(self.config, fixtures)
        self.image = next(c for c in self.config['cache'] if c['repository'] == 'workstream-test/smol-python')
        self.leases = Path(self.config['socket_path']).parent / 'smol-leases'
        self.groups = Path(self.config['smol']['cgroup_root'])
        self.foreign = 'smol-recovery-foreign-control'
        self.foreign_process = None
        self.connections = []
        self.disks = set()
        self.flag = config_path.parent / 'recovery-delete-fault'
        self.wrapper = config_path.parent / 'recovery-smol-wrapper'
        self.trace = config_path.parent / 'recovery-runtime-trace.jsonl'
        self.mode = config_path.parent / 'recovery-prepare-failures'

    def runtime(self, *args):
        s = self.config['smol']
        return subprocess.run([s['binary'], *args], check=True, capture_output=True, text=True,
                              timeout=15, env={'HOME': s['home'], 'PATH': '/usr/bin:/bin'})

    def rows(self):
        return json.loads(self.runtime('machine', 'ls', '--json').stdout)

    def owned(self):
        owner = (self.leases.parent / '.workstream-checker-owner').read_text().strip()
        rows = [r for r in self.rows() if r['labels'].get('workstream.external-checker-owner') == owner]
        for row in rows:
            name_hash = hashlib.sha256(row['name'].encode()).hexdigest()[:16]
            self.disks.add(Path(self.config['smol']['home']) / '.cache/smolvm/vms' / name_hash)
        return rows

    def ready(self):
        try:
            result = exchange(self.config['socket_path'],
                              {'protocol_version': 'external_checker_service.v1', 'operation': 'health'})
            return result['status'] == 'ready'
        except (OSError, EOFError):
            return False

    def clean(self):
        return (not list(self.leases.iterdir()) and not self.owned()
                and not any(path.exists() for path in self.disks)
                and not [p for p in self.groups.iterdir() if p.is_dir() and p.name.startswith('ws-')])

    def start(self):
        envelope = self.proof.request(self.image, 'pre_submit', 'sleep', deadline_ms=30000)
        connection = socket.socket(socket.AF_UNIX)
        connection.settimeout(3)
        connection.connect(self.config['socket_path'])
        self.connections.append(connection)
        raw = canonical(envelope)
        connection.sendall(struct.pack('>I', len(raw)) + raw)
        return connection

    def running(self, count):
        return len([r for r in self.owned() if r['state'] == 'running']) == count

    def disconnect(self):
        for connection in self.connections:
            connection.close()
        self.connections.clear()

    def report(self, case):
        assert any(r['name'] == self.foreign for r in self.rows()), 'foreign VM deleted'
        assert self.foreign_process.poll() is None, 'foreign cgroup process killed'
        assert (self.groups / self.foreign).exists(), 'foreign cgroup deleted'
        print(json.dumps({'case': case, 'cleanup': 'confirmed', 'foreign_resources': 'preserved'}), flush=True)

    def restart(self):
        subprocess.run(['sudo', 'systemctl', 'reset-failed', self.unit], check=True, timeout=15)
        subprocess.run(['sudo', 'systemctl', 'restart', self.unit], check=True, timeout=30)
        wait_until(self.ready, 'node failed to become ready')

    def retry_proof(self):
        for remaining, expected_creates, case in (
            (1, 2, 'retry_after_confirmed_cleanup'),
            (-1, 3, 'preparation_retry_limit'),
            (0, 1, 'launched_deadline_never_retried'),
        ):
            self.trace.write_text('')
            self.mode.write_text(str(remaining))
            if remaining == -1:
                envelope = self.proof.request(self.image, 'pre_submit', 'pass')
                response = exchange(self.config['socket_path'], envelope)
                assert response['result']['request_digest'] == envelope['request']['request_digest']
                assert response['result']['outcome'] == 'infrastructure_failed'
                assert response['result']['infrastructure_failure_code'] == 'implementation_unavailable'
                assert response['isolation'] is None
            elif remaining:
                self.proof.execute(self.image, 'pre_submit', 'pass')
            else:
                self.proof.execute(self.image, 'pre_submit', 'sleep',
                                   expected='deadline_exceeded', deadline_ms=5000)
            wait_until(self.clean, 'retry test leaked resources')
            events = [json.loads(line) for line in self.trace.read_text().splitlines()]
            creates = [e for e in events if e['operation'] == 'create']
            executions = [e for e in events if e['operation'] == 'exec']
            assert len(creates) == expected_creates, events
            assert len({e['name'] for e in creates}) == expected_creates, events
            assert all(e['prior_resources'] == [] for e in creates), events
            assert len(executions) == (0 if remaining == -1 else 1), events
            assert len([e for e in events if e['operation'] == 'start']) == expected_creates, events
            assert len([e for e in events if e['operation'] == 'delete']) == expected_creates, events
            self.report(case)
        self.mode.write_text('0')

    def run(self):
        assert self.clean() and self.ready(), 'isolated node must start drained and ready'
        self.runtime('machine', 'create', '--name', self.foreign, '--image', self.image['smol']['archive'],
                     '--label', 'workstream.external-checker-owner=foreign-control', '--mem', '256', '--storage', '1')
        # The separate process in a foreign sibling cgroup proves restart cleanup
        # does not infer ownership merely from membership under the delegated root.
        group = self.groups / self.foreign
        group.mkdir()
        script = 'echo $$ > ' + shlex.quote(str(group / 'cgroup.procs')) + '; exec sleep 600'
        self.foreign_process = subprocess.Popen(['sudo', 'sh', '-c', script])
        wait_until(lambda: 'populated 1' in (group / 'cgroup.events').read_text(), 'foreign control failed')
        try:
            self.start()
            wait_until(lambda: self.running(1), 'first VM never started')
            self.disconnect()
            wait_until(self.clean, 'disconnect leaked resources', timeout=15)
            self.report('disconnect_cleanup')

            for _ in range(self.config['smol']['maximum_parallel']):
                self.start()
            wait_until(lambda: self.running(self.config['smol']['maximum_parallel']), 'VMs did not overlap')
            try:
                extra = self.start()
                assert extra.recv(1) == b'', 'capacity overflow was accepted'
            except (ConnectionResetError, BrokenPipeError):
                pass
            assert len(self.owned()) == self.config['smol']['maximum_parallel']
            self.disconnect()
            wait_until(self.clean, 'capacity test leaked resources', timeout=15)
            self.report('concurrent_capacity_rejection')

            self.start()
            wait_until(lambda: self.running(1), 'kill target never started')
            pid = int(subprocess.check_output(['systemctl', 'show', self.unit, '-p', 'MainPID', '--value'], text=True))
            assert Path(f'/proc/{pid}/exe').resolve() == self.path.parent / 'service'
            os.kill(pid, signal.SIGKILL)
            self.disconnect()
            wait_until(self.clean, 'guardian did not clean after controller death', timeout=15)
            wait_until(self.ready, 'startup did not reconcile after controller death')
            self.report('controller_kill_guardian_cleanup')

            # Signed/pinned wrapper is test-only configuration, not a production
            # fault switch. A failed exact-name delete must leave custody durable.
            source = Path(__file__).parent / 'smol_fixture/runtime_wrapper.py'
            self.wrapper.write_bytes(source.read_bytes())
            self.mode.write_text('0')
            self.wrapper.with_suffix('.json').write_text(json.dumps({
                'binary': self.config['smol']['binary'], 'trace': str(self.trace),
                'mode': str(self.mode), 'cgroups': str(self.groups), 'delete_fault': str(self.flag),
            }))
            self.wrapper.chmod(0o700)
            changed = json.loads(self.original)
            changed['smol']['binary'] = str(self.wrapper)
            changed['smol']['binary_sha256'] = 'sha256:' + hashlib.sha256(self.wrapper.read_bytes()).hexdigest()
            self.path.write_text(json.dumps(changed))
            self.restart()
            self.retry_proof()
            self.start()
            wait_until(lambda: self.running(1), 'cleanup fault target never started')
            self.flag.touch()
            self.disconnect()
            wait_until(lambda: not self.ready(), 'cleanup uncertainty left readiness open')
            time.sleep(3)
            assert list(self.leases.iterdir()), 'failed cleanup discarded durable lease'
            assert self.owned(), 'fault did not discriminate failed VM deletion'
            assert not self.ready(), 'restart admitted work with unsettled cleanup'
            self.flag.unlink()
            self.path.write_bytes(self.original)
            self.restart()
            wait_until(self.clean, 'startup failed to recover retained lease')
            self.report('cleanup_uncertainty_closes_readiness')
        finally:
            self.disconnect()
            self.flag.unlink(missing_ok=True)
            self.path.write_bytes(self.original)
            self.restart()
            wait_until(self.clean, 'test cleanup failed')
            self.runtime('machine', 'delete', '--name', self.foreign, '--force')
            (group / 'cgroup.kill').write_text('1')
            self.foreign_process.wait(timeout=10)
            group.rmdir()
            self.wrapper.unlink(missing_ok=True)
            self.wrapper.with_suffix('.json').unlink(missing_ok=True)
            self.mode.unlink(missing_ok=True)
            self.proof.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--fixtures', required=True, type=Path)
    parser.add_argument('--unit', required=True)
    args = parser.parse_args()
    Recovery(args.config, args.fixtures, args.unit).run()


if __name__ == '__main__':
    main()
