"""Opt-in KVM regression: image mount-target links must fail before its command.

Use an isolated runtime HOME and prebuilt clean, /work-link and /tmp-link OCI
archives. This bypasses the controller only to observe guest stdout even when
bootstrap exits nonzero; a failed result alone cannot prove no image code ran.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--guest', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--clean-image', type=Path, required=True)
    parser.add_argument('--work-link-image', type=Path, required=True)
    parser.add_argument('--tmp-link-image', type=Path, required=True)
    args = parser.parse_args()
    args.home.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = 'WORKSTREAM_IMAGE_COMMAND_REACHED'
    job = {'request': json.loads(args.request.read_text()),
           'command': ['/bin/sh', '-c', 'echo ' + marker],
           'environment': ['PATH=/usr/local/bin:/usr/bin:/bin'],
           'working_directory': '/', 'uid': 1000, 'gid': 1000,
           'directories': [], 'files': []}
    raw = json.dumps(job).encode()

    def runtime(*command, **options):
        return subprocess.run([str(args.binary), *command],
                              env={'HOME': str(args.home), 'PATH': '/usr/bin:/bin'},
                              capture_output=True, timeout=60, **options)

    for case, archive in [('clean', args.clean_image), ('work_link', args.work_link_image),
                          ('tmp_link', args.tmp_link_image)]:
        name = 'ws-mount-proof-' + uuid.uuid4().hex
        try:
            runtime('machine', 'create', '--name', name, '--image', str(archive),
                    '--cpus', '1', '--mem', '512', '--storage', '1',
                    '--label', 'workstream-test=guest-mount-targets', check=True)
            runtime('machine', 'start', '--name', name, '--no-workload', check=True)
            runtime('machine', 'cp', '--mode', '0555', str(args.guest),
                    name + ':/.workstream-guest', check=True)
            result = runtime('machine', 'exec', '--name', name, '--user', '0:0',
                             '--interactive', '--stream', '--', '/.workstream-guest',
                             input=struct.pack('>I', len(raw)) + raw)
            reached = marker.encode() in result.stdout
            print(json.dumps({'case': case, 'exit': result.returncode,
                              'command_reached': reached,
                              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                              'guest_sha256': hashlib.sha256(args.guest.read_bytes()).hexdigest(),
                              'stderr': result.stderr.decode(errors='replace')}), flush=True)
            if case == 'clean':
                if result.returncode != 0 or not reached:
                    raise AssertionError('clean image did not reach its command')
            elif result.returncode == 0 or reached:
                raise AssertionError('image-owned mount link reached workload execution')
            elif b'mount target is not a directory' not in result.stderr:
                raise AssertionError('negative image failed for an unrelated reason')
        finally:
            runtime('machine', 'delete', '--name', name, '--force', check=True)
            rows = json.loads(runtime('machine', 'ls', '--json', check=True).stdout)
            disk = args.home / '.cache/smolvm/vms' / hashlib.sha256(name.encode()).hexdigest()[:16]
            if any(row['name'] == name for row in rows) or os.path.lexists(disk):
                raise AssertionError('exact proof machine or disk remains')


if __name__ == '__main__':
    main()
