"""Real project-launch outage and authorized durable retry in the isolated public drill."""

import json
from pathlib import Path
import time
from uuid import uuid4

from app.modules.checkers.api.execution import CheckerRetryPublicResult
from app.modules.checkers.models import CheckerRun
from app.modules.tasks.models import SubmissionDispatch
from experiments.pilot04_external_checker_runtime.public_intake_trials import (
    _assert_no_submission_after_intake_failure, _selected,
)
from experiments.pilot04_external_checker_runtime.public_node_faults import node_command
from experiments.pilot04_external_checker_runtime.run_public_journey_probe import (
    _assert_task_has_no_effects, _json, _public_project, _require, _started_public_task,
    _wait_outbox_acknowledged, _with_fixture_file,
)
from tests.post_submit_materialization_helpers import archive_with_modes


def trace_events(root):
    return [json.loads(line) for line in (root / 'runtime-trace.jsonl').read_text().splitlines()]


def assert_launches(root, start, *, creates, executions):
    events = [event for event in trace_events(root)[start:] if event['project']]
    made = [event['name'] for event in events if event['operation'] == 'create']
    _require(len(made) == creates and len(set(made)) == creates,
             'runtime retry did not allocate the expected fresh machines')
    _require(len([e for e in events if e['operation'] == 'exec']) == executions,
             'runtime retried an invoked guest or skipped expected execution')
    _require(set(made) == {event['name'] for event in events if event['operation'] == 'delete'},
             'runtime retry lacks deletion of each exact machine')
    return made


async def public_runtime_trials(client, factory, env, root: Path):
    project, _, manager, contributor = await _public_project(
        client, factory, env, human_review_required=True,
    )
    task, assignment = await _started_public_task(
        client, project_id=str(project.project_id), manager_token=manager,
        contributor_token=contributor, source_ref='runtime-failure-recovery',
    )
    archive = archive_with_modes('evidence/results', project.project_id)
    route = f'/api/v1/tasks/{task}/submission-bundle-preparations'
    headers = {'Content-Type': 'application/zip', 'X-Task-Assignment-Id': assignment,
               'X-Submission-Summary': 'Completed task evidence.',
               'X-Contributor-Attestation': 'rights_confirmed; no confidential data or credentials.'}
    evidence = []
    try:
        for action, expected, creates, executions in (
            ('project_fail_once', 202, 2, 1),
            ('project_fail_all', 503, 3, 0),
            ('project_kill', 503, 1, 1),
        ):
            await node_command(root, action)
            start = len(trace_events(root))
            key = str(uuid4())
            content = _with_fixture_file(archive, 'runtime-wait.txt') if action == 'project_kill' else archive
            began = time.monotonic()
            result = await _json(client, 'POST', route, contributor, expected,
                                 headers=headers | {'Idempotency-Key': key}, content=content)
            await node_command(root, 'drained')
            names = assert_launches(root, start, creates=creates, executions=executions)
            row = await _selected(factory, key)
            if expected == 503:
                _require(row.status == 'infrastructure_failed' and row.terminal_json['execution'] is None,
                         'runtime outage was represented as a work verdict')
                await _assert_no_submission_after_intake_failure(factory, task, row.id)
                await node_command(root, 'clear')
                replay_start = len(trace_events(root))
                replay = await _json(client, 'POST', route, contributor, 503,
                                     headers=headers | {'Idempotency-Key': key}, content=content)
                _require(replay['error']['code'] == result['error']['code'], 'failure replay changed code')
                # Re-upload and trusted inspection may occur; selected project execution may not.
                assert_launches(root, replay_start, creates=0, executions=0)
                repeated = await _selected(factory, key)
                _require((repeated.id, repeated.terminal_digest) == (row.id, row.terminal_digest),
                         'same-key replay replaced terminal failure custody')
                fresh_key = str(uuid4())
                await _json(client, 'POST', route, contributor, 202,
                            headers=headers | {'Idempotency-Key': fresh_key}, content=archive)
                fresh = await _selected(factory, fresh_key)
                _require(fresh.id != row.id and fresh.eligible is True,
                         'fresh request did not repeat intake successfully after recovery')
            evidence.append({'case': action, 'run_id': row.id, 'machines': names,
                             'elapsed_seconds': round(time.monotonic() - began, 3),
                             'status': row.status})
    finally:
        await node_command(root, 'clear')
        await node_command(root, 'drained')
    return evidence


async def retry_post_outage(client, factory, submission_id, project_id, operator_token, root):
    async with factory() as session:
        dispatch = await session.get(SubmissionDispatch, submission_id)
        run_id, event_id = dispatch.evaluation_attempt_id, dispatch.evaluation_event_id
    await _wait_outbox_acknowledged(factory, event_id, project_id)
    async with factory() as session:
        failed = await session.get(CheckerRun, run_id)
        _require(failed.status == 'infrastructure_failed' and failed.completion_event_id is None
                 and failed.failure_code == 'implementation_unavailable'
                 and failed.finalize_evidence_id is not None,
                 'project POST outage lacks terminal infrastructure custody')
        await _assert_task_has_no_effects(session, failed.task_id)
    await node_command(root, 'clear')
    await node_command(root, 'drained')
    base = f'/api/v1/operations/projects/{project_id}'
    page = await _json(client, 'GET', base + '/checker-retry-sources', operator_token, 200)
    _require([item['source']['source_run_id'] for item in page['items']] == [run_id],
             'public recovery discovery did not return the exact failed run')
    route = base + f'/checker-runs/{run_id}/retry'
    headers = {'Idempotency-Key': str(uuid4())}
    payload = {'reason': 'Restored dedicated Smol project execution'}
    raw = await _json(client, 'POST', route, operator_token, 201, headers=headers, json=payload)
    replay = await _json(client, 'POST', route, operator_token, 201, headers=headers, json=payload)
    _require(replay == raw, 'authorized POST retry replay changed receipt')
    receipt = CheckerRetryPublicResult.model_validate_json(json.dumps(raw))
    _require(receipt.successor.generation == failed.evaluation_generation + 1,
             'POST retry did not allocate exactly the next evaluation generation')
    return receipt.successor, {'entry': 'public_operator_checker_retry',
                              'failed_run_id': run_id, 'receipt_id': str(receipt.receipt_id),
                              'successor_run_id': str(receipt.successor.run_id),
                              'generation': receipt.successor.generation}
