"""Opt-in destructive recovery proof for an isolated Smol test node only.

Requires authority over the named systemd unit. Never target a shared production
node: this intentionally kills its controller and injects a deletion failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import socket
import struct
import subprocess
import time

from smol_runtime import Proof, canonical, exchange


def wait_until(predicate, description, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(description)


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
