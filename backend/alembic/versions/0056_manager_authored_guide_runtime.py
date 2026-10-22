"""Admit the provider-free manager-authored guide runtime.

The runtime records provider, API and model ``none`` and allocates no provider
resources. Its document reads therefore carry no attachment allocation. Every
other runtime keeps the strict OpenAI Responses identity, may not use the
provider-free model ``none``, and keeps the full container/file/attachment
lineage for each document read.

A provider-free attempt may also return from ``compilation_provider_uncertain``
to ``compilation_reserved``. Its dispatch fence guards no provider call, so a
transient document or storage failure must stay retryable rather than strand
the guide. Hosted attempts keep the one-way fence.
"""

from alembic import op
from sqlalchemy import text

revision = "0056_manager_authored_runtime"
down_revision = "0055_delivery_reconciliation"
branch_labels = None
depends_on = None

_CONFIGURATION_GUARD = "public.guard_project_guide_runtime_configuration()"
_ALLOCATION_GUARD = "public.guard_guide_runtime_allocation()"
_ATTEMPT_GUARD = "public.guard_project_guide_compilation_attempt_update()"
_ACCESS_GUARD = "public.guard_guide_document_access()"

_PROVIDER_PREDECESSOR = (
    "or config->>'model_provider' is distinct from 'openai'\n"
    "           or config->>'model_api' is distinct from 'responses'\n"
)
# Null-safe comparisons: a missing or JSON-null member must reject, not yield NULL.
_PROVIDER_CURRENT = (
    "or not ((config->>'runtime_key' is distinct from 'manager_authored'\n"
    "                    and config->>'model_provider' is not distinct from 'openai'\n"
    "                    and config->>'model_api' is not distinct from 'responses'\n"
    "                    and config->>'model' is distinct from 'none')\n"
    "                or (config->>'runtime_key' is not distinct from 'manager_authored'\n"
    "                    and config->>'model_provider' is not distinct from 'none'\n"
    "                    and config->>'model_api' is not distinct from 'none'\n"
    "                    and config->>'model' is not distinct from 'none'))\n"
)

_ALLOCATION_PREDECESSOR = (
    "        if tg_op='INSERT' then\n"
    "          if attempt.status <> 'compilation_provider_uncertain'"
)
_ALLOCATION_CURRENT = (
    "        if tg_op='INSERT' then\n"
    "          if attempt.runtime_configuration->>'model_provider' is not distinct from 'none' then\n"
    "            raise exception 'provider-free guide runtime allocates no provider resources'\n"
    "              using errcode='23514';\n"
    "          end if;\n"
    "          if attempt.status <> 'compilation_provider_uncertain'"
)

_ACCESS_PREDECESSOR = (
    "           or new.manifest_sha256 is distinct from attempt.guide_material_hash\n"
    "           or not exists(select 1 from project_guide_runtime_allocations resource\n"
)
_ACCESS_CURRENT = (
    "           or new.manifest_sha256 is distinct from attempt.guide_material_hash\n"
    "           or (new.attachment_allocation_id is null and (\n"
    "             attempt.runtime_configuration->>'model_provider' is distinct from 'none'\n"
    "             or new.document_handle is distinct from canonical_guide_document_handle(\n"
    "               attempt.setup_run_id::uuid, new.source_item_id, new.document_version_id)\n"
    "             or not exists(select 1 from guide_source_snapshot_items item\n"
    "               join guide_source_artifact_ingests ingest on ingest.source_item_id=item.id\n"
    "               where item.id=new.source_item_id\n"
    "                 and item.source_snapshot_id=attempt.source_snapshot_id\n"
    "                 and item.source_kind='document' and item.ingestion_adapter='upload'\n"
    "                 and ingest.id=new.document_version_id and ingest.sha256=new.sha256)))\n"
    "           or (new.attachment_allocation_id is not null\n"
    "             and not exists(select 1 from project_guide_runtime_allocations resource\n"
)
_ACCESS_TAIL_PREDECESSOR = (
    "               and container.provider_id=resource.parent_provider_id) then\n"
)
_ACCESS_TAIL_CURRENT = (
    "               and container.provider_id=resource.parent_provider_id)) then\n"
)


_PROVIDER_FREE_RELEASE = (
    "(old.status='compilation_provider_uncertain' and new.status='compilation_reserved'\n"
    "              and new.provider_uncertain_at is null\n"
    "              and old.runtime_configuration->>'model_provider' is not distinct from 'none')"
)
_UNCERTAIN_AT_PREDECESSOR = (
    "not (old.status='compilation_reserved' and new.status='compilation_provider_uncertain') then"
)
_UNCERTAIN_AT_CURRENT = (
    "not ((old.status='compilation_reserved' and new.status='compilation_provider_uncertain')\n"
    "            or " + _PROVIDER_FREE_RELEASE + ") then"
)
_TRANSITION_PREDECESSOR = (
    "(old.status='compilation_provider_uncertain' and new.status in "
    "('provider_result_accepted','compilation_invalid_terminal')) or"
)
_TRANSITION_CURRENT = _TRANSITION_PREDECESSOR + "\n                  " + _PROVIDER_FREE_RELEASE + " or"


def _replace_function(signature: str, *replacements: tuple[str, str]) -> None:
    """Refuse to modify an unexpected predecessor custody function."""
    body = op.get_bind().execute(
        text("select pg_catalog.pg_get_functiondef(cast(:signature as regprocedure))"),
        {"signature": signature},
    ).scalar_one()
    for old, new in replacements:
        if body.count(old) != 1:
            raise RuntimeError("manager-authored runtime predecessor changed: " + signature)
        body = body.replace(old, new)
    op.execute(body)


def upgrade() -> None:
    op.execute("set local search_path = pg_catalog, public, pg_temp")
    _replace_function(_CONFIGURATION_GUARD, (_PROVIDER_PREDECESSOR, _PROVIDER_CURRENT))
    _replace_function(
        _ATTEMPT_GUARD,
        (_UNCERTAIN_AT_PREDECESSOR, _UNCERTAIN_AT_CURRENT),
        (_TRANSITION_PREDECESSOR, _TRANSITION_CURRENT),
    )
    _replace_function(_ALLOCATION_GUARD, (_ALLOCATION_PREDECESSOR, _ALLOCATION_CURRENT))
    _replace_function(
        _ACCESS_GUARD,
        (_ACCESS_PREDECESSOR, _ACCESS_CURRENT),
        (_ACCESS_TAIL_PREDECESSOR, _ACCESS_TAIL_CURRENT),
    )
    op.execute(
        "alter table public.project_guide_document_accesses "
        "alter column attachment_allocation_id drop not null"
    )


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
