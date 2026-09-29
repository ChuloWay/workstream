"""Complete locked-policy classification; one bad member cannot hide in a pass."""

import pytest

from app.modules.checkers.api.post_submit import PostSubmitMemberResult
from app.modules.checkers.execution_results import classify_result
from tests.checkers.post_submit.support import request
from tests.checkers.post_submit.test_result_contract import result


@pytest.mark.parametrize(
    "failed_ids,expected",
    [
        ((), "allow_review"),
        (("check_submission_packet",), "needs_revision"),
        (("check_policy_context_present",), "task_setup_blocked"),
        (("check_submission_packet", "check_policy_context_present"), "task_setup_blocked"),
        (("check_low_quality_generated_artifacts",), "allow_review"),
    ],
)
def test_routing_uses_complete_locked_policy(failed_ids, expected):
    source = request()
    members = []
    matched = set()
    for entry, passed in zip(source.policy.entries, result(source).member_results, strict=True):
        definition = source.catalogue.definition(entry.checker_id, entry.definition_version)
        if entry.checker_id in failed_ids:
            matched.add(entry.checker_id)
            members.append(
                PostSubmitMemberResult(
                    checker_id=entry.checker_id,
                    definition_version=entry.definition_version,
                    implementation_version=entry.implementation_version,
                    status=definition.failure_status,
                    code=definition.failure_code,
                    failure_category=definition.failure_category,
                    severity=definition.failure_severity,
                )
            )
        else:
            members.append(passed)
    assert matched == set(failed_ids), "case must exercise a registered member"
    actual = classify_result(source, result(source, member_results=tuple(members)))
    assert actual.routing == expected
    assert actual.passed + actual.warning + actual.failed == len(source.policy.entries)
    assert actual.blocking == sum(m.status == "failed" for m in members)


def test_incomplete_members_cannot_classify():
    source = request()
    with pytest.raises(ValueError, match="members mismatch"):
        classify_result(source, result(source, member_results=result(source).member_results[:-1]))


@pytest.mark.parametrize("strict", [False, True])
def test_locked_medium_severity_can_block_placeholder_warning(strict):
    from app.modules.projects.post_submit_policy import (
        build_project_post_submit_checker_spec,
        compile_project_post_submit_checker_spec,
    )
    from tests.checkers.post_submit.support import change_request

    source = request()
    policy = compile_project_post_submit_checker_spec(
        project_id=str(source.project_id),
        guide_version="v1",
        spec=build_project_post_submit_checker_spec(
            project_id=str(source.project_id),
            guide_version="v1",
            blocking_severities=["critical", "high", "medium"] if strict else ["critical", "high"],
        ),
    )
    source = change_request(
        source,
        policy=policy,
        expected_context=source.expected_context.model_copy(
            update={"post_policy_hash": policy.policy_hash}
        ),
    )
    members = list(result(source).member_results)
    idx = next(
        index
        for index, item in enumerate(members)
        if item.checker_id == "check_low_quality_generated_artifacts"
    )
    definition = source.catalogue.definition(
        members[idx].checker_id, members[idx].definition_version
    )
    members[idx] = PostSubmitMemberResult(
        checker_id=definition.capability_id,
        implementation_version=definition.implementation_version,
        status="warning",
        severity="medium",
        code=definition.failure_code,
        failure_category=definition.failure_category,
    )
    classified = classify_result(source, result(source, member_results=tuple(members)))
    assert classified.routing == ("needs_revision" if strict else "allow_review")
    assert classified.warning == 1 and classified.failed == 0 and classified.blocking == int(strict)
