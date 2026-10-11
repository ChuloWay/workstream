"""Built CLI correction custody, explicit dispatch and no automatic replay."""

from copy import deepcopy
import json
from uuid import UUID

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_create_http import GUIDE, SETUP
from test_guide_post_approval_http import unknown
from test_guide_post_policy_http import LARGE
from test_guide_proposal_http import COMPILATION, HASH, OTHER, proposal
from test_http_boundary import PROJECT, TOKEN, http_fixture

SELECTORS = (PROJECT, GUIDE, COMPILATION)


def correction_input():
    return {"target": proposal()["target"], "reason": "Clarify café evidence."}


def saved(body=None):
    return {
        "operation_id": OTHER,
        "target_digest": HASH,
        "successor_setup_run_id": SETUP,
        "successor_setup_generation": (body or correction_input())["target"][
            "setup_generation"
        ]
        + 1,
        "feedback_hash": HASH,
        "status": "correction_requested",
    }


def dispatched(receipt=None, status="queued"):
    value = receipt or saved()
    return {
        "correction_operation_id": value["operation_id"],
        "setup_run_id": value["successor_setup_run_id"],
        "setup_generation": value["successor_setup_generation"],
        "status": status,
    }


def invoke(
    cli,
    origin,
    path,
    *,
    dispatch=False,
    selectors=SELECTORS,
    token=TOKEN,
    key=KEY,
    output="json",
    **kwargs,
):
    args = [
        "project",
        "guide",
        "dispatch-correction" if dispatch else "correct",
        *selectors,
        "--input",
        str(path),
        "-o",
        output,
    ]
    if not dispatch:
        args += ["--idempotency-key", key]
    return cli(origin, token, *args, **kwargs)


def test_guide_correction_exact_wire_and_closed_inputs(cli, tmp_path):
    path = tmp_path / "correction.json"
    body = correction_input()
    body["target"]["setup_generation"] = LARGE
    body["reason"] = "Guide feedback\n\t" + "é" * 2000
    original = json.dumps(body, ensure_ascii=False, indent=2).encode()
    path.write_bytes(original)
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(saved(body)).encode())
        for selectors, key in (
            (SELECTORS, KEY),
            (tuple(UUID(x).hex for x in SELECTORS), UUID(KEY).hex),
        ):
            result = invoke(cli, origin, path, selectors=selectors, key=key)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == saved(body)
            assert requests[-1] == (
                "POST",
                "/api/v1/projects/{}/guides/{}/compilations/{}/corrections".format(
                    *selectors
                ),
                "Bearer " + TOKEN,
            )
            assert response["raw_commands"][-1] == original
            assert response["commands"][-1] == ("application/json", [key], body)
        variants = [
            body | {"extra": 1},
            body | {"reason": None},
            body | {"reason": ""},
            body | {"reason": "é" * 4001},
            body | {"target": None},
        ]
        crossed = deepcopy(body)
        crossed["target"]["project_id"] = OTHER
        variants.append(crossed)
        for invalid in variants:
            path.write_text(json.dumps(invalid), encoding="utf-8")
            result = invoke(cli, origin, path)
            assert result.returncode == 2 and result.stdout == ""
        path.write_text(
            '{"reason":"a","reason":"b","target":' + json.dumps(body["target"]) + "}"
        )
        assert invoke(cli, origin, path).returncode == 2
        path.write_bytes(original)
        assert invoke(cli, origin, path, key="not-uuid").returncode == 2
        assert len(requests) == 2


def test_guide_correction_receipt_and_explicit_dispatch_binding(cli, tmp_path):
    path = tmp_path / "decision.json"
    body = correction_input()
    body["target"]["setup_generation"] = LARGE
    path.write_text(json.dumps(body))
    receipt = saved(body)
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(receipt).encode())
        assert invoke(cli, origin, path).returncode == 0
        for field, invalid in (
            ("successor_setup_generation", LARGE + 2),
            ("operation_id", "not-uuid"),
            ("successor_setup_run_id", None),
            ("feedback_hash", "wrong"),
            ("status", None),
            ("target_digest", "wrong"),
            ("extra", 1),
        ):
            response["body"] = json.dumps(receipt | {field: invalid}).encode()
            unknown(invoke(cli, origin, path))
        without_default = receipt.copy()
        del without_default["status"]
        response["body"] = json.dumps(without_default).encode()
        assert invoke(cli, origin, path).returncode == 0
        path.write_text(json.dumps(without_default))
        response.update(status=202, body=json.dumps(dispatched(receipt)).encode())
        for selectors in (SELECTORS, tuple(UUID(x).hex for x in SELECTORS)):
            result = invoke(cli, origin, path, dispatch=True, selectors=selectors)
            assert result.returncode == 0 and json.loads(result.stdout) == dispatched(
                receipt
            )
            assert requests[-1] == (
                "POST",
                "/api/v1/projects/{}/guides/{}/compilations/{}/corrections/{}/dispatch".format(
                    *selectors, receipt["operation_id"]
                ),
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == (None, None, b"")
        # Each substitute is otherwise valid; a control reaches the same decoder.
        for field, invalid in (
            ("correction_operation_id", PROJECT),
            ("setup_run_id", PROJECT),
            ("setup_generation", LARGE + 2),
            ("status", None),
            ("status", 1),
            ("extra", 1),
        ):
            response["body"] = json.dumps(
                dispatched(receipt) | {field: invalid}
            ).encode()
            unknown(invoke(cli, origin, path, dispatch=True))
        response["body"] = (
            b'{"status":"queued","status":"queued","correction_operation_id":'
            + json.dumps(receipt["operation_id"]).encode()
            + b',"setup_run_id":'
            + json.dumps(receipt["successor_setup_run_id"]).encode()
            + b',"setup_generation":'
            + str(receipt["successor_setup_generation"]).encode()
            + b"}"
        )
        unknown(invoke(cli, origin, path, dispatch=True))
        for status in (
            "enqueue_failed",
            "provider_outcome_unresolved",
            "future diagnostic\n\x1b[31m",
        ):
            response["body"] = json.dumps(dispatched(receipt, status)).encode()
            result = invoke(cli, origin, path, dispatch=True)
            assert (
                result.returncode == 0 and json.loads(result.stdout)["status"] == status
            )
            text_result = invoke(cli, origin, path, dispatch=True, output="text")
            assert (
                text_result.returncode == 0
                and "not completion or activation" in text_result.stdout
            )
            assert "\x1b" not in text_result.stdout
        count = len(requests)
        for invalid in (
            receipt | {"operation_id": None},
            receipt | {"extra": 1},
            {"correction": receipt},
        ):
            path.write_text(json.dumps(invalid))
            assert invoke(cli, origin, path, dispatch=True).returncode == 2
        assert len(requests) == count


def test_guide_correction_uncertainty_credentials_and_bodyless_no_replay(cli, tmp_path):
    path = tmp_path / "input.json"
    for dispatch in (False, True):
        path.write_text(json.dumps(saved() if dispatch else correction_input()))
        with http_fixture() as (origin, response, requests):
            response.update(
                status=404, body=json.dumps(canonical_error("not_found")).encode()
            )
            result = invoke(cli, origin, path, dispatch=dispatch)
            assert result.returncode == 1 and not json.loads(result.stderr)[
                "error"
            ].get("outcome_unknown", False)
            for status, raw, headers, drop in (
                (
                    404,
                    json.dumps(
                        canonical_error("not_found")
                        | {
                            "error": canonical_error("not_found")["error"]
                            | {"details": None}
                        }
                    ).encode(),
                    {"Content-Type": "application/json"},
                    False,
                ),
                (500, b"failure", {"Content-Type": "text/plain"}, False),
                (302, b"", {"Location": origin + "/must-not-follow"}, False),
                (
                    202 if dispatch else 201,
                    b"{}",
                    {"Content-Type": "text/plain"},
                    False,
                ),
                (
                    202 if dispatch else 201,
                    b" " * 65537,
                    {"Content-Type": "application/json"},
                    False,
                ),
                (
                    202 if dispatch else 201,
                    b"{}",
                    {"Content-Type": "application/json"},
                    True,
                ),
            ):
                response.update(status=status, body=raw, headers=headers, drop=drop)
                before = len(requests)
                result = invoke(cli, origin, path, dispatch=dispatch)
                assert (
                    result.returncode == 1
                    and result.stdout == ""
                    and json.loads(result.stderr)["error"]["outcome_unknown"] is True
                )
                assert len(requests) == before + 1
                text_result = invoke(
                    cli, origin, path, dispatch=dispatch, output="text"
                )
                assert "unchanged" in text_result.stderr
    path.write_text(json.dumps(correction_input()))
    with http_fixture() as (origin, response, _):
        response["status"] = 201
        for field, token in (
            ("operation_id", UUID(OTHER).hex),
            ("successor_setup_run_id", UUID(SETUP).hex),
            ("target_digest", "a" * 64),
            ("feedback_hash", "a" * 64),
        ):
            response["body"] = json.dumps(saved()).encode()
            unknown(invoke(cli, origin, path, token=token))
    path.write_text(json.dumps(saved()))
    with http_fixture() as (origin, response, _):
        response.update(status=202, body=json.dumps(dispatched(status=TOKEN)).encode())
        unknown(invoke(cli, origin, path, dispatch=True))
        response["body"] = json.dumps(dispatched(status=PROJECT)).encode()
        unknown(invoke(cli, origin, path, dispatch=True, token=UUID(PROJECT).hex))
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = invoke(cli, origin, path, dispatch=True, extra_env=env)
        unknown(result, "service_unavailable")
        assert bodies == [b""] and connections == ["h2"]
