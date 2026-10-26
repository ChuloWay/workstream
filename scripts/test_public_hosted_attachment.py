"""Hosted attachment refuses substitute services and observes real native copies."""

import copy
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/scripts'), str(ROOT / 'backend/tests')]
from experiments.pilot04_external_checker_runtime.public_hosted_attachment import (  # noqa: E402
    validate_container,
    HostedAttachment, manager_rules, duplicate_completed,
)


class HostedContainerCustody(unittest.TestCase):
    def setUp(self):
        self.rendered = {
            'image': 'example/backend@sha256:' + 'a' * 64, 'user': '10001:10001',
            'command': ['python', '-m', 'celery', '-A', 'app.workers.celery_app', 'worker', '--pool=prefork'],
            'environment': {'WORKSTREAM_ENVIRONMENT': 'production',
                            'WORKSTREAM_PROJECT_AGENT_RUNTIME': 'manager_authored'},
            'volumes': [{'type': 'bind', 'source': '/owned/scratch', 'target': '/owned/scratch'}],
            'secrets': [{'source': 'database', 'target': 'database_url'}],
            'networks': {'default': None},
        }
        self.image = {'Id': 'sha256:' + 'b' * 64, 'Config': {
            'Entrypoint': ['/usr/local/bin/workstream-release-entrypoint'], 'Env': ['PATH=/usr/bin']}}
        self.container = {'Id': 'exact-worker', 'Image': self.image['Id'],
                          'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                          'Config': {'Image': self.rendered['image'], 'User': self.rendered['user'],
                                     'Cmd': self.rendered['command'],
                                     'Entrypoint': self.image['Config']['Entrypoint'],
                                     'Env': ['PATH=/usr/bin'] + [k + '=' + v for k, v in self.rendered['environment'].items()]},
                          'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False,
                                         'CapDrop': ['ALL'], 'CapAdd': None,
                                         'SecurityOpt': ['no-new-privileges:true']},
                          'NetworkSettings': {'Networks': {'owned_default': {}}},
                          'Mounts': [{'Type': 'bind', 'Source': '/owned/scratch',
                                      'Destination': '/owned/scratch', 'RW': True},
                                     {'Type': 'bind', 'Source': '/private/db',
                                      'Destination': '/run/secrets/database_url', 'RW': False}]}

    def check(self, container=None):
        validate_container('worker', self.rendered, container or self.container,
                           self.image, {'database': {'file': '/private/db'}},
                           {'default': {'name': 'owned_default'}})

    def test_exact_production_service_is_accepted(self):
        self.check()

    def test_recorded_worker_host_api_and_hmac_are_refused(self):
        for command in (
            ['python', '-m', 'celery', '-A', 'experiments.pilot04_external_checker_runtime.guide_worker', 'worker'],
            ['python', '-m', 'uvicorn', 'experiments.pilot04_external_checker_runtime.public_intake_observer:app'],
        ):
            changed = copy.deepcopy(self.container)
            changed['Config']['Cmd'] = command
            with self.assertRaisesRegex(RuntimeError, 'executable differs'):
                self.check(changed)
        for environment in ('WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET=fixture-secret',
                            'WORKSTREAM_CELERY_TASK_ALWAYS_EAGER=true',
                            'WORKSTREAM_PROBE_INTAKE_TRACE=/tmp/fake'):
            changed = copy.deepcopy(self.container)
            changed['Config']['Env'].append(environment)
            with self.assertRaisesRegex(RuntimeError, 'extra environment'):
                self.check(changed)

    def test_same_labels_cannot_hide_foreign_image_mount_or_entrypoint(self):
        changes = (
            ('Image', 'sha256:' + 'c' * 64),
            ('Mounts', self.container['Mounts'] + [{'Type': 'bind', 'Source': '/var/run/docker.sock',
                                                  'Destination': '/var/run/docker.sock', 'RW': True}]),
            ('Config', dict(self.container['Config'], Entrypoint=['/bin/sh'])),
            ('HostConfig', dict(self.container['HostConfig'], Privileged=True)),
            ('State', {'Running': True, 'Health': {'Status': 'starting'}}),
            ('NetworkSettings', {'Networks': {'foreign': {}}}),
            ('HostConfig', dict(self.container['HostConfig'], PortBindings={
                '8000/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8000'}]})),
        )
        for key, value in changes:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.check(dict(self.container, **{key: value}))


class NativePreparationObservation(unittest.TestCase):
    def test_only_successful_final_copy_records_completion_without_altering_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = root / 'wrapper'
            shutil.copyfile(ROOT / 'experiments/pilot04_external_checker_runtime/public_runtime_wrapper.py', wrapper)
            binary = root / 'smol'
            binary.write_text('#!/bin/sh\nprintf "actual-native-output\\n"\nexit "$RESULT"\n')
            binary.chmod(0o700)
            trace = root / 'trace'
            leases = root / 'smol-leases'
            leases.mkdir()
            lease = {'name': 'intake-one', 'owner': 'owned', 'epoch': 'original',
                     'expires_ms': 100000, 'lifetime_ms': 90000}
            (leases / 'intake-one.json').write_text(json.dumps(lease))
            wrapper.with_suffix('.json').write_text(json.dumps({
                'trace': str(trace), 'binary': str(binary), 'project_archive': '/project.tar',
                'socket': str(root / 'node.sock')}))
            for status, destination, completed in ((7, 'intake-one:/.workstream-guest', False),
                                                   (0, 'intake-one:/unrelated', False),
                                                   (0, 'intake-one:/.workstream-guest', True)):
                trace.write_text(json.dumps({'operation': 'create', 'name': 'intake-one',
                                             'project': False, 'lease': lease}) + '\n')
                result = subprocess.run([sys.executable, str(wrapper), 'machine', 'cp', '--mode', '0555',
                                         '/guest', destination], env={'RESULT': str(status)},
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, status)
                self.assertEqual(result.stdout, b'actual-native-output\n')
                events = [json.loads(line) for line in trace.read_text().splitlines()]
                self.assertEqual(len(events), 2 if completed else 1)
                if completed:
                    self.assertEqual(events[-1]['operation'], 'prepare_completed')
                    self.assertEqual(events[-1]['name'], 'intake-one')
                    self.assertEqual(events[-1]['lease'], lease)
                    self.assertFalse(events[-1]['project'])


class HostedFixtureContracts(unittest.TestCase):
    def test_service_setup_uses_public_owner_endpoint_and_stable_exact_replay_keys(self):
        import httpx
        from provision_local_service_actors import JOURNEY_SERVICE_IDENTITIES

        attachment = HostedAttachment('http://127.0.0.1:8000', Path('/release'), Path('/issuer'),
                                      Path('/node'), {}, 'sha256:fixture')
        attachment.actors['access-admin'] = SimpleNamespace(actor_profile_id=uuid4())
        observed = []

        async def respond(request):
            observed.append((request.method, request.url.path, request.headers['Authorization'],
                             request.headers['Idempotency-Key'], json.loads(request.content)))
            return httpx.Response(201, json={'created': True})

        async def exercise():
            async with httpx.AsyncClient(base_url=attachment.origin, transport=httpx.MockTransport(respond)) as client:
                await attachment.provision_services(client)
                await attachment.provision_services(client)

        with patch.object(attachment, 'token_for_label', return_value='scoped-rs256-token'):
            asyncio.run(exercise())
        count = len(JOURNEY_SERVICE_IDENTITIES)
        self.assertEqual(observed[:count], observed[count:])
        self.assertEqual([item[4]['service_identity'] for item in observed[:count]], list(JOURNEY_SERVICE_IDENTITIES))
        self.assertTrue(all(item[:3] == ('POST', '/api/v1/service-actors', 'Bearer scoped-rs256-token')
                            for item in observed))
        self.assertEqual(len({item[3] for item in observed}), count)

    def test_duplicate_requires_same_task_received_then_exact_terminal_worker_result(self):
        identifier = str(uuid4())
        prefix = 'Task workstream.outbox.deliver_event[' + identifier + ']'
        received = '[INFO/MainProcess] ' + prefix + ' received\n'
        completed = "[INFO/ForkPoolWorker-2] " + prefix + " succeeded in 0.124s: {'status': 'delivery_unavailable'}\n"
        self.assertTrue(duplicate_completed(received + completed, identifier))
        for logs in (received, completed, completed + received,
                     received + completed.replace(identifier, str(uuid4())),
                     received + completed.replace('delivery_unavailable', 'delivered')):
            self.assertFalse(duplicate_completed(logs, identifier))

    def test_scoped_fixture_token_uses_rs256_without_embedded_product_roles(self):
        import jwt
        from experiments.hosted_drill_identity.fixture import initialize, read_private, ISSUER, AUDIENCE

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'issuer'
            initialize(root)
            attachment = HostedAttachment('http://127.0.0.1:8000', root / 'release.env', root,
                                          root / 'node', {}, 'sha256:unused')
            token = attachment.token_for_label('operator')
            key = jwt.PyJWK(json.loads(read_private(root / 'jwks.json'))['keys'][0]).key
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=ISSUER, audience=AUDIENCE)
            self.assertEqual(claims['scope'], 'workstream:access')
            self.assertEqual(claims['subject_kind'], 'human')
            self.assertEqual(claims['exp'] - claims['iat'], 900)
            self.assertNotIn('roles', claims)
            self.assertEqual(list(root.glob('token-*')), [])
            with self.assertRaises(jwt.InvalidAlgorithmError):
                jwt.decode(token, key, algorithms=['HS256'])

    def test_manager_rules_compile_with_production_dto_and_original_citation(self):
        from app.adapters.project_agents.manager_authored import _compile_rules

        original = b'Explicit synthetic hosted runtime guide.'
        document = SimpleNamespace(source_item_id=uuid4(), ingest_id=uuid4(),
                                   sha256='sha256:' + hashlib.sha256(original).hexdigest())
        rules = SimpleNamespace(source_item_id=uuid4(), ingest_id=uuid4(), sha256='sha256:' + 'f' * 64)
        context = SimpleNamespace(agent_version='v1', material=SimpleNamespace(documents=[document, rules]))
        capabilities = {stage: {'capability_id': 'probe.' + stage, 'capability_version': 'v1'}
                        for stage in ('pre_submit', 'post_submit')}
        for count in (0, 1, 2):
            authored = json.loads(manager_rules(original, capabilities, count))
            result = _compile_rules(context, [(rules, authored)])
            self.assertEqual(result.status, 'draft_ready')
            self.assertEqual(len(result.pre_submit_bindings), count)
            self.assertEqual(len(result.post_submit_bindings), 1)
            self.assertEqual(len(result.requirements), count + 1)
            self.assertEqual(result.findings[0].evidence_refs[0].sha256, document.sha256)

    def test_hosted_cli_never_calls_local_launcher(self):
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe
        from experiments.pilot04_external_checker_runtime import public_hosted_attachment as hosted

        with patch.object(sys, 'argv', ['proof', '--hosted-attachment', '/private/attach.json',
                                       '--database-url', 'postgresql+asyncpg://isolated', '--broker-url', 'redis://isolated']), \
                patch.object(hosted.HostedAttachment, 'read', return_value='attached'), \
                patch.object(hosted, 'run', new=AsyncMock(return_value={'attached': True})) as attached, \
                patch.object(probe, 'run') as launch, patch('builtins.print'):
            self.assertEqual(probe.main(), 0)
            attached.assert_awaited_once_with('attached', 'postgresql+asyncpg://isolated', 'redis://isolated')
            launch.assert_not_called()
        with patch.object(sys, 'argv', ['proof', '--hosted-attachment', '/private/attach.json',
                                       '--database-url', 'postgresql+asyncpg://isolated', '--broker-url', 'redis://isolated',
                                       '--node-config', '/local/node.json']), patch.object(probe, 'run') as launch:
            with self.assertRaises(SystemExit):
                probe.main()
            launch.assert_not_called()

    def test_stalled_upload_refuses_early_cleanup_or_reset_deadline(self):
        import time
        from experiments.pilot04_external_checker_runtime import public_intake_trials as intake

        class StreamingClient:
            async def post(self, route, *, headers, content):
                async for _ in content:
                    pass
                raise AssertionError('invalid expiry should fail before completing request')

        expires = time.time_ns() // 1_000_000 + 1000
        prepared = {'operation': 'prepare_completed', 'name': 'exact-intake', 'project': False,
                    'lease': {'epoch': 'original', 'expires_ms': expires}}
        for deletion in (
            {'wall_ms': expires - 1, 'lease': prepared['lease']},
            {'wall_ms': expires + 1, 'lease': {'epoch': 'original', 'expires_ms': expires + 1000}},
            {'wall_ms': expires + 1, 'lease': {'epoch': 'restarted', 'expires_ms': expires}},
        ):
            with self.subTest(deletion=deletion), patch.object(intake, 'trace_events', return_value=[]), \
                    patch.object(intake, '_native_event', new=AsyncMock(side_effect=[prepared, deletion])), \
                    patch.object(intake, 'node_command', new=AsyncMock()) as cleanup:
                with self.assertRaisesRegex(RuntimeError, 'original lease expiry'):
                    asyncio.run(intake._expire_upload(StreamingClient(), None, '/public', {}, 'token', b'zip',
                                                     'task', Path('/owned/control')))
                cleanup.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
