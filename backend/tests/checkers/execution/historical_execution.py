"""Literal predecessor rows for migration tests, never an execution implementation.

Callers supply archived members, counts and routing. This file only encodes those
facts and inserts them with the predecessor database constraints enabled. It does
not invoke current CHECKERS, AUTH, outbox or TASK owners on an archived schema.
"""

import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

from sqlalchemy import text

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from tests.historical_submission_fixtures import historical_material_fixture


def _json_uuid(value):
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Non-JSON archived fact: {type(value).__name__}")


def _canonical_text(value, *, exclude=frozenset()):
    return json.dumps(
        {key: item for key, item in value.items() if key not in exclude},
        default=_json_uuid,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _json_facts(value):
    return json.loads(_canonical_text(value))


async def archived_schema_revision(session):
    revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
    assert 8 <= int(revision[:4]) <= 28, "archive seeder used outside predecessor schemas"
    assert not await session.scalar(text("""SELECT EXISTS(
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='checker_runs'
          AND column_name='input_materialization_evidence_id')"""))
    return int(revision[:4])


async def seed_archived_checker_request(h):
    request = h.request
    context = request["expected_context"]
    run_id, result_id = new_record_id(), new_record_id()
    async with h.factory() as session, session.begin():
        await archived_schema_revision(session)
        previous = await session.scalar(text(
            "SELECT current_run_id FROM public.checker_submission_fences WHERE submission_id=:id"
        ), {"id": UUID(str(request["submission_id"]))})
        await session.execute(text("""INSERT INTO public.checker_runs (
            id, project_id, task_id, submission_id, submission_version,
            evaluation_request_id, phase, evaluation_generation, request_json,
            request_digest, result_id, trigger_source, status, outcome_source,
            routing_recommendation, worker_lease_generation, supersedes_checker_run_id,
            locked_guide_version, locked_post_submit_checker_policy_id,
            locked_post_submit_checker_policy_version, locked_post_submit_checker_policy_hash,
            locked_review_policy_id, locked_review_policy_generation, locked_review_policy_hash,
            locked_revision_policy_id, locked_revision_policy_generation, locked_revision_policy_hash,
            passed_count, warning_count, failed_count, blocking_count
        ) VALUES (
            :id, :project, :task, :submission, :version,
            :request_id, 'post_submission', :generation, :request_json,
            :digest, :result_id, 'coordinated_evaluation', 'queued', 'none',
            'not_evaluated', 0, :previous,
            :guide, :post_id, :post_version, :post_hash,
            :review_id, :review_generation, :review_hash,
            :revision_id, :revision_generation, :revision_hash, 0, 0, 0, 0
        )"""), {
            "id": run_id,
            "project": UUID(str(request["project_id"])),
            "task": UUID(str(request["task_id"])),
            "submission": UUID(str(request["submission_id"])),
            "version": request["submission_version"],
            "request_id": UUID(str(request["evaluation_request_id"])),
            "generation": request["evaluation_generation"],
            "request_json": _canonical_text(request, exclude={"request_sha256"}),
            "digest": request["request_sha256"],
            "result_id": result_id,
            "previous": previous,
            "guide": context["guide_version"],
            "post_id": UUID(str(context["post_policy_id"])),
            "post_version": context["post_policy_version"],
            "post_hash": context["post_policy_hash"],
            "review_id": UUID(str(context["review_policy_id"])),
            "review_generation": context["review_generation"],
            "review_hash": context["review_hash"],
            "revision_id": UUID(str(context["revision_policy_id"])),
            "revision_generation": context["revision_generation"],
            "revision_hash": context["revision_hash"],
        })
        await session.execute(text(
            "INSERT INTO public.checker_submission_fences(submission_id,current_run_id) "
            "VALUES (:submission,:run)" if previous is None else
            "UPDATE public.checker_submission_fences SET current_run_id=:run "
            "WHERE submission_id=:submission"
        ), {"submission": UUID(str(request["submission_id"])), "run": run_id})
    return {
        "request_id": UUID(str(request["evaluation_request_id"])),
        "request_digest": request["request_sha256"],
        "attempt_id": run_id,
        "result_id": result_id,
        "evaluation_generation": request["evaluation_generation"],
    }


async def _seed_archived_receipt(session, run_id, phase, receipt_id):
    """Store the then-installed SQL receipt shape as archived migration data."""
    row = (await session.execute(text("""SELECT r.project_id,r.evaluation_request_id,
        public.checker_post_submit_authority_digest(r,:phase) AS digest,
        (SELECT id FROM public.actor_profiles
         WHERE service_identity='workstream.checker.post_submit') AS actor
        FROM public.checker_runs r WHERE r.id=:id"""),
        {"id": run_id, "phase": phase})).mappings().one()
    assert row["actor"] is not None
    await session.execute(text("""INSERT INTO public.audit_events (
        id, entity_type, entity_id, event_type, actor_id, actor_roles, claim_snapshot,
        auth_source, is_dev_auth, event_payload, event_domain, event_version, occurred_at,
        reason, actor_ref_kind, request_id, correlation_id, action_id, permission_id,
        project_id, resource_type, resource_id, target_ref_kind, target_ref_id, after_facts
    ) VALUES (
        :id, 'authorization_decision', :id, 'SensitiveAuthorizationAllowed', :actor,
        CAST('[]' AS json), CAST('{}' AS json), 'local_authority', false, CAST('{}' AS json),
        'authority', 1, clock_timestamp(), 'authorization_evaluation', 'actor_profile',
        :request, :request, :action, :action, :project, 'checker_run', :resource,
        'project', :target, CAST(:facts AS json)
    )"""), {
        "id": receipt_id,
        "actor": str(row["actor"]),
        "request": UUID(str(row["evaluation_request_id"])),
        "action": "checker.post_submit." + phase,
        "project": UUID(str(row["project_id"])),
        "resource": str(run_id),
        "target": str(row["project_id"]),
        "facts": _canonical_text({"allowed": True, "resource_context_digest": row["digest"]}),
    })


async def seed_archived_running_checker(h):
    async with h.factory() as session, session.begin():
        revision = await archived_schema_revision(session)
        row = (await session.execute(text("""SELECT r.* FROM public.checker_runs r
            JOIN public.checker_submission_fences f ON f.current_run_id=r.id
            WHERE f.submission_id=:id"""),
            {"id": UUID(str(h.request["submission_id"]))})).mappings().one()
        now = await session.scalar(text("SELECT clock_timestamp()"))
        lease = {
            "reservation": {
                "request_id": UUID(str(row["evaluation_request_id"])),
                "request_digest": row["request_digest"],
                "attempt_id": UUID(str(row["id"])),
                "result_id": UUID(str(row["result_id"])),
                "evaluation_generation": row["evaluation_generation"],
            },
            "lease_id": new_record_id(),
            "lease_generation": 1,
            "expires_at": now + timedelta(seconds=300),
            "execute_evidence_id": new_record_id(),
        }
        await session.execute(text("""UPDATE public.checker_runs SET status='running',
            started_at=:now, worker_lease_id=:lease, worker_lease_generation=1,
            worker_lease_expires_at=:expires, execute_evidence_id=:receipt WHERE id=:id"""), {
            "id": row["id"], "now": now, "lease": lease["lease_id"],
            "expires": lease["expires_at"], "receipt": lease["execute_evidence_id"],
        })
        if revision >= 10:
            await _seed_archived_receipt(session, row["id"], "execute", lease["execute_evidence_id"])
        return lease


def archived_terminal_rows(h, lease, *, outcome, members, counts,
                           routing_recommendation, failure_code, material):
    """Encode supplied archived terminal facts without classifying any member."""
    request = _json_facts(h.request)
    reservation = lease["reservation"]
    serialized_members = []
    for member in members:
        assert member.get("schema_version", "post_submit_structural_result") == (
            "post_submit_structural_result"
        ), "archived member protocol tag differs from predecessor SQL"
        serialized_members.append({
            "schema_version": "post_submit_structural_result",
            **{key: deepcopy(member[key]) for key in (
                "checker_id", "definition_version", "implementation_version", "status",
                "code", "failure_category", "severity", "counters",
            )},
        })
    result = _json_facts({
        "schema_version": "post_submit_evaluation_result",
        "request_id": request["evaluation_request_id"],
        "request_digest": request["request_sha256"],
        "attempt_id": reservation["attempt_id"],
        "evaluation_generation": request["evaluation_generation"],
        "result_id": reservation["result_id"],
        "outcome": outcome,
        "member_results": serialized_members,
        "infrastructure_failure_code": failure_code,
    })
    result["result_digest"] = canonical_json_hash(result)
    final_id = new_record_id()
    outbox = None
    if outcome == "completed":
        payload = {
            "project_id": request["project_id"],
            "task_id": request["task_id"],
            "submission_id": request["submission_id"],
            "reference": {"schema_version": "post_submit_current_result_reference", **{
                key: result[key] for key in (
                    "request_id", "request_digest", "attempt_id", "evaluation_generation",
                    "result_id", "result_digest",
                )
            }},
            "routing_recommendation": routing_recommendation,
            "output_binding_ids": [],
            "execute_evidence_id": str(lease["execute_evidence_id"]),
            "finalize_evidence_id": str(final_id),
        }
        outbox = {
            "event_id": new_record_id(),
            "event_type": "PostSubmissionEvaluationCompleted",
            "event_version": 1,
            "aggregate_type": "checker_run",
            "aggregate_id": reservation["attempt_id"],
            "project_id": UUID(str(request["project_id"])),
            "correlation_id": request["evaluation_request_id"],
            "idempotency_key": "checker-completed:" + str(reservation["attempt_id"]),
            "payload": payload,
            "payload_digest": canonical_json_hash(payload),
        }
    member_rows = [{
        "id": new_record_id(),
        "checker_run_id": reservation["attempt_id"],
        "task_id": UUID(str(request["task_id"])),
        "submission_id": UUID(str(request["submission_id"])),
        "member_order": order,
        "checker_name": member["checker_id"],
        **{key: deepcopy(member[key]) for key in (
            "definition_version", "implementation_version", "status", "severity", "code",
            "failure_category", "counters",
        )},
    } for order, member in enumerate(result["member_results"])]
    return {
        "request": request,
        "lease": deepcopy(lease),
        "result": result,
        "material": _json_facts(material) if material is not None else None,
        "member_rows": member_rows,
        "outbox": outbox,
        "run": {
            "id": reservation["attempt_id"],
            "status": outcome,
            "result_json": _canonical_text(result, exclude={"result_digest"}),
            "result_digest": result["result_digest"],
            "material_custody": _json_facts(material) if material is not None else None,
            "finalize_evidence_id": final_id,
            "routing_recommendation": routing_recommendation,
            "failure_code": failure_code,
            "passed_count": counts["passed"],
            "warning_count": counts["warning"],
            "failed_count": counts["failed"],
            "blocking_count": counts["blocking"],
            "completion_event_id": outbox["event_id"] if outbox is not None else None,
        },
    }


async def seed_archived_terminal(session, rows):
    """Insert supplied rows inside the caller's transaction; constraints decide validity."""
    revision = await archived_schema_revision(session)
    for member in rows["member_rows"]:
        await session.execute(text("""INSERT INTO public.checker_results (
            id, checker_run_id, task_id, submission_id, member_order, checker_name,
            definition_version, implementation_version, status, severity, code,
            failure_category, counters
        ) VALUES (
            :id, :checker_run_id, :task_id, :submission_id, :member_order, :checker_name,
            :definition_version, :implementation_version, :status, :severity, :code,
            :failure_category, CAST(:counters AS json)
        )"""), member | {"counters": json.dumps(member["counters"], allow_nan=False)})
    event = rows["outbox"]
    if event is not None:
        await session.execute(text("""INSERT INTO public.outbox_events (
            event_id, event_type, event_version, aggregate_type, aggregate_id, project_id,
            correlation_id, idempotency_key, payload, payload_digest
        ) VALUES (
            :event_id, :event_type, :event_version, :aggregate_type, :aggregate_id, :project_id,
            :correlation_id, :idempotency_key, CAST(:payload AS jsonb), :payload_digest
        )"""), event | {"payload": _canonical_text(event["payload"])})
    run = rows["run"]
    await session.execute(text("""UPDATE public.checker_runs SET status=:status,
        result_json=:result_json, result_digest=:result_digest,
        material_custody=CAST(:material_custody AS json),
        finalize_evidence_id=:finalize_evidence_id, completed_at=clock_timestamp(),
        outcome_source='auto_checker', routing_recommendation=:routing_recommendation,
        failure_code=:failure_code, passed_count=:passed_count, warning_count=:warning_count,
        failed_count=:failed_count, blocking_count=:blocking_count,
        completion_event_id=:completion_event_id WHERE id=:id"""), run | {
            "material_custody": _canonical_text(run["material_custody"])
            if run["material_custody"] is not None else None,
        })
    if revision >= 10:
        await _seed_archived_receipt(session, run["id"], "finalize", run["finalize_evidence_id"])


@asynccontextmanager
async def archived_completed_checker_source(tmp_path, database_url, **options):
    async with historical_material_fixture(tmp_path, database_url, **options) as h:
        await seed_archived_checker_request(h)
        lease = await seed_archived_running_checker(h)
        rows = archived_terminal_rows(
            h, lease, outcome="completed", members=h.archived_members, counts=h.archived_counts,
            routing_recommendation="allow_review", failure_code=None, material=h.archived_material,
        )
        async with h.factory() as session, session.begin():
            await seed_archived_terminal(session, rows)
        h.result, h.material, h.completion_event = rows["result"], rows["material"], rows["outbox"]
        async with h.factory() as session:
            row = (await session.execute(text("""SELECT r.*,s.task_assignment_id,s.contributor_id,
                s.contribution_policy_version_id,p.human_review_required FROM public.checker_runs r
                JOIN public.submissions s ON s.id=r.submission_id
                JOIN public.review_policies p ON p.id=s.locked_review_policy_id WHERE r.id=:id"""),
                {"id": rows["run"]["id"]})).mappings().one()
        h.source = {name: row[name] for name in (
            "project_id", "task_id", "submission_id", "submission_version", "contributor_id",
            "contribution_policy_version_id", "evaluation_request_id", "request_digest",
            "evaluation_generation", "result_id", "result_digest", "completion_event_id",
            "execute_evidence_id", "finalize_evidence_id", "human_review_required",
        )} | {
            "id": new_record_id(),
            "checker_run_id": row["id"],
            "assignment_id": row["task_assignment_id"],
            **{name: h.material[name] for name in (
                "replica_id", "content_sha256", "byte_count", "semantic_manifest_sha256",
            )},
        }
        for name, value in h.source.items():
            if name.endswith("_id") or name == "id":
                h.source[name] = UUID(str(value))
        yield h
