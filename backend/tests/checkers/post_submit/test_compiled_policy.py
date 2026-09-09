"""Dormant v2 compile/parse and exact historical identity controls."""

import pytest
from pydantic import ValidationError

from app.modules.checkers.api import CompiledPostSubmitPolicyV2
from app.modules.projects.post_submit_policy import (
    POST_SUBMIT_COMPILER_VERSION,
    compile_post_submit_policy_v2,
    parse_post_submit_policy_v2,
    project_guide_post_submission_capabilities,
    project_guide_post_submission_capabilities_v2,
)
from tests.checkers.post_submit.support import PROJECT, altered_catalogue, catalogue, request


def test_explicit_compile_parse_and_current_implementation_selection():
    source = request()
    body = source.policy.model_dump(mode="json")
    parsed = parse_post_submit_policy_v2(
        body=body, policy_hash=source.policy.policy_hash, catalogue=source.catalogue
    )
    assert parsed == source.policy
    assert parsed.entries[1].implementation_version == "workstream-policy-context-v2"
    assert len(parsed.entries) == 9
    defaults = compile_post_submit_policy_v2(
        project_id=PROJECT, guide_version="v1", catalogue=source.catalogue
    )
    assert len(defaults.entries) == 8
    warning = compile_post_submit_policy_v2(
        project_id=PROJECT,
        guide_version="v1",
        catalogue=source.catalogue,
        warning_checkers=("check_acceptance_criteria_present",),
    )
    assert warning.entries[-1].classification == "project_warning"


@pytest.mark.parametrize(
    "required,warning",
    [
        (("unknown",), ()),
        (("check_submission_packet",), ()),
        (("check_acceptance_criteria_present",), ("check_acceptance_criteria_present",)),
    ],
)
def test_compiler_rejects_unknown_default_and_repeated_project_selection(required, warning):
    with pytest.raises(ValueError, match="selection is unavailable|entries repeat"):
        compile_post_submit_policy_v2(
            project_id=PROJECT,
            guide_version="v1",
            catalogue=catalogue(),
            required_checkers=required,
            warning_checkers=warning,
        )


@pytest.mark.parametrize("index", (0, 8))
def test_disabled_default_or_selected_capability_cannot_compile(index):
    with pytest.raises(ValueError, match="definition is unavailable"):
        compile_post_submit_policy_v2(
            project_id=PROJECT,
            guide_version="v1",
            catalogue=altered_catalogue(index=index, state="disabled"),
            required_checkers=("check_acceptance_criteria_present",),
        )


@pytest.mark.parametrize(
    "change,match",
    [
        ("hash", "policy hash mismatch"),
        ("catalogue", "catalogue hash mismatch"),
        ("implementation", "implementation version mismatch"),
        ("omit", "omits mandatory"),
        ("default", "classification mismatch"),
        ("order", "order or dependency"),
        ("repeat", "duplicate entries"),
        ("severity", "blocking severities"),
    ],
)
def test_exact_body_validation(change, match):
    source = request()
    body = source.policy.model_dump(mode="json")
    if change == "hash":
        with pytest.raises(ValueError, match=match):
            parse_post_submit_policy_v2(
                body=body, policy_hash="sha256:" + "0" * 64, catalogue=source.catalogue
            )
        return
    if change == "catalogue":
        body["catalogue_manifest_sha256"] = "sha256:" + "0" * 64
    elif change == "implementation":
        body["entries"][1]["implementation_version"] = "workstream-structural-v1"
    elif change == "omit":
        del body["entries"][0]
    elif change == "default":
        body["entries"][0]["classification"] = "project_required"
    elif change == "order":
        body["entries"][0], body["entries"][1] = body["entries"][1], body["entries"][0]
    elif change == "repeat":
        body["entries"][1] = body["entries"][0]
    elif change == "severity":
        body["blocking_severities"] = ["low", "medium"]
    with pytest.raises(ValueError, match=match):
        CompiledPostSubmitPolicyV2.model_validate_json(
            __import__("json").dumps(body)
        ).validate_catalogue(source.catalogue)


def test_agent_projection_matches_canonical_catalogue():
    source = catalogue()
    projection = project_guide_post_submission_capabilities_v2(source)
    assert projection.model_dump(mode="json") == source.model_dump(mode="json")
    corrupted = projection.model_dump()
    corrupted["definitions"][0]["state"] = "disabled"
    with pytest.raises(ValidationError, match="hash mismatch"):
        type(projection).model_validate(corrupted)


def test_historical_projection_keeps_exact_original_schema_and_versions():
    old = project_guide_post_submission_capabilities()
    assert old.schema_version == "post_submission_checker_capability_projection.v1"
    assert POST_SUBMIT_COMPILER_VERSION == "workstream-post-submit-compiler-v0.1"
    assert all(item.capability_version == POST_SUBMIT_COMPILER_VERSION for item in old.definitions)
    assert all(
        set(item.model_dump())
        == {"capability_id", "capability_version", "stage", "platform_default", "selectable"}
        for item in old.definitions
    )


def test_historical_compilation_and_policy_hashes():
    # Golden identity obtained from main 4e05ebfa's original pure compiler.
    from app.modules.projects.post_submit_policy import (
        build_project_post_submit_checker_spec,
        compile_project_post_submit_checker_spec,
        parse_locked_post_submit_checker_policy_body,
    )

    spec = build_project_post_submit_checker_spec(
        project_id=str(PROJECT),
        guide_version="v1",
        required_checkers=["check_acceptance_criteria_present"],
    )
    original = compile_project_post_submit_checker_spec(
        project_id=str(PROJECT), guide_version="v1", spec=spec
    )
    assert (
        original.policy_hash
        == "sha256:589b26ae65bc021bc2b8e257900e86773bc37a80fc2088b613da8c14d52b2f7e"
    )
    assert (
        project_guide_post_submission_capabilities().manifest_sha256
        == "sha256:f9a0b13bedeb7f35dc8941d75c6a44cabf193ed51604d462b2bbfdbe236f37a3"
    )
    assert original.policy_body["schema_version"] == "post_submit_checker_policy.v1"
    assert "catalogue_manifest_sha256" not in original.policy_body
    with pytest.raises(ValueError):
        parse_post_submit_policy_v2(
            body=original.policy_body, policy_hash=original.policy_hash, catalogue=catalogue()
        )
    assert (
        parse_locked_post_submit_checker_policy_body(
            original.policy_body,
            project_id=str(PROJECT),
            guide_version="v1",
            policy_hash=original.policy_hash,
        ).compiler_version
        == POST_SUBMIT_COMPILER_VERSION
    )
