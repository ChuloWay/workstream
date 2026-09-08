"""Actual policy writer semantics with bounded repository/authority doubles."""

from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.projects.policy_mutation_service import (
    NO_CURRENT_POLICY_ETAG,
    PolicyMutationConflict,
    policy_selector_etag,
)
from app.modules.projects.schemas import ReviewPolicyInput, ReviewPolicyResponse
from test_project_policy_mutations import _subject, _review_payload


def _payload(value=None):
    values = _review_payload().model_dump(exclude={"human_review_required"})
    if value is not None:
        values["human_review_required"] = value
    return ReviewPolicyInput.model_validate(values)


async def _write(case, payload, key=None, etag=None):
    service, resolved, prepared, _, repository, project_id, guide_id = case
    current = repository.review
    if etag is None:
        etag = (
            NO_CURRENT_POLICY_ETAG
            if current is None
            else policy_selector_etag(current.id, current.policy_generation, current.policy_hash)
        )
    return await service.replace_review_policy(
        resolved, prepared, key or uuid4(), etag, project_id, guide_id, payload
    )


@pytest.mark.parametrize("value", [None, True, False])
async def test_creation_persists_and_returns_exact_mode(value):
    case = _subject()
    result = await _write(case, _payload(value))
    expected = value if value is not None else True
    assert result.response.human_review_required is expected
    assert result.response.semantics_format == "v2"
    assert case[4].review.human_review_required is expected
    resource = case[2].consumed[0][3]
    assert resource.policy_digest == result.response.policy_hash
    assert resource.predecessor_policy_id is None


@pytest.mark.parametrize("value,expected", [(None, False), (True, True), (False, False)])
async def test_false_predecessor_omission_or_override_only_changes_new_version(value, expected):
    case = _subject()
    first = await _write(case, _payload(False))
    old_row = case[4].review
    old_facts = deepcopy(first.response.model_dump())
    second = await _write(case, _payload(value))
    assert second.response.human_review_required is expected
    assert second.response.supersedes_policy_id == first.response.id
    assert second.response.policy_generation == 2
    assert second.response.policy_hash == case[2].consumed[-1][3].policy_digest
    assert ReviewPolicyResponse.model_validate(old_row).model_dump() == old_facts
    assert (second.response.policy_hash == first.response.policy_hash) is (not expected)


async def test_omitted_retry_recovers_original_false_after_selector_advances():
    case = _subject()
    await _write(case, _payload(False))
    prior = case[4].review
    etag = policy_selector_etag(prior.id, prior.policy_generation, prior.policy_hash)
    key = uuid4()
    original = await _write(case, _payload(), key, etag)
    await _write(case, _payload(True))
    count = len(case[2].consumed)
    replay = await _write(case, _payload(), key, etag)
    assert replay.replayed
    assert replay.response == original.response
    assert replay.response.human_review_required is False
    assert len(case[2].consumed) == count
    with pytest.raises(PolicyMutationConflict, match="idempotency_mismatch"):
        await _write(case, _payload(True), key, etag)
    assert case[4].review.human_review_required is True


async def test_legacy_response_recovery_defaults_true_and_retains_v1_hash():
    case = _subject()
    key = uuid4()
    result = await _write(case, _payload(), key)
    record = next(iter(case[3].records.values()))
    # Model historical stored replay JSON, whose omitted request shape is unchanged.
    old = result.response.model_dump(
        mode="json", exclude={"human_review_required", "semantics_format"}
    )
    from app.modules.projects.policy_lineage import ReviewPolicySemantics, policy_digest

    old["policy_hash"] = policy_digest(
        "review",
        ReviewPolicySemantics.model_validate(_payload().model_dump()),
        review_semantics_format="v1",
    )
    record.response_json = old
    record.policy_hash = old["policy_hash"]

    async def unexpected_lookup(*_):
        raise AssertionError("exact replay must precede current policy lookup")

    case[4].get_guide = unexpected_lookup
    replay = await _write(case, _payload(), key, NO_CURRENT_POLICY_ETAG)
    assert replay.replayed
    assert replay.response.human_review_required is True
    assert replay.response.semantics_format == "v1"
    assert replay.response.policy_hash == old["policy_hash"]
    assert len(case[2].consumed) == 1


async def test_v2_response_cannot_omit_mode_or_claim_legacy_false():
    case = _subject()
    response = (await _write(case, _payload(False))).response.model_dump()
    with pytest.raises(ValidationError, match="explicit human_review_required"):
        ReviewPolicyResponse.model_validate(
            {k: v for k, v in response.items() if k != "human_review_required"}
        )
    with pytest.raises(ValidationError, match="legacy review policy"):
        ReviewPolicyResponse.model_validate({**response, "semantics_format": "v1"})


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", "foreign"),
        ("guide_version", "v2"),
        ("policy_generation", 12),
        ("policy_hash", "sha256:" + "a" * 64),
        ("id", str(uuid4())),
    ],
)
async def test_omission_rejects_foreign_or_stale_predecessor_before_authority(field, value):
    case = _subject()
    await _write(case, _payload(False))
    current = case[4].review
    etag = policy_selector_etag(current.id, current.policy_generation, current.policy_hash)
    setattr(current, field, value)
    with pytest.raises(PolicyMutationConflict, match="policy_precondition_failed"):
        await _write(case, _payload(), etag=etag)
    assert len(case[2].consumed) == 1
    assert case[3].completed == 1
