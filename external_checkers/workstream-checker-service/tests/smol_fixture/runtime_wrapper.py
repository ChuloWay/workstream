#!/usr/bin/python3
"""Test-only runtime interposer: exact attempt telemetry and bounded faults."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

settings = json.loads(Path(__file__).with_suffix('.json').read_text())
arguments = sys.argv[1:]
if len(arguments) >= 2 and arguments[0] == 'machine':
    operation = arguments[1]
    name = arguments[arguments.index('--name') + 1] if '--name' in arguments else None
    trace = Path(settings['trace'])
    if operation in {'create', 'start', 'exec', 'delete'}:
        with trace.open('a+') as output:
            fcntl.flock(output, fcntl.LOCK_EX)
            output.seek(0)
            prior = [json.loads(line)['name'] for line in output if json.loads(line)['operation'] == 'create']
            event = {'operation': operation, 'name': name}
            if operation == 'create':
                rows = json.loads(subprocess.check_output([settings['binary'], 'machine', 'ls', '--json']))
                event['prior_resources'] = [row['name'] for row in rows if row['name'] in prior]
                for previous in prior:
                    disk = Path(os.environ['HOME']) / '.cache/smolvm/vms' / hashlib.sha256(previous.encode()).hexdigest()[:16]
                    if (Path(settings['cgroups']) / previous).exists() or disk.exists():
                        event['prior_resources'].append(previous)
            output.write(json.dumps(event) + '\n')
            output.flush()
            os.fsync(output.fileno())
        if operation == 'start':
            mode = Path(settings['mode'])
            with mode.open('r+') as state:
                fcntl.flock(state, fcntl.LOCK_EX)
                remaining = int(state.read())
                if remaining:
                    state.seek(0)
                    state.write(str(max(-1, remaining - 1)))
                    state.truncate()
                    state.flush()
                    os.fsync(state.fileno())
                    sys.exit(93)
        if operation == 'delete' and Path(settings['delete_fault']).exists():
            sys.exit(93)
os.execv(settings['binary'], [settings['binary'], *arguments])
