"""Current activation checks exact versioned semantics before mode availability."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.modules.projects.policy_lineage import (
    ReviewPolicySemantics,
    RevisionPolicySemantics,
    policy_digest,
)
from app.modules.projects.service import GuideActivationBlocked, ProjectService
from projects.test_activation_readiness import _activation_ready_bundle
from test_project_policy_mutations import _review_payload, _revision_payload


@pytest.mark.parametrize("format", ["v1", "v2"])
def test_current_validator_accepts_true_then_rejects_valid_false(monkeypatch, format):
    bundle = _activation_ready_bundle()
    review = ReviewPolicySemantics.model_validate(_review_payload().model_dump())
    revision = RevisionPolicySemantics.model_validate(_revision_payload().model_dump())
    bundle["review_policy"] = SimpleNamespace(
        **review.model_dump(),
        semantics_status="complete",
        semantics_format=format,
        policy_hash=policy_digest("review", review, review_semantics_format=format),
    )
    bundle["revision_policy"] = SimpleNamespace(
        **revision.model_dump(),
        semantics_status="complete",
        policy_hash=policy_digest("revision", revision),
    )
    service = ProjectService(None)
    monkeypatch.setattr(
        service,
        "_merge_effective_submission_artifact_policy",
        lambda _: deepcopy(bundle["effective_policy"].effective_policy),
    )
    # The complete-policy validator remains real for both the positive and negative.
    service.validate_activation_ready(**bundle)
    false = ReviewPolicySemantics.model_validate(
        {**review.model_dump(), "human_review_required": False}
    )
    bundle["review_policy"] = SimpleNamespace(
        **false.model_dump(),
        semantics_status="complete",
        semantics_format="v2",
        policy_hash=policy_digest("review", false),
    )
    with pytest.raises(GuideActivationBlocked, match="^automated acceptance is unavailable$"):
        service.validate_activation_ready(**bundle)
