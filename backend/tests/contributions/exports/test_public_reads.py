"""Public signed read/export proof against real canonical source and retained AUTH."""

import csv
import json
from io import StringIO

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.db.session import get_session_factory
from app.modules.actors.models import ActorIdentityLink
from app.modules.actors.api import ServiceIdentity
from tests.authentication.support import issue_asymmetric_token
from tests.contributions.records.support import authorized_submitter_source, rows
from tests.authorization.admin_access.support import create_project
from .support import source_actor, export_path, export_audits
from uuid import uuid4


@pytest.mark.parametrize("instruments", [(), ("money",), ("money", "project_points")])
async def test_self_export_preserves_real_source_and_complete_json_csv_awards(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle, instruments,
):
    async with authorized_submitter_source(tmp_path, auth_database_env, contribution_awards=instruments) as h:
        actor = await source_actor(signed_access, h)
        async with h.factory() as session:
            before = {table: await rows(session, table) for table in
                      ("contribution_records", "compensation_awards", "final_acceptances")}
        json = await signed_access.client.get("/api/v1/actors/me/contributions", headers=actor.headers)
        assert json.status_code == 200, json.text
        item, = json.json()["items"]
        assert item["contribution_id"] == str(h.submitter_record.id)
        assert item["source_final_acceptance_id"] == str(h.acceptance.id)
        assert item["acceptance_routing_manifest_id"] == str(h.acceptance.source_routing_manifest_id)
        assert {award["instrument"] for award in item["awards"]} == set(instruments)
        csv_response = await signed_access.client.get("/api/v1/actors/me/contributions?format=csv", headers=actor.headers)
        assert csv_response.status_code == 200, csv_response.text
        exported = list(csv.DictReader(StringIO(csv_response.text, newline="")))
        assert len(exported) == max(1, len(instruments))
        assert {row["contribution_id"] for row in exported} == {item["contribution_id"]}
        assert {(row["award_id"], row["quantity"]) for row in exported if row["award_id"]} == {
            (award["award_id"], award["quantity"]) for award in item["awards"]
        }
        async with h.factory() as session:
            assert {table: await rows(session, table) for table in before} == before
        evidence = await export_audits(h.factory)
        assert len(evidence) == 2 and all(row["after_facts"]["allowed"] for row in evidence)
        assert all(row["after_facts"].get("resource_context_digest") for row in evidence)


@pytest.mark.parametrize("role,scope,expected", [
    ("project_manager", "system", 200), ("project_manager", "project", 200),
    ("finance_authority", "project", 200), ("finance_authority", "system", 404),
    ("finance_authority", "foreign", 404), ("operator", "system", 404),
    ("audit_authority", "project", 404),
])
async def test_project_export_requires_covering_pm_or_exact_project_finance(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle, role, scope, expected,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        project = h.submitter_record.project_id
        foreign = await create_project("Foreign export scope") if scope == "foreign" else None
        reader = await admin_access.signed.actor(f"export-reader-{role}-{scope}")
        await admin_access.signed.grant(admin_access.admin, reader, role=role,
                                       project_id=project if scope == "project" else foreign)
        response = await admin_access.signed.client.get(export_path(project), headers=reader.headers)
        assert response.status_code == expected, response.text
        event, = await export_audits(h.factory)
        assert event["after_facts"]["allowed"] is (expected == 200)
        if expected == 200:
            assert response.json()["items"][0]["contribution_id"] == str(h.submitter_record.id)
            assert event["project_id"] == str(project) and event["target_ref_id"] == str(project)
        else:
            assert event["project_id"] is event["resource_type"] is event["target_ref_id"] is None


async def test_self_read_cannot_substitute_another_contributor(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        other = await signed_access.actor("different-contributor")
        response = await signed_access.client.get(
            "/api/v1/actors/me/contributions", params={"actor_profile_id": str(h.submitter_record.contributor_id)},
            headers=other.headers,
        )
        assert response.status_code == 200 and response.json()["items"] == []
        event, = await export_audits(get_session_factory())
        assert event["resource_id"] == str(other.id)


@pytest.mark.parametrize("transition", ["profile", "identity_link"])
async def test_fresh_self_read_refuses_real_inactive_identity(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle, transition,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        actor = await source_actor(admin_access.signed, h)
        allowed = await admin_access.signed.client.get("/api/v1/actors/me/contributions", headers=actor.headers)
        assert allowed.status_code == 200, allowed.text
        path = f"/api/v1/actors/{actor.id}/suspend"
        if transition == "identity_link":
            async with h.factory() as session:
                link = await session.scalar(select(ActorIdentityLink).where(
                    ActorIdentityLink.actor_profile_id == str(actor.id),
                ))
                path = f"/api/v1/actor-identity-links/{link.id}/revoke"
        withdrawn = await admin_access.signed.client.post(
            path, headers=admin_access.admin.headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Withdraw contribution read identity"},
        )
        assert withdrawn.status_code == 200, withdrawn.text
        denied = await admin_access.signed.client.get("/api/v1/actors/me/contributions", headers=actor.headers)
        assert denied.status_code == 404, denied.text
        evidence = await export_audits(h.factory)
        assert len([row for row in evidence if row["after_facts"]["allowed"]]) == 1


async def test_service_claims_cannot_provision_a_contribution_reader(signed_access):
    token = issue_asymmetric_token(signed_access.private_key, scope="workstream:service", claims={
        "sub": "unprovisioned-contribution-reader", "subject_kind": "service",
        "roles": ["project_manager", "finance_authority"],
    })
    response = await signed_access.client.get(
        "/api/v1/actors/me/contributions", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403 and response.json()["error"]["code"] == "service_actor_not_provisioned", response.text
    async with get_session_factory()() as session:
        assert await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.subject == "unprovisioned-contribution-reader",
        )) is None


async def test_provisioned_service_cannot_read_project_contribution_facts(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        subject = "provisioned-contribution-denial-" + uuid4().hex
        provisioned = await admin_access.signed.client.post(
            "/api/v1/service-actors", headers=admin_access.admin.headers | {"Idempotency-Key": str(uuid4())},
            json={"service_identity": ServiceIdentity.REVIEW_PROJECTION.value, "subject": subject,
                  "reason": "Prove fixed service cannot disclose contribution evidence"},
        )
        assert provisioned.status_code == 201, provisioned.text
        token = issue_asymmetric_token(admin_access.signed.private_key, scope="workstream:service", claims={
            "sub": subject, "subject_kind": "service", "roles": ["project_manager", "finance_authority"],
        })
        denied = await admin_access.signed.client.get(
            export_path(h.submitter_record.project_id), headers={"Authorization": f"Bearer {token}"},
        )
        assert denied.status_code == 404, denied.text
        event, = await export_audits(h.factory)
        assert event["after_facts"]["allowed"] is False
        assert event["target_ref_id"] is event["project_id"] is None


async def test_export_audit_sql_requires_each_exact_allow_and_deny_pair(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle,
):
    """Bypass schema validation with real decision templates; roll all probes back."""
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        own = await source_actor(signed_access, h)
        other = await signed_access.actor("export-audit-sql-ungranted-human")
        allowed = await signed_access.client.get("/api/v1/actors/me/contributions", headers=own.headers)
        denied = await signed_access.client.get(export_path(h.submitter_record.project_id), headers=other.headers)
        assert allowed.status_code == 200, allowed.text
        assert denied.status_code == 404, denied.text
        before = await export_audits(h.factory)
        assert len(before) == 2
        statement = text("""
            INSERT INTO public.audit_events
            SELECT (jsonb_populate_record(NULL::public.audit_events,
                to_jsonb(a) || CAST(:changes AS jsonb))).*
            FROM public.audit_events a WHERE a.id=:source
        """)
        async with h.factory() as session:
            await session.begin()
            templates = (await session.execute(text("""
                SELECT id,event_type FROM public.audit_events
                WHERE action_id IN ('contribution.read_self','contribution.read_project')
                ORDER BY created_at,id
            """))).all()
            assert {row.event_type for row in templates} == {
                "SensitiveAuthorizationAllowed", "SensitiveAuthorizationDenied",
            }
            for template in templates:
                for action in ("contribution.read_self", "contribution.read_project"):
                    identity = new_record_id()
                    changes = {"id": str(identity), "entity_id": str(identity),
                               "action_id": action, "permission_id": action}
                    # These staged clones prove only SQL pair vocabulary, not runtime authority.
                    await session.execute(statement, {"source": template.id, "changes": json.dumps(changes)})
                    assert await session.scalar(text(
                        "SELECT count(*) FROM public.audit_events WHERE id=:id AND action_id=:action AND permission_id=:action"
                    ), {"id": identity, "action": action}) == 1
                    crossed = "contribution.read_project" if action.endswith("self") else "contribution.read_self"
                    for permission in (crossed, "project.read"):
                        refused_id = new_record_id()
                        changed = changes | {"id": str(refused_id), "entity_id": str(refused_id),
                                             "permission_id": permission}
                        with pytest.raises(DBAPIError, match="ck_audit_events_authorization_action_evidence"):
                            async with session.begin_nested():
                                await session.execute(statement, {
                                    "source": template.id, "changes": json.dumps(changed),
                                })
                        assert await session.scalar(text(
                            "SELECT count(*) FROM public.audit_events WHERE id=:id"
                        ), {"id": refused_id}) == 0
            await session.rollback()
        assert await export_audits(h.factory) == before
