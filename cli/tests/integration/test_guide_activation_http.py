"""Built-process activation selections, exact receipts and uncertain writes."""

from copy import deepcopy
import json
from uuid import UUID

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_create_http import GUIDE, SETUP
from test_guide_post_approval_http import unknown
from test_guide_post_policy_http import LARGE, package
from test_guide_proposal_http import HASH, OTHER
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture


def activation():
    return {
        "target": package()["target"],
        "post_approval_operation_id": OTHER,
        "post_approval_output_digest": HASH,
        "guide_mutation_generation": LARGE,
        "review": {"policy_id": SETUP, "generation": LARGE, "policy_hash": HASH},
        "revision": {"policy_id": OTHER, "generation": LARGE, "policy_hash": HASH},
        "contribution_policy_id": SETUP,
        "contribution_policy_version_id": OTHER,
        "expected_previous_active_guide_id": None,
        "expected_previous_active_guide_generation": None,
    }


def receipt(body=None, key=KEY):
    body = deepcopy(body or activation())
    return {
        "operation_id": OTHER,
        "command": body | {"idempotency_key": key},
        "contribution": {
            "project_id": body["target"]["proposal"]["project_id"],
            "contribution_policy_id": body["contribution_policy_id"],
            "contribution_policy_version_id": body["contribution_policy_version_id"],
            "purpose": "guide_activation",
            "version_number": LARGE,
            "rules_and_definitions_digest": HASH,
            "adapter_binding_ids": [],
        },
        "activation_generation": body["guide_mutation_generation"] + 1,
        "effective_at": "2026-10-11T12:00:00+00:00",
        "prior_project_status": "draft",
    }


def write_input(tmp_path, body=None):
    path = tmp_path / "activation.json"
    path.write_text(json.dumps(body or activation(), indent=2), encoding="utf-8")
    return path


def invoke(
    cli,
    origin,
    path,
    *,
    selectors=(PROJECT, GUIDE),
    key=KEY,
    token=TOKEN,
    output="json",
    **kwargs,
):
    return cli(
        origin,
        token,
        "-o",
        output,
        "project",
        "guide",
        "activate",
        *selectors,
        "--input",
        str(path),
        "--idempotency-key",
        key,
        **kwargs,
    )


def test_activation_exact_wire_predecessor_and_uuid_identity(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        for previous, generation in ((None, None), (OTHER, LARGE), (OTHER, None)):
            body = activation()
            body["target"]["proposal"]["guide_version"] = "Guide é\x1b[31m\nversion"
            body.update(
                expected_previous_active_guide_id=previous,
                expected_previous_active_guide_generation=generation,
            )
            path = write_input(tmp_path, body)
            observed = receipt(body)
            observed["prior_project_status"] = "active" if previous else "draft"
            observed["command"]["review"]["policy_id"] = UUID(SETUP).hex
            observed["command"]["idempotency_key"] = UUID(KEY).hex
            observed["contribution"]["adapter_binding_ids"] = [OTHER]
            response["body"] = json.dumps(observed).encode()
            selected = (UUID(PROJECT).hex, UUID(GUIDE).hex)
            result = invoke(cli, origin, path, selectors=selected, key=UUID(KEY).hex)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == observed
            assert requests[-1] == (
                "POST",
                "/api/v1/projects/{}/guides/{}/activate".format(*selected),
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == (
                "application/json",
                [UUID(KEY).hex],
                body,
            )
            assert response["raw_commands"][-1] == path.read_bytes()
            result = invoke(cli, origin, path, output="text")
            assert result.returncode == 0 and result.stderr == ""
            assert "Guide activation receipt" in result.stdout
            assert "\x1b" not in result.stdout and "\r" not in result.stdout
        assert len(requests) == 6


def test_activation_invalid_input_never_calls_api(cli, tmp_path):
    variants = []
    for field in activation():
        value = activation()
        del value[field]
        variants.append(value)
    for field in (
        "guide_mutation_generation",
        "review",
        "contribution_policy_id",
        "target",
    ):
        value = activation()
        value[field] = None
        variants.append(value)
    variants.extend(
        [
            activation() | {"idempotency_key": KEY},
            activation() | {"guide_mutation_generation": True},
            activation() | {"guide_mutation_generation": 1.5},
            activation()
            | {"review": {"policy_id": SETUP, "generation": 0, "policy_hash": HASH}},
            activation() | {"expected_previous_active_guide_generation": 1},
            activation() | {"expected_previous_active_guide_id": GUIDE},
            activation() | {"post_approval_output_digest": "bad"},
        ]
    )
    path = write_input(tmp_path)
    with http_fixture() as (origin, _, requests):
        for value in variants:
            path.write_text(json.dumps(value))
            assert_failure(invoke(cli, origin, path), "invalid_arguments", 2)
        path = write_input(tmp_path)
        for selectors, key in (
            ((PROJECT + "/private", GUIDE), KEY),
            ((OTHER, GUIDE), KEY),
            ((PROJECT, OTHER), KEY),
            ((PROJECT, GUIDE), "bad"),
        ):
            assert_failure(
                invoke(cli, origin, path, selectors=selectors, key=key),
                "invalid_arguments",
                2,
            )
        path.write_text(
            json.dumps(activation()).replace('"review":', '"review": null, "review":')
        )
        assert_failure(invoke(cli, origin, path), "invalid_arguments", 2)
        assert requests == []


def test_activation_rejects_substituted_and_malformed_success_receipts(cli, tmp_path):
    path = write_input(tmp_path)
    variants = []
    # Every required field must be present and non-null, including nested facts.
    for prefix in (
        (),
        ("command",),
        ("contribution",),
        ("command", "review"),
        ("command", "revision"),
    ):
        original = receipt()
        target = original
        for name in prefix:
            target = target[name]
        for field, value in target.items():
            for missing in (True, False):
                if value is None and not missing:
                    continue
                changed = deepcopy(original)
                selected = changed
                for name in prefix:
                    selected = selected[name]
                if missing:
                    del selected[field]
                else:
                    selected[field] = None
                variants.append(changed)
    substitutions = [
        (("operation_id",), "550e8400-e29b-41d4-a716-446655440000"),
        (("activation_generation",), LARGE),
        (("effective_at",), "2026-10-11T12:00:00"),
        (("prior_project_status",), "complete"),
        (("command", "idempotency_key"), OTHER),
        (("command", "post_approval_operation_id"), PROJECT),
        (("command", "post_approval_output_digest"), "sha256:" + "f" * 64),
        (("command", "guide_mutation_generation"), LARGE + 1),
        (("command", "target", "policy_id"), OTHER),
        (("command", "review", "policy_id"), OTHER),
        (("command", "review", "generation"), LARGE + 1),
        (("command", "revision", "policy_hash"), "sha256:" + "f" * 64),
        (("command", "expected_previous_active_guide_id"), OTHER),
        (("command", "contribution_policy_id"), OTHER),
        (("contribution", "project_id"), OTHER),
        (("contribution", "contribution_policy_id"), OTHER),
        (("contribution", "contribution_policy_version_id"), PROJECT),
        (("contribution", "purpose"), "final_acceptance"),
        (("contribution", "version_number"), False),
        (("contribution", "rules_and_definitions_digest"), "bad"),
        (("contribution", "adapter_binding_ids"), [None]),
        (("contribution", "adapter_binding_ids"), ["bad"]),
        (("private",), "unexpected"),
    ]
    for keys, value in substitutions:
        changed = receipt()
        selected = changed
        for name in keys[:-1]:
            selected = selected[name]
        selected[keys[-1]] = value
        variants.append(changed)
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(receipt()).encode()
        assert invoke(cli, origin, path).returncode == 0
        for value in variants:
            response["body"] = json.dumps(value).encode()
            unknown(invoke(cli, origin, path))
        response["body"] = (
            json.dumps(receipt())
            .replace('"effective_at":', '"effective_at": null, "effective_at":')
            .encode()
        )
        unknown(invoke(cli, origin, path))
        assert len(requests) == len(variants) + 2


def test_activation_credentials_denials_and_no_transport_retry(cli, tmp_path):
    path = write_input(tmp_path)
    with http_fixture() as (origin, response, requests):
        for status, value, ambiguous in (
            (404, canonical_error(), False),
            (409, canonical_error("proposal_stale"), False),
            (422, canonical_error("validation_error"), False),
            (503, canonical_error(), True),
            (403, {"error": canonical_error()["error"] | {"details": None}}, True),
            (302, {}, True),
            (201, receipt(), True),
        ):
            response.update(
                status=status,
                body=json.dumps(value).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Location": origin + "/private",
                },
            )
            result = invoke(cli, origin, path)
            assert result.returncode == 1 and result.stdout == ""
            assert (
                json.loads(result.stderr)["error"].get("outcome_unknown", False)
                is ambiguous
            )
        response.update(status=200, body=b" " * 65537)
        unknown(invoke(cli, origin, path))
        response.update(
            body=json.dumps(receipt()).encode(), headers={"Content-Type": "text/html"}
        )
        unknown(invoke(cli, origin, path))
        # Decode escaped strings and compare UUID identity, not just raw bytes.
        body = activation()
        body["target"]["proposal"]["guide_version"] = TOKEN
        path = write_input(tmp_path, body)
        response.update(
            headers={"Content-Type": "application/json"},
            body=json.dumps(receipt(body))
            .replace(TOKEN, "\\u0063aller.flow.token")
            .encode(),
        )
        unknown(invoke(cli, origin, path))
        path = write_input(tmp_path)
        response["body"] = json.dumps(receipt()).encode()
        unknown(invoke(cli, origin, path, token=UUID(OTHER).hex))
        unknown(invoke(cli, origin, path, token=str(LARGE)))
        response["drop"] = True
        result = invoke(cli, origin, path, output="text")
        assert result.returncode == 1 and result.stdout == ""
        assert (
            "unchanged project, guide, input file contents and idempotency key"
            in result.stderr
        )
        assert len(requests) == 13
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        unknown(invoke(cli, origin, path, extra_env=env), "service_unavailable")
        assert connections == ["h2"] and bodies == [path.read_bytes()]
