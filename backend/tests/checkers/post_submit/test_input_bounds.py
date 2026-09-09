"""Finite detached values, strict numbers and a reachable aggregate byte boundary."""

import pytest
from pydantic import ValidationError

from app.modules.checkers.api import ExpectedPostSubmitContext, PostSubmissionStructuralInput
from app.modules.checkers.api.post_submit import (
    PostSubmitEvidenceEntry,
    PostSubmitManifestEntry,
    PostSubmitPolicyInputs,
)
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitResourceLimits,
    canonical_post_submit_bytes,
)
from tests.checkers.post_submit.support import HASH, change_request, request


@pytest.mark.parametrize("field", ("summary", "worker_attestation", "criteria"))
def test_structural_text_exact_limit_and_limit_plus_one(field):
    fields = request().structural_input.model_dump()
    fields[field] = "x" * 65536
    assert len(getattr(PostSubmissionStructuralInput(**fields), field)) == 65536
    fields[field] += "x"
    with pytest.raises(ValidationError, match="65536"):
        PostSubmissionStructuralInput(**fields)


@pytest.mark.parametrize(
    "kind,field,limit",
    [
        ("manifest", "artifact", 1000),
        ("manifest", "hash", 128),
        ("manifest", "notes", 4096),
        ("evidence", "label", 200),
        ("evidence", "uri", 1000),
        ("evidence", "hash", 128),
        ("evidence", "type", 200),
        ("evidence", "key", 200),
        ("evidence", "policy_key", 200),
        ("evidence", "evidence_key", 200),
        ("evidence", "required_evidence_key", 200),
    ],
)
def test_entry_text_bounds(kind, field, limit):
    cls = PostSubmitManifestEntry if kind == "manifest" else PostSubmitEvidenceEntry
    values = (
        dict(artifact="file", hash=HASH) if kind == "manifest" else dict(label="label", type="file")
    )
    values[field] = "x" * limit
    assert len(getattr(cls(**values), field)) == limit
    values[field] += "x"
    with pytest.raises(ValidationError):
        cls(**values)


@pytest.mark.parametrize("field", ("manifest", "evidence"))
def test_collection_limits_are_independent_of_request_aggregate(field):
    data = request().structural_input.model_dump()
    element = data[field][0]
    data[field] = (element,) * 1024
    assert len(getattr(PostSubmissionStructuralInput(**data), field)) == 1024
    data[field] += (element,)
    with pytest.raises(ValidationError, match="1024"):
        PostSubmissionStructuralInput(**data)


@pytest.mark.parametrize("field", tuple(PostSubmitPolicyInputs.model_fields))
def test_policy_input_count_and_token_limit(field):
    assert len(getattr(PostSubmitPolicyInputs(**{field: ("x",) * 256}), field)) == 256
    assert getattr(PostSubmitPolicyInputs(**{field: ("x" * 1000,)}), field)[0] == "x" * 1000
    for value in (("x",) * 257, ("x" * 1001,)):
        with pytest.raises(ValidationError):
            PostSubmitPolicyInputs(**{field: value})


@pytest.mark.parametrize("invalid", (True, -1, 9_223_372_036_854_775_808, "1"))
def test_strict_size_boundaries(invalid):
    for valid in (0, 9_223_372_036_854_775_807):
        assert (
            PostSubmitManifestEntry(artifact="x", hash=HASH, size_bytes=valid).size_bytes == valid
        )
        assert change_request(request(), byte_count=valid).byte_count == valid
    with pytest.raises(ValidationError):
        PostSubmitManifestEntry(artifact="x", hash=HASH, size_bytes=invalid)
    with pytest.raises(ValidationError):
        change_request(request(), byte_count=invalid)


def test_version_types_and_numeric_generations_match_existing_owners():
    base = request().expected_context.model_dump()
    expected = ExpectedPostSubmitContext(
        **{**base, "guide_version": "x" * 50, "post_policy_version": "x" * 50}
    )
    assert len(expected.guide_version) == 50
    for value in ("x" * 51, " ", 1):
        with pytest.raises(ValidationError):
            ExpectedPostSubmitContext(
                **{**base, "guide_version": value, "post_policy_version": value}
            )
    for field in ("review_generation", "revision_generation"):
        assert (
            getattr(ExpectedPostSubmitContext(**{**base, field: 2_147_483_647}), field)
            == 2_147_483_647
        )
        for value in (True, 0, 2_147_483_648, "1"):
            with pytest.raises(ValidationError):
                ExpectedPostSubmitContext(**{**base, field: value})
    for field in ("submission_version", "evaluation_generation"):
        assert getattr(change_request(request(), **{field: 2_147_483_647}), field) == 2_147_483_647
        with pytest.raises(ValidationError):
            change_request(request(), **{field: 2_147_483_648})


def test_nested_extra_fields_and_strict_resource_ids_deny():
    base = request()
    for owner in (
        base.structural_input,
        base.structural_input.policy_inputs,
        base.expected_context,
    ):
        with pytest.raises(ValidationError, match="Extra inputs"):
            type(owner)(**owner.model_dump(), unexpected={"private": "data"})
    with pytest.raises(ValidationError, match="UUID"):
        change_request(base, task_id=str(base.task_id))
    with pytest.raises(ValidationError):
        change_request(base, content_sha256="sha256:invalid")


@pytest.mark.parametrize(
    "field,maximum",
    [
        ("maximum_input_bytes", 1_048_576),
        ("maximum_result_bytes", 4096),
        ("deadline_ms", 5000),
        ("phase_deadline_ms", 45000),
        ("maximum_manifest_items", 1024),
        ("maximum_evidence_items", 1024),
        ("maximum_policy_items", 256),
        ("maximum_text_characters", 65536),
    ],
)
def test_catalogue_resource_limits_match_exact_enforced_contract(field, maximum):
    assert getattr(PostSubmitResourceLimits(**{field: maximum}), field) == maximum
    for value in (True, 0, maximum - 1, maximum + 1, float(maximum), str(maximum)):
        with pytest.raises(ValidationError):
            PostSubmitResourceLimits(**{field: value})


def test_request_aggregate_exact_limit_and_one_byte_over():
    source = request()
    data = source.structural_input.model_dump()
    data["summary"] = ""
    # Each item remains within its own limit; only the aggregate boundary varies.
    data["manifest"] = tuple(
        {"artifact": f"entry{i}", "hash": HASH, "notes": "x" * 3800, "size_bytes": 0}
        for i in range(260)
    )
    small = change_request(source, structural_input=data)
    delta = 1_048_576 - len(canonical_post_submit_bytes(small))
    assert 0 < delta < 65536
    data["summary"] = "x" * delta
    exact = change_request(source, structural_input=data)
    assert len(canonical_post_submit_bytes(exact)) == 1_048_576
    data["summary"] += "x"
    with pytest.raises(ValidationError, match="request capacity exceeded"):
        change_request(source, structural_input=data)
