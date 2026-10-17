"""Contract proof for the one Workstream-owned default checker."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_MANIFEST,
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WORKSTREAM_DEFAULT_CHECK_IDS,
    WorkstreamDefaultCheck,
    WorkstreamDefaultCheckerResult,
)
from app.core.hashing import canonical_json_hash


def _passing_result() -> WorkstreamDefaultCheckerResult:
    return WorkstreamDefaultCheckerResult(
        behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        eligible=True,
        checks=tuple(
            WorkstreamDefaultCheck(
                check_id=check_id,
                status="passed",
                failure_code=None,
                finding_count=0,
            )
            for check_id in WORKSTREAM_DEFAULT_CHECK_IDS
        ),
        warnings=(),
    )


def test_behavior_identity_and_exact_four_check_order_are_stable() -> None:
    result = _passing_result()

    assert WORKSTREAM_DEFAULT_BEHAVIOR_SHA256 == (
        "sha256:af2c604f792c4456d3b222036c772161b1503eace65ff90c3d3a23d9d348c28f"
    )
    assert tuple(item.check_id for item in result.checks) == WORKSTREAM_DEFAULT_CHECK_IDS

    for changed in (
        result.model_copy(update={"checks": result.checks[:-1]}),
        result.model_copy(update={"checks": tuple(reversed(result.checks))}),
        result.model_copy(update={"behavior_sha256": "sha256:" + "0" * 64}),
    ):
        with pytest.raises(ValidationError):
            WorkstreamDefaultCheckerResult.model_validate(changed)


def test_behavior_identity_binds_executable_secret_patterns_and_flags() -> None:
    changed = {
        **WORKSTREAM_DEFAULT_BEHAVIOR_MANIFEST,
        "secret_signatures": [
            *WORKSTREAM_DEFAULT_BEHAVIOR_MANIFEST["secret_signatures"][:-1],
            {
                **WORKSTREAM_DEFAULT_BEHAVIOR_MANIFEST["secret_signatures"][-1],
                "pattern": "changed",
            },
        ],
    }

    assert canonical_json_hash(changed) != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256


def test_failure_shape_is_bound_to_its_exact_default() -> None:
    with pytest.raises(ValidationError):
        WorkstreamDefaultCheck(
            check_id="received_identity_exact",
            status="failed",
            failure_code="high_confidence_secret_detected",
            finding_count=1,
        )
    with pytest.raises(ValidationError):
        WorkstreamDefaultCheck(
            check_id="high_confidence_secrets_absent",
            status="passed",
            failure_code="high_confidence_secret_detected",
            finding_count=1,
        )
    with pytest.raises(ValidationError):
        WorkstreamDefaultCheck(
            check_id="high_confidence_secrets_absent",
            status="passed",
            failure_code="high_confidence_secret_detected",
            finding_count=0,
        )


def test_warning_order_is_closed_and_does_not_change_eligibility() -> None:
    result = _passing_result()
    values = result.model_dump(mode="python")
    values["warnings"] = [
        {"code": "submission_attestation_missing"},
        {"code": "submission_summary_missing"},
    ]

    with pytest.raises(ValidationError):
        WorkstreamDefaultCheckerResult.model_validate(values)

    values = result.model_dump(mode="python")
    values["eligible"] = False
    with pytest.raises(ValidationError):
        WorkstreamDefaultCheckerResult.model_validate(values)
