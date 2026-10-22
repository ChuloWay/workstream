"""Admit authorized project points-unit creation and its immutable creation events.

Adds the ``contribution.compensation_unit.create`` action to the closed
action/permission audit vocabulary and the append-only table that lets an
identical request replay its original result. Existing units and audit rows are
unchanged.
"""

from alembic import op
from sqlalchemy import text

revision = "0058_compensation_unit_create"
down_revision = "0057_roles_anywhere_custody"
branch_labels = None
depends_on = None

_ACTION = ("contribution.compensation_unit.create", "compensation.policy.manage")
_ANCHOR = (
    "(((action_id)::text = 'contribution.policy.retire'::text) AND "
    "((permission_id)::text = 'compensation.policy.manage'::text))"
)

_EVENT_TABLE = """
CREATE TABLE public.project_compensation_unit_creation_events (
  id uuid NOT NULL,
  operation_id uuid NOT NULL,
  request_digest character varying(71) NOT NULL,
  actor_profile_id uuid NOT NULL,
  project_id uuid NOT NULL,
  instrument_type character varying(32) NOT NULL,
  unit_code character varying(32) NOT NULL,
  occurred_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
  CONSTRAINT pk_project_compensation_unit_creation_events PRIMARY KEY (id),
  CONSTRAINT ck_project_compensation_unit_creation_events_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
  CONSTRAINT ck_project_compensation_unit_creation_events_request_digest CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
  CONSTRAINT ck_project_compensation_unit_creation_events_instrument_type CHECK (instrument_type = 'project_points'),
  CONSTRAINT uq_project_compensation_unit_creation_operation UNIQUE (operation_id),
  CONSTRAINT uq_project_compensation_unit_creation_unit UNIQUE (project_id, instrument_type, unit_code),
  CONSTRAINT fk_project_compensation_unit_creation_actor FOREIGN KEY (actor_profile_id) REFERENCES public.actor_profiles(id),
  CONSTRAINT fk_project_compensation_unit_creation_project FOREIGN KEY (project_id) REFERENCES public.projects(id),
  CONSTRAINT fk_project_compensation_unit_creation_unit FOREIGN KEY (project_id, instrument_type, unit_code)
    REFERENCES public.project_compensation_units(project_id, instrument_type, unit_code)
);
"""

_GUARDS = (
    """
CREATE FUNCTION public.guard_project_compensation_unit_creation_event() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE unit public.project_compensation_units;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'project compensation-unit creation events are immutable'
      USING ERRCODE='55000';
  END IF;
  SELECT * INTO unit FROM public.project_compensation_units
    WHERE project_id=NEW.project_id AND instrument_type=NEW.instrument_type
      AND unit_code=NEW.unit_code;
  IF NOT FOUND OR unit.status IS DISTINCT FROM 'active'
     OR unit.created_by IS DISTINCT FROM NEW.actor_profile_id THEN
    RAISE EXCEPTION 'invalid project compensation-unit creation event' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$
""",
    "CREATE TRIGGER project_compensation_unit_creation_event_guard BEFORE INSERT OR DELETE OR UPDATE"
    " ON public.project_compensation_unit_creation_events FOR EACH ROW"
    " EXECUTE FUNCTION public.guard_project_compensation_unit_creation_event()",
    "CREATE TRIGGER project_compensation_unit_creation_event_no_truncate BEFORE TRUNCATE"
    " ON public.project_compensation_unit_creation_events FOR EACH STATEMENT"
    " EXECUTE FUNCTION public.guard_project_compensation_unit_creation_event()",
)


def upgrade() -> None:
    """Extend the closed audit vocabulary, then add the guarded creation-event table."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute("LOCK TABLE public.audit_events IN ACCESS EXCLUSIVE MODE")
    name = "ck_audit_events_authorization_action_evidence"
    definition = op.get_bind().execute(text(
        "SELECT pg_catalog.pg_get_constraintdef(oid) FROM pg_catalog.pg_constraint "
        "WHERE conrelid='public.audit_events'::regclass AND conname=:name"
    ), {"name": name}).scalar_one()
    action, permission = _ACTION
    if definition.count(_ANCHOR) != 2 or action in definition:
        raise RuntimeError("compensation-unit audit action constraint shape changed")
    addition = (
        f" OR (((action_id)::text = '{action}'::text) AND "
        f"((permission_id)::text = '{permission}'::text))"
    )
    op.execute("ALTER TABLE public.audit_events DROP CONSTRAINT " + name)
    op.execute("ALTER TABLE public.audit_events ADD CONSTRAINT " + name + " "
               + definition.replace(_ANCHOR, _ANCHOR + addition))
    op.execute(_EVENT_TABLE)
    for statement in _GUARDS:
        op.execute(statement)


def downgrade() -> None:
    """Refuse removal of immutable unit-creation evidence."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
