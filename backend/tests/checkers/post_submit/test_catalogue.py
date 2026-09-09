"""Registry installation, identity, and single-handler installation proof."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.post_submit_catalogue import (
    structural_definition,
    PostSubmitCatalogue,
    PostSubmitDefinition,
)
from app.modules.checkers.post_submit_catalogue import (
    build_post_submit_catalogue,
)
from app.modules.checkers.runner import (
    CheckerNameConflict,
    CheckerRegistry,
    FunctionChecker,
    UnknownChecker,
    check_policy_context_present,
    default_checker_registry,
)
from tests.checkers.post_submit.support import altered_catalogue, catalogue


def test_catalogue_matches_exactly_one_registered_handler_per_id():
    registry = default_checker_registry()
    snapshot = build_post_submit_catalogue(registry)
    assert len(snapshot.definitions) == 9
    assert len(registry._checkers) == 9
    for definition in snapshot.definitions:
        entry = registry.resolve(definition.capability_id)
        assert entry.definition == definition
        assert entry.checker.name == definition.capability_id
    entry = registry.resolve("check_policy_context_present")
    assert entry.checker._handler is check_policy_context_present
    assert entry.definition in snapshot.definitions
    assert registry.names() == {item.capability_id for item in snapshot.definitions}


@pytest.mark.parametrize("damage", ("missing", "version", "identity"))
def test_catalogue_rejects_uninstalled_or_mismatched_handler(damage):
    registry = default_checker_registry()
    key = "check_submission_packet"
    entry = registry._checkers.pop(key)
    if damage == "version":
        registry._checkers[key] = replace(
            entry,
            definition=entry.definition.model_copy(update={"implementation_version": "wrong"}),
        )
    elif damage == "identity":
        registry._checkers[key] = replace(
            entry, checker=FunctionChecker("other", entry.checker._handler)
        )
    with pytest.raises((ValueError, UnknownChecker), match="incomplete|unregistered|mismatch"):
        build_post_submit_catalogue(registry)


def test_registry_rejects_duplicates_and_metadata_substitution():
    registry = default_checker_registry()
    checker = registry.resolve("check_submission_packet").checker
    with pytest.raises(CheckerNameConflict, match="already registered"):
        registry.register(checker, definition=structural_definition(checker.name))
    with pytest.raises(ValueError, match="definition mismatch"):
        CheckerRegistry().register(
            checker, definition=structural_definition("check_required_files")
        )
    with pytest.raises(UnknownChecker, match="unregistered checker policy names"):
        registry.require_registered({"missing"})
    with pytest.raises(ValueError, match="unknown structural"):
        structural_definition("missing")


@pytest.mark.parametrize(
    "change",
    [
        {"state": "disabled"},
        {"implementation_version": "another-implementation"},
        {"supported_claim": "packet_presence"},
        {"dependencies": ["check_submission_packet"]},
    ],
)
def test_catalogue_hash_binds_semantics(change):
    original = catalogue()
    changed = altered_catalogue(original, **change)
    assert changed.manifest_sha256 != original.manifest_sha256
    assert catalogue().manifest_sha256 == original.manifest_sha256
    exported = original.model_dump(mode="json")
    exported["definitions"][0]["state"] = "disabled"
    assert original.definitions[0].resources.deadline_ms == 5000
    with pytest.raises(ValidationError, match="hash mismatch"):
        PostSubmitCatalogue.model_validate(exported)


@pytest.mark.parametrize(
    "kind", ("duplicate", "order", "dependency", "hash", "classification", "severity")
)
def test_invalid_catalogue_shape(kind):
    body = catalogue().model_dump(mode="json", exclude={"manifest_sha256"})
    if kind == "duplicate":
        body["definitions"][1]["capability_id"] = body["definitions"][0]["capability_id"]
    elif kind == "order":
        body["definitions"][0]["order"] = 9
    elif kind == "dependency":
        body["definitions"][0]["dependencies"] = ["missing"]
    elif kind == "classification":
        body["definitions"][0]["selectable"] = True
    elif kind == "severity":
        body["definitions"][0]["failure_severity"] = "medium"
    digest = "sha256:" + "0" * 64 if kind == "hash" else canonical_json_hash(body)
    with pytest.raises(ValidationError):
        PostSubmitCatalogue(**body, manifest_sha256=digest)


def test_definition_validates_boolean_resource_limits_and_unknown_fields():
    definition = catalogue().definitions[0].model_dump()
    definition["resources"] = {"maximum_results": True}
    with pytest.raises(ValidationError, match="require integers"):
        PostSubmitDefinition(**definition)
    with pytest.raises(ValidationError, match="Extra inputs"):
        PostSubmitDefinition(**catalogue().definitions[0].model_dump(), arbitrary="secret")


def test_hash_valid_catalogue_rejects_duplicate_dependencies():
    body = catalogue().model_dump(mode="json", exclude={"manifest_sha256"})
    dependency = body["definitions"][0]["capability_id"]
    body["definitions"][1]["dependencies"] = [dependency, dependency]
    with pytest.raises(ValidationError, match="definition has duplicate dependencies"):
        PostSubmitCatalogue(**body, manifest_sha256=canonical_json_hash(body))
