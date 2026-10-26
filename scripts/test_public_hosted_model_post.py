"""Bounded hosted model proof: public authority, no second paid project or fake grading."""

import asyncio
import copy
from datetime import UTC, datetime
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend'), str(ROOT / 'backend/scripts'), str(ROOT / 'backend/tests')]
from app.core.identifiers import new_record_id  # noqa: E402
from app.modules.model_usage.api import ProjectModelProfile  # noqa: E402
from experiments.pilot04_external_checker_runtime.public_hosted_model_post import (  # noqa: E402
    CEILING, CHECK, MODEL, ModelPostQualification, canonical, digest, fixture_archive,
    profile_spec, registry_spec, require_completed_effect, specification, POST_IMAGE, POST_CONFIG, POST_ARCHIVE,
    account_snapshot,
)


class HostedModelAuthority(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def qualification(self):
        value = ModelPostQualification(POST_IMAGE, POST_CONFIG, POST_ARCHIVE, self.root / 'proof.json',
                    'earlier setup effect remains unresolved in its original account')
        value.claim()
        self.addCleanup(value.close)
        return value

    def test_cache_requires_exact_qualified_production_image_not_a_substitute(self):
        qualification = self.qualification()
        binding = {'node_config': {'cache': [{'repository': 'workstream/terminal-systems-post',
            'platform_manifest_digest': POST_IMAGE.rsplit('@', 1)[1], 'config_image_id': POST_CONFIG,
            'smol': {'archive_sha256': POST_ARCHIVE}}]}}
        (self.root / 'node-binding.json').write_bytes(canonical(binding))
        attachment = SimpleNamespace(node_root=self.root, values={'WORKSTREAM_MODEL_PROXY_ENABLED': 'true'},
                                     custody={'model-proxy': {'image_id': 'verified-by-attachment'}})
        qualification.verify_cache(attachment)
        qualification.image_config_digest = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'image identity differs'):
            qualification.verify_cache(attachment)
        qualification.image_config_digest = POST_CONFIG
        binding['node_config']['cache'][0]['smol']['archive_sha256'] = 'sha256:' + '0' * 64
        (self.root / 'node-binding.json').write_bytes(canonical(binding))
        with self.assertRaisesRegex(RuntimeError, 'absent or substituted'):
            qualification.verify_cache(attachment)

    def test_one_literal_profile_reserves_full_context_within_the_total_authorization(self):
        profile = profile_spec(new_record_id(), new_record_id())
        self.assertEqual((profile.provider, profile.api, profile.model_snapshot), ('openrouter', 'chat_completions', MODEL))
        self.assertEqual(profile.maximum_input_tokens, 1050000)
        self.assertEqual(profile.maximum_calls, 1)
        self.assertEqual(profile.allowed_tools, ())
        self.assertEqual(profile.maximum_reservation_nanodollars, 5_323_728_000)
        self.assertLessEqual(profile.maximum_reservation_nanodollars, CEILING)
        self.assertEqual(profile.maximum_dispatch_reservation_nanodollars, profile.maximum_reservation_nanodollars)
        with self.assertRaises(ValueError):
            type(profile).model_validate(profile.model_dump(mode='python') | {'maximum_response_bytes': 200703})

    def test_existing_claim_or_alias_cannot_create_another_paid_project(self):
        value = self.qualification()
        value.checkpoint(project_id=str(new_record_id()), phase='authority_published')
        retained = value.proof_state.read_bytes()
        mode = value.proof_state.stat().st_mode
        with self.assertRaises(FileExistsError):
            self.qualification()
        self.assertEqual(value.proof_state.read_bytes(), retained)
        self.assertEqual(value.proof_state.stat().st_mode, mode)
        alias = self.root / 'alias'
        alias.symlink_to(value.proof_state)
        other = ModelPostQualification(value.image_reference, value.image_config_digest, value.image_archive_sha256,
                                       alias, 'unresolved')
        with self.assertRaisesRegex(RuntimeError, 'canonical'):
            other.claim()
        self.assertEqual(value.proof_state.read_bytes(), retained)

    def test_provider_override_is_rejected_before_claim_or_mutation(self):
        config = self.root / 'input.json'
        config.write_bytes(canonical({'image_reference': 'workstream/terminal-systems-post@sha256:' + 'a' * 64,
            'image_config_digest': 'sha256:' + 'b' * 64, 'image_archive_sha256': 'sha256:' + 'c' * 64,
            'proof_state': str(self.root / 'claim'), 'historical_uncertain_reference': 'unresolved',
            'provider': 'openai'}))
        config.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'fields differ'):
            ModelPostQualification.read_and_claim(config, self.root)
        self.assertFalse((self.root / 'claim').exists())

    def test_claim_creation_flushes_its_parent_before_any_public_mutation(self):
        import stat

        flushed = []
        original = os.fsync

        def fsync(descriptor):
            flushed.append('directory' if stat.S_ISDIR(os.fstat(descriptor).st_mode) else 'file')
            original(descriptor)

        with patch('os.fsync', side_effect=fsync):
            self.qualification()
        self.assertEqual(flushed, ['file', 'directory'])

    def test_changing_the_state_path_cannot_reset_the_deployment_authorization(self):
        config = self.root / 'input.json'
        config.write_bytes(canonical({'image_reference': POST_IMAGE, 'image_config_digest': POST_CONFIG,
            'image_archive_sha256': POST_ARCHIVE, 'proof_state': str(self.root / 'another-claim'),
            'historical_uncertain_reference': 'unresolved'}))
        config.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'single fixed state path'):
            ModelPostQualification.read_and_claim(config, self.root)
        self.assertFalse((self.root / 'another-claim').exists())

    def test_public_authority_publication_and_real_rules_bind_the_exact_profile(self):
        import httpx
        from app.adapters.project_agents.manager_authored import _compile_rules
        from app.core.hashing import canonical_json_hash

        qualification = self.qualification()
        project_id = str(new_record_id())
        requests = []
        actor_id, profile_id = new_record_id(), new_record_id()

        async def handler(request):
            body = json.loads(request.content)
            requests.append((request.method, request.url.path, request.headers['Idempotency-Key'], body))
            if request.url.path.endswith('/model-profiles'):
                spec = type(profile_spec(UUID(project_id), new_record_id())).model_validate_json(request.content)
                response = ProjectModelProfile(operation_id=UUID(request.headers['Idempotency-Key']),
                    actor_profile_id=actor_id, spec=spec, profile_digest=canonical_json_hash(body),
                    profile_id=profile_id, authorization_evidence_id=new_record_id(), created_at=datetime.now(UTC)).model_dump(mode='json')
            elif request.url.path.endswith('/model-budget-configurations'):
                response = {'spec': body, 'configuration_id': str(new_record_id()),
                            'lifetime_reserved_nanodollars': 0, 'lifetime_settled_nanodollars': 0}
            else:
                spec = registry_spec(body['image_digest'])
                self.assertEqual(body, spec.model_dump(mode='json'))
                response = {**body, 'entry_digest': spec.spec_digest, 'registry_entry_id': str(new_record_id())}
            return httpx.Response(201, json=response)

        attachment = SimpleNamespace(token_for_label=lambda label: 'scoped-rs256-fixture')

        async def exercise():
            async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', transport=httpx.MockTransport(handler)) as client:
                await qualification.bind_project(client, project_id, attachment)
                with self.assertRaisesRegex(RuntimeError, 'already owns one project'):
                    await qualification.bind_project(client, str(new_record_id()), attachment)

        asyncio.run(exercise())
        self.assertEqual([item[1] for item in requests], [
            f'/api/v1/operations/projects/{project_id}/model-profiles',
            f'/api/v1/operations/projects/{project_id}/model-budget-configurations',
            '/api/v1/operations/external-checker-registry'])
        self.assertTrue(all(item[0] == 'POST' for item in requests))
        budget = requests[1][3]
        self.assertEqual(budget['authorized_total_nanodollars'], CEILING)
        self.assertEqual(budget['lifetime_limit_nanodollars'], CEILING)
        self.assertEqual(budget['configuration_version'], 1)
        self.assertEqual(qualification.state['historical_charge']['status'], 'unresolved_separate')
        original = qualification.guide_bytes()
        capabilities = {stage: {'capability_id': 'fixture.' + stage, 'capability_version': 'v1'}
                        for stage in ('pre_submit', 'post_submit')}
        rules = json.loads(qualification.rules(original, capabilities, 0))
        binding = rules['post_submit_bindings'][0]
        configuration = {item['name']: item['value'] for item in binding['parameters']}
        registry_spec('sha256:' + 'a' * 64).configuration_schema.validate_instance(configuration)
        self.assertEqual(configuration['check'], CHECK)
        self.assertEqual(configuration['model_profile_id'], str(profile_id))
        self.assertEqual(rules['pre_submit_bindings'], [])
        doc = SimpleNamespace(source_item_id=new_record_id(), ingest_id=new_record_id(), sha256=digest(original))
        authored = SimpleNamespace(source_item_id=new_record_id(), ingest_id=new_record_id(), sha256=digest(canonical(rules)))
        result = _compile_rules(SimpleNamespace(agent_version='v1', material=SimpleNamespace(documents=[doc, authored])), [(authored, rules)])
        self.assertEqual(result.requirements[0].check_specification, specification()[0])
        self.assertEqual(result.requirements[0].check_specification.runtime_dependencies[0].provisioning, 'model_proxy')
        with self.assertRaisesRegex(RuntimeError, 'PRE model'):
            qualification.rules(original, capabilities, 1)

    def test_ambiguous_effect_or_outstanding_reservation_cannot_claim_model_proof(self):
        good = {'reserved_nanodollars': 0, 'effects': [{'state': 'completed', 'provider_response_known': True,
                                                      'request_binding_id': 'request', 'response_binding_id': 'response'}]}
        require_completed_effect(good)
        for state in ('prepared', 'dispatching', 'uncertain', 'known_failed', 'known_no_effect'):
            changed = copy.deepcopy(good)
            changed['effects'][0]['state'] = state
            with self.assertRaisesRegex(RuntimeError, 'ambiguous paid effect'):
                require_completed_effect(changed)
        for changed in ({**good, 'reserved_nanodollars': 1}, {**good, 'effects': []},
                        {**good, 'effects': good['effects'] * 2}):
            with self.assertRaises(RuntimeError):
                require_completed_effect(changed)

    def test_account_snapshot_joins_real_checker_and_setup_slot_owners_without_mutation(self):
        from sqlalchemy.dialects import postgresql

        statements = []

        class ReadOnlySession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, model, identifier):
                return SimpleNamespace(lifetime_reserved_nanodollars=0, lifetime_settled_nanodollars=123,
                                       current_configuration_id='retained-budget')

            async def scalars(self, statement):
                statements.append(str(statement.compile(dialect=postgresql.dialect())))
                return SimpleNamespace(all=lambda: [])

        result = asyncio.run(account_snapshot(ReadOnlySession, str(new_record_id())))
        self.assertEqual(result['settled_nanodollars'], 123)
        self.assertEqual(result['reserved_nanodollars'], 0)
        self.assertFalse(result['provider_invoice_qualified'])
        self.assertIn('LEFT OUTER JOIN checker_model_usage_slots', statements[0])
        self.assertIn('LEFT OUTER JOIN setup_model_usage_slots', statements[0])
        self.assertNotIn('model_usage_effects.project_id', statements[0])

    def test_fixture_is_deterministic_and_its_disclosed_commands_are_coherent(self):
        first = fixture_archive()
        self.assertEqual(first, fixture_archive())
        with ZipFile(BytesIO(first)) as archive:
            self.assertTrue(all(not name.startswith('/') and '..' not in Path(name).parts for name in archive.namelist()))
            archive.extractall(self.root)
        before = subprocess.run(['sh', 'tests/run.sh'], cwd=self.root, capture_output=True, timeout=5)
        self.assertNotEqual(before.returncode, 0)
        subprocess.run(['sh', 'solution/apply.sh'], cwd=self.root, capture_output=True, check=True, timeout=5)
        subprocess.run(['sh', 'tests/run.sh'], cwd=self.root, capture_output=True, check=True, timeout=5)
        self.assertIn(b'no execution or trial measurement is claimed', (self.root / 'evidence/results').read_bytes())

    def test_hosted_stalled_admission_does_not_inject_a_verifier_task(self):
        from app.core.config import get_settings

        with patch.dict(os.environ, {'WORKSTREAM_CELERY_BROKER_URL': 'redis://127.0.0.1:6379/15'}):
            # Earlier proof imports may have cached settings without a broker.
            get_settings.cache_clear()
            try:
                from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe
                from app.workers.artifacts import verify_object

                result = {'pre_submission_results': [{}], 'submission_bundle_preparation_status': 'object_confirmed', 'admission_id': None}
                ticks = iter(range(0, 1000, 31))
                with patch.object(probe, '_fixture_hashes', return_value={}), \
                        patch.object(probe, '_scan_audit_count', new=AsyncMock(return_value=0)), \
                        patch.object(probe, '_json', new=AsyncMock(return_value=result)), \
                        patch.object(probe, '_artifact_task_state', new=AsyncMock(return_value=([], [('job', 'pending', None)]))), \
                        patch.object(probe.time, 'monotonic', side_effect=lambda: next(ticks)), \
                        patch.object(probe.asyncio, 'sleep', new=AsyncMock()), patch.object(verify_object, 'apply_async') as dispatch:
                    with self.assertRaisesRegex(RuntimeError, 'remained object_confirmed'):
                        asyncio.run(probe._ready_admission(None, None, 'task', 'assignment', 'token', b'zip', 'summary', 'attestation', hosted=True))
                    dispatch.assert_not_called()
            finally:
                get_settings.cache_clear()

    def test_model_stage_requires_and_uses_the_existing_hosted_attachment(self):
        from experiments.pilot04_external_checker_runtime import run_public_journey_probe as probe
        from experiments.pilot04_external_checker_runtime import public_hosted_attachment as hosted

        args = ['proof', '--database-url', 'postgresql+asyncpg://isolated', '--broker-url', 'redis://isolated',
                '--hosted-model-post', '/private/model.json']
        with patch.object(sys, 'argv', args), patch.object(probe, 'run') as local:
            with self.assertRaises(SystemExit):
                probe.main()
            local.assert_not_called()
        with patch.object(sys, 'argv', args + ['--hosted-attachment', '/private/attachment.json']), \
                patch.object(hosted.HostedAttachment, 'read', return_value='inspected-later'), \
                patch.object(hosted, 'run', new=AsyncMock(return_value={'scope': 'hosted'})) as attach, \
                patch.object(probe, 'run') as local, patch('builtins.print'):
            self.assertEqual(probe.main(), 0)
            attach.assert_awaited_once_with('inspected-later', 'postgresql+asyncpg://isolated', 'redis://isolated',
                                           Path('/private/model.json'))
            local.assert_not_called()


if __name__ == '__main__':
    unittest.main()
