"""Exact identity vectors, complete canonical digests and nominal authority."""

from copy import copy, deepcopy
from dataclasses import fields, replace
import hashlib
import json
import pickle
from uuid import UUID, uuid4

import pytest

from app.modules.authorization.api import (
    ProjectSetupFinalizationFacts,
    ProjectSetupFinalizationLocator,
    setup_finalization_fact_values,
    setup_finalization_facts_digest,
    setup_finalization_identity,
)
from app.modules.projects.api import (
    ProjectGuideSetupFinalizationCommand,
    ProjectGuideSetupFinalizationError,
)
from app.modules.projects.guide_compilation import finalization
from .support import Prepared, scenario


def mutated(facts, field):
    value = getattr(facts, field)
    if isinstance(value, UUID):
        return uuid4()
    if field == "component_hashes":
        return ((value[0][0], "sha256:" + "f" * 64), *value[1:])
    if type(value) is int:
        return value + 1
    if field.endswith(("hash", "digest")):
        return "sha256:" + "f" * 64
    return "changed"


def test_finalization_identity_uses_exact_uuid5_namespaces_and_seed():
    identities = setup_finalization_identity(
        UUID("11111111-1111-4111-8111-111111111111"),
        2,
        UUID("33333333-3333-4333-8333-333333333333"),
    )
    assert tuple(map(str, identities)) == (
        "38b5b694-2802-53b4-958a-3df7d4a2faf0",
        "61c2c6fd-634e-538f-a92d-3d62f42e0024",
        "d825a8b2-a9ad-5f54-831c-0af0e4e18910",
    )


@pytest.mark.parametrize("index", [0, 1, 2])
def test_identity_rejects_invalid_seed(index):
    values = [uuid4(), 1, uuid4()]
    values[index] = False if index == 1 else "not-parsed"
    with pytest.raises(ValueError):
        setup_finalization_identity(*values)


@pytest.mark.parametrize("field", [f.name for f in fields(ProjectSetupFinalizationFacts)])
def test_each_finalization_digest_field_changes_hash(field):
    facts = scenario().auth.expected
    changed = deepcopy(facts)
    object.__setattr__(changed, field, mutated(facts, field))
    assert setup_finalization_facts_digest(changed) != setup_finalization_facts_digest(facts)


@pytest.mark.parametrize("field", [f.name for f in fields(ProjectSetupFinalizationFacts)])
async def test_each_finalization_fact_mutation_denies(field, monkeypatch):
    case = scenario()
    changed = deepcopy(case.auth.expected)
    object.__setattr__(changed, field, mutated(changed, field))
    monkeypatch.setattr(finalization, "compose_facts", lambda *_args: changed)
    with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
        await case.service.finalize(case.command)
    assert "persist" not in case.repo.calls
    assert case.auth.events == ["prepare", "consume", "close"]


def test_digest_uses_canonical_utf8_explicit_nulls_and_all_keys():
    facts = scenario("guide_blocked").auth.expected
    body = setup_finalization_fact_values(facts)
    assert set(body) == {f.name for f in fields(facts)}
    assert body["artifact_policy_id"] is None
    encoded = json.dumps(
        {"domain": "workstream.project_guide_setup_finalization.facts.v1", "facts": body},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert setup_finalization_facts_digest(facts) == "sha256:" + hashlib.sha256(encoded).hexdigest()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", "not-parsed"),
        ("setup_generation", True),
        ("setup_generation", 0),
        ("result_hash", "SHA256:" + "a" * 64),
        ("guide_version", ""),
        ("guide_version", "x" * 161),
        ("component_hashes", {}),
        ("component_hashes", ()),
        ("component_hashes", (("wrong", "sha256:" + "f" * 64),)),
        ("artifact_policy_id", None),
        ("result_classification", "unsafe"),
        ("setup_outcome", "sufficiency_blocked"),
    ],
)
def test_facts_reject_noncanonical_or_partial_values(field, value):
    facts = scenario().auth.expected
    with pytest.raises(ValueError):
        replace(facts, **{field: value})


def test_component_hash_values_and_order_are_validated():
    facts = scenario().auth.expected
    for pairs in (
        tuple(reversed(facts.component_hashes)),
        ((facts.component_hashes[0][0], "invalid"), *facts.component_hashes[1:]),
    ):
        with pytest.raises(ValueError):
            replace(facts, component_hashes=pairs)


def test_locator_accepts_only_parsed_ids():
    with pytest.raises(ValueError):
        ProjectSetupFinalizationLocator(project_id="wrong", operation_id=uuid4(), correlation_id=uuid4())


@pytest.mark.parametrize("operation", [copy, deepcopy, pickle.dumps])
def test_prepared_authority_cannot_be_copied_or_serialized(operation):
    handle = Prepared(scenario().auth)
    with pytest.raises(TypeError):
        operation(handle)


async def test_closed_authority_is_unusable_after_root_change():
    case = scenario()
    await case.service.finalize(case.command)
    case.session.root = object()
    with pytest.raises(Exception, match="prepared binding invalid"):
        await case.auth.handles[0].consume_new(case.auth.expected)


def test_public_command_has_no_caller_authority_or_time_fields():
    case = scenario()
    assert set(ProjectGuideSetupFinalizationCommand.model_fields) == {
        "project_id",
        "guide_id",
        "setup_run_id",
        "setup_generation",
        "compilation_id",
    }
    with pytest.raises(ValueError):
        ProjectGuideSetupFinalizationCommand(**case.command.model_dump(), finished_at="forged")
