"""Close the v0.1 project-role contract to submitter and reviewer."""

from alembic import op
import sqlalchemy as sa

revision = "0014_project_role_scope"
down_revision = "0013_compilation_request_origin"
branch_labels = None
depends_on = None

_PROJECT_ROLES_WITH_ADJUDICATOR = "array['submitter','reviewer','adjudicator']"
_PROJECT_ROLES = "array['submitter','reviewer']"
_INVALIDATION_ADJUDICATOR = (
    "\n                  or (before_state::jsonb->>'role'='adjudicator' and "
    "before_state::jsonb->>'future_obligation'='none')"
)
_LINKED_EVENT_ROLES_WITH_ADJUDICATOR = "not in ('submitter','reviewer','adjudicator')"
_LINKED_EVENT_ROLES = "not in ('submitter','reviewer')"
_LINKED_EVENT_ADJUDICATOR = (
    "\n               or (new.before_facts::jsonb->>'role'='adjudicator' and "
    "new.before_facts::jsonb->>'future_obligation'<>'none')"
)


def _function_definition(signature: str) -> str:
    definition = op.get_bind().execute(
        sa.text("select pg_get_functiondef(to_regprocedure(:signature))"),
        {"signature": signature},
    ).scalar_one_or_none()
    if definition is None:
        raise RuntimeError("project-role audit function is unavailable")
    return definition


def _replace_exact(
    definition: str,
    *,
    old: str,
    new: str,
    count: int,
    owner: str,
) -> str:
    if definition.count(old) != count or (new and definition.count(new) != 0):
        raise RuntimeError(f"{owner} shape changed")
    return definition.replace(old, new)


def _amend_audit_functions(*, narrow: bool) -> None:
    event_definition = _function_definition(
        "public.authority_event_facts_are_safe(text,json,json,text)"
    )
    linked_definition = _function_definition("public.validate_linked_authority_event()")
    if narrow:
        event_definition = _replace_exact(
            event_definition,
            old=_PROJECT_ROLES_WITH_ADJUDICATOR,
            new=_PROJECT_ROLES,
            count=3,
            owner="authority event role vocabulary",
        )
        event_definition = _replace_exact(
            event_definition,
            old=_INVALIDATION_ADJUDICATOR,
            new="",
            count=1,
            owner="authority invalidation role vocabulary",
        )
        linked_definition = _replace_exact(
            linked_definition,
            old=_LINKED_EVENT_ROLES_WITH_ADJUDICATOR,
            new=_LINKED_EVENT_ROLES,
            count=1,
            owner="linked authority event role vocabulary",
        )
        linked_definition = _replace_exact(
            linked_definition,
            old=_LINKED_EVENT_ADJUDICATOR,
            new="",
            count=1,
            owner="linked authority invalidation vocabulary",
        )
    else:
        event_definition = _replace_exact(
            event_definition,
            old=_PROJECT_ROLES,
            new=_PROJECT_ROLES_WITH_ADJUDICATOR,
            count=3,
            owner="authority event role vocabulary",
        )
        event_definition = _replace_exact(
            event_definition,
            old=(
                "\n                  or (before_state::jsonb->>'role'='reviewer' and "
                "before_state::jsonb->>'future_obligation'='rev_reviewer_obligation')"
            ),
            new=(
                "\n                  or (before_state::jsonb->>'role'='reviewer' and "
                "before_state::jsonb->>'future_obligation'='rev_reviewer_obligation')"
                + _INVALIDATION_ADJUDICATOR
            ),
            count=1,
            owner="authority invalidation role vocabulary",
        )
        linked_definition = _replace_exact(
            linked_definition,
            old=_LINKED_EVENT_ROLES,
            new=_LINKED_EVENT_ROLES_WITH_ADJUDICATOR,
            count=1,
            owner="linked authority event role vocabulary",
        )
        linked_definition = _replace_exact(
            linked_definition,
            old=(
                "\n               or (new.before_facts::jsonb->>'role'='reviewer' and "
                "new.before_facts::jsonb->>'future_obligation'<>'rev_reviewer_obligation')"
            ),
            new=(
                "\n               or (new.before_facts::jsonb->>'role'='reviewer' and "
                "new.before_facts::jsonb->>'future_obligation'<>'rev_reviewer_obligation')"
                + _LINKED_EVENT_ADJUDICATOR
            ),
            count=1,
            owner="linked authority invalidation vocabulary",
        )
    op.execute(event_definition)
    op.execute(linked_definition)


def _role_constraint_definition(table: str, constraint: str) -> str:
    definition = op.get_bind().execute(
        sa.text(
            "select pg_get_constraintdef(c.oid) from pg_constraint c "
            "join pg_class t on t.oid=c.conrelid "
            "join pg_namespace n on n.oid=t.relnamespace "
            "where n.nspname='public' and t.relname=:table and c.conname=:constraint"
        ),
        {"table": table, "constraint": constraint},
    ).scalar_one_or_none()
    if definition is None:
        raise RuntimeError("project-role persistence constraint is unavailable")
    return definition


def _replace_role_constraints(*, narrow: bool) -> None:
    constraints = (
        ("project_role_grants", "ck_project_role_grants_role"),
        (
            "project_role_qualification_snapshots",
            "ck_project_role_qualification_snapshots_role",
        ),
    )
    anchor = "('reviewer'::character varying)::text"
    token = ", ('adjudicator'::character varying)::text"
    old = token if narrow else anchor
    new = "" if narrow else anchor + token
    amended: list[tuple[str, str, str]] = []
    for table, constraint in constraints:
        definition = _role_constraint_definition(table, constraint)
        amended.append(
            (
                table,
                constraint,
                _replace_exact(
                    definition,
                    old=old,
                    new=new,
                    count=1,
                    owner=constraint,
                ),
            )
        )
    for table, constraint, definition in amended:
        op.execute(f"alter table {table} drop constraint {constraint}")
        op.execute(f"alter table {table} add constraint {constraint} {definition}")


def _lock_role_contracts() -> None:
    op.get_bind().execute(
        sa.text(
            "lock table project_role_qualification_snapshots, project_role_grants, "
            "audit_events in access exclusive mode"
        )
    )


def _refuse_incompatible_history() -> None:
    incompatible = op.get_bind().execute(
        sa.text(
            "select "
            "exists(select 1 from project_role_qualification_snapshots "
            "where requested_role='adjudicator') or "
            "exists(select 1 from project_role_grants where role='adjudicator') or "
            "exists(select 1 from audit_events where event_domain='authority' and "
            "(before_facts::jsonb->>'role'='adjudicator' or "
            "after_facts::jsonb->>'role'='adjudicator'))"
        )
    ).scalar_one()
    if incompatible:
        raise RuntimeError("retained adjudicator authority history prevents role narrowing")


def upgrade() -> None:
    """Narrow current roles only when every retained authority fact is compatible."""
    _lock_role_contracts()
    _refuse_incompatible_history()
    _amend_audit_functions(narrow=True)
    _replace_role_constraints(narrow=True)


def downgrade() -> None:
    """Restore the former role vocabulary without deleting or relabeling retained facts."""
    _lock_role_contracts()
    _amend_audit_functions(narrow=False)
    _replace_role_constraints(narrow=False)
