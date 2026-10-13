"""Built-process evidence reads, hostile wire data and private server CSV."""

from copy import deepcopy
import csv
from io import StringIO
import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

from app.modules.contributions.api.records import ContributionExportResponse
from app.modules.contributions.records.csv import contribution_csv

STAMP = "2026-10-01T00:00:00Z"


def identity(n):
    return f"018f0ebc-7966-7e8d-bc4d-{n:012x}"


def evidence():
    return {
        "exported_at": STAMP,
        "items": [
            {
                "contribution_id": identity(3),
                "project_id": PROJECT,
                "task_id": identity(4),
                "submission_id": identity(5),
                "contributor_id": ACTOR,
                "contributor_display_name": "Ada",
                "contribution_type": "accepted_submission",
                "source_review_id": None,
                "source_review_lease_id": None,
                "source_final_acceptance_id": identity(6),
                "source_task_assignment_id": identity(7),
                "artifact_hash": "sha256:" + "a" * 64,
                "contribution_policy_version_id": identity(8),
                "policy_version_number": 9223372036854775808,
                "recorded_at": STAMP,
                "accepted_at": STAMP,
                "acceptance_source": "task_post_submit_route",
                "acceptance_review_id": None,
                "acceptance_routing_manifest_id": identity(9),
                "task_title": "=project\n\x1b[31m\u009b\u202e\U000e0001",
                "source_type": "research",
                "source_ref": None,
                "external_task_id": None,
                "awards": [
                    {
                        "award_id": identity(10),
                        "award_definition_id": identity(11),
                        "instrument": "money",
                        "unit": "USD",
                        "quantity": "99999999999999999999.123456789012345678",
                    },
                    {
                        "award_id": identity(12),
                        "award_definition_id": identity(13),
                        "instrument": "project_points",
                        "unit": "POINTS",
                        "quantity": "12",
                    },
                ],
            }
        ],
    }


def csv_bytes(value):
    return contribution_csv(
        ContributionExportResponse.model_validate_json(json.dumps(value))
    )


def test_contributions_exact_self_project_filters_and_text(cli):
    value = evidence()
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(value, ensure_ascii=False).encode()
        for args, path in (
            (
                ("contributions", "--project", PROJECT.replace("-", "")),
                "/api/v1/actors/me/contributions",
            ),
            (
                ("project", "contributions", PROJECT.replace("-", "")),
                f"/api/v1/projects/{PROJECT.replace('-', '')}/contributions/export",
            ),
        ):
            result = cli(
                origin,
                TOKEN,
                *args,
                "--type",
                "accepted_submission",
                "--recorded-from",
                "2026-10-01T01:00:00+01:00",
                "--recorded-before",
                "2026-10-02T00:00:00Z",
                "-o",
                "json",
            )
            assert result.returncode == 0 and json.loads(result.stdout) == value, (
                result.stderr
            )
            assert all(
                control not in result.stdout
                for control in ("\u009b", "\u202e", "\U000e0001")
            )
            method, target, bearer = requests[-1]
            assert method == "GET" and bearer == "Bearer " + TOKEN
            assert urlsplit(target).path == path
            expected = {
                "format": ["json"],
                "contribution_type": ["accepted_submission"],
                "recorded_from": [STAMP],
                "recorded_before": ["2026-10-02T00:00:00Z"],
            }
            if path.startswith("/api/v1/actors"):
                expected["project_id"] = [PROJECT.replace("-", "")]
            assert parse_qs(urlsplit(target).query) == expected
        rendered = cli(origin, TOKEN, "contributions")
        assert rendered.returncode == 0 and "\x1b" not in rendered.stdout
        assert "not payment status" in rendered.stdout
        assert "99999999999999999999.123456789012345678" in rendered.stdout
        assert len(requests) == 3


def test_contributions_empty_review_and_filter_validation(cli):
    with http_fixture() as (origin, response, requests):
        for value in ({"exported_at": STAMP, "items": []}, evidence()):
            if value["items"]:
                value["items"][0].update(
                    contribution_type="completed_review",
                    source_review_id=identity(20),
                    source_review_lease_id=identity(21),
                    source_final_acceptance_id=None,
                    source_task_assignment_id=None,
                    accepted_at=None,
                    acceptance_source=None,
                    acceptance_routing_manifest_id=None,
                    awards=[],
                )
            response["body"] = json.dumps(value).encode()
            result = cli(origin, TOKEN, "contributions", "-o", "json")
            assert result.returncode == 0 and json.loads(result.stdout) == value
        before = len(requests)
        for args in (
            ("--project", "../foreign"),
            ("--type", "paid"),
            ("--type", ""),
            ("--recorded-from", "2026-10-01"),
            ("--recorded-from", STAMP, "--recorded-before", STAMP),
            ("--actor", ACTOR),
            ("--csv", ""),
        ):
            result = cli(origin, TOKEN, "-o", "json", "contributions", *args)
            assert_failure(result, "invalid_arguments", 2)
        assert len(requests) == before


def test_contributions_refuse_wrong_scope_shape_lineage_and_duplicate_identity(cli):
    original = evidence()
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(original).encode()
        control = cli(origin, TOKEN, "project", "contributions", PROJECT, "-o", "json")
        assert control.returncode == 0, control.stderr
        mutations = [
            {"project_id": identity(99)},
            {"actor_profile_id": ACTOR},
            {"contributor_id": "bad"},
            {"task_title": None},
            {"awards": None},
            {"awards": [None]},
            {"source_final_acceptance_id": None},
            {"source_review_id": identity(20)},
            {"acceptance_routing_manifest_id": None},
            {"accepted_at": "yesterday"},
            {"policy_version_number": 0},
            {"artifact_hash": "sha256:bad"},
            {"awards": [original["items"][0]["awards"][0] | {"quantity": "1e2"}]},
            {"awards": [original["items"][0]["awards"][1] | {"quantity": "1.0"}]},
        ]
        for patch in mutations:
            value = deepcopy(original)
            value["items"][0].update(patch)
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, TOKEN, "project", "contributions", PROJECT, "-o", "json"),
                "invalid_api_response",
            )
        for field in tuple(original["items"][0]):
            value = deepcopy(original)
            del value["items"][0][field]
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )
        duplicate = deepcopy(original)
        duplicate["items"].append(deepcopy(duplicate["items"][0]))
        duplicate["items"][1]["contribution_id"] = identity(3).replace("-", "")
        duplicate["items"][1]["awards"] = []
        response["body"] = json.dumps(duplicate).encode()
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        response["body"] = json.dumps(original).encode()
        for flags in (
            ("--type", "completed_review"),
            ("--recorded-before", STAMP),
            ("--recorded-from", "2026-10-02T00:00:00Z"),
        ):
            assert_failure(
                cli(origin, TOKEN, "contributions", *flags, "-o", "json"),
                "invalid_api_response",
            )


def test_contribution_csv_exact_bytes_private_no_overwrite_and_symlink(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        body = csv_bytes(evidence())
        response["body"] = body
        response["headers"] = {"Content-Type": "text/csv; charset=utf-8"}
        output = tmp_path / "earned.csv"
        result = cli(
            origin,
            TOKEN,
            "project",
            "contributions",
            PROJECT,
            "--csv",
            str(output),
            "-o",
            "json",
        )
        assert result.returncode == 0 and json.loads(result.stdout) == {
            "format": "csv",
            "saved": True,
        }, result.stderr
        assert output.read_bytes() == body and output.stat().st_mode & 0o777 == 0o600
        assert parse_qs(urlsplit(requests[-1][1]).query) == {"format": ["csv"]}
        assert "'=project" in output.read_text()
        for target in (output, tmp_path / "link.csv"):
            if target != output:
                target.symlink_to(output)
            result = cli(
                origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"
            )
            assert_failure(result, "invalid_arguments", 2)
            assert output.read_bytes() == body
        assert not list(tmp_path.glob(".workstream-contributions-*"))


def test_contribution_csv_refuses_malformed_foreign_and_unsafe_rows(cli, tmp_path):
    body = csv_bytes(evidence())
    rows = list(csv.reader(StringIO(body.decode(), newline="")))
    with http_fixture() as (origin, response, _):
        response["headers"] = {"Content-Type": "text/csv"}

        def refused(content):
            response["body"] = content
            target = tmp_path / "refused.csv"
            result = cli(
                origin,
                TOKEN,
                "project",
                "contributions",
                PROJECT,
                "--csv",
                str(target),
                "-o",
                "json",
            )
            assert_failure(result, "invalid_api_response")
            assert not target.exists() and not list(
                tmp_path.glob(".workstream-contributions-*")
            )

        refused(body.replace(PROJECT.encode(), identity(99).encode()))
        refused(
            body.replace(b"' =", b"=")
            if b"' =" in body
            else body.replace(b"'=project", b"=project")
        )
        refused(body.replace(b'"quantity"', b'"extra"', 1))
        refused(body + b'"truncated')
        refused(b"\xff" + body)
        for column, value in (
            ("task_title", "different repeated fact"),
            ("award_id", identity(10).replace("-", "")),
            ("quantity", ""),
        ):
            changed = deepcopy(rows)
            changed[2][changed[0].index(column)] = value
            stream = StringIO(newline="")
            csv.writer(stream).writerows(changed)
            refused(stream.getvalue().encode())
        response["headers"] = {"Content-Type": "application/json"}
        refused(body)


def test_contributions_redaction_and_failure_never_publish(cli, tmp_path):
    with http_fixture() as (origin, response, _):
        for token in ("credential_canary_AAA", identity(9)):
            value = evidence()
            value["items"][0]["task_title"] = token
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, token, "contributions", "-o", "json"),
                "invalid_api_response",
            )
            response["body"] = csv_bytes(value)
            response["headers"] = {"Content-Type": "text/csv"}
            target = tmp_path / "secret.csv"
            assert_failure(
                cli(origin, token, "contributions", "--csv", str(target), "-o", "json"),
                "invalid_api_response",
            )
            assert not target.exists()
            response["headers"] = {"Content-Type": "application/json"}
        for status, code in (
            (404, "contribution_export_not_found"),
            (422, "contribution_export_too_large"),
            (503, "contribution_export_unavailable"),
        ):
            response.update(
                status=status, body=json.dumps({"error": {"code": code}}).encode()
            )
            target = tmp_path / "failed.csv"
            result = cli(
                origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"
            )
            assert_failure(result, code)
            assert not target.exists()


def test_contributions_human_acceptance_and_leading_zero_quantities(cli, tmp_path):
    value = evidence()
    item = value["items"][0]
    item.update(
        acceptance_source="human_review",
        acceptance_review_id=identity(40),
        acceptance_routing_manifest_id=None,
    )
    item["awards"][0]["quantity"] = "000001.2300"
    item["awards"][1]["quantity"] = "00012"
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(value).encode()
        result = cli(origin, TOKEN, "contributions", "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == value, (
            result.stderr
        )
        response["body"] = csv_bytes(value)
        response["headers"] = {"Content-Type": "text/csv"}
        target = tmp_path / "human.csv"
        saved = cli(origin, TOKEN, "contributions", "--csv", str(target), "-o", "json")
        assert saved.returncode == 0 and target.read_bytes() == response["body"], (
            saved.stderr
        )
        assert (
            b'"000001.2300"' in target.read_bytes()
            and b'"00012"' in target.read_bytes()
        )
        response["headers"] = {"Content-Type": "application/json"}
        for patch in (
            {"acceptance_review_id": None},
            {"acceptance_routing_manifest_id": identity(41)},
        ):
            bad = deepcopy(value)
            bad["items"][0].update(patch)
            response["body"] = json.dumps(bad).encode()
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )


def test_contributions_json_and_csv_size_caps_reject_valid_oversized_exports(
    cli, tmp_path
):
    value = evidence()
    value["items"][0]["task_title"] = "x" * (32 * 1024 * 1024)
    with http_fixture() as (origin, response, _):
        response["body"] = json.dumps(value).encode()
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        response["headers"] = {"Content-Type": "text/csv"}
        response["body"] = csv_bytes(value)
        target = tmp_path / "oversized.csv"
        result = cli(origin, TOKEN, "contributions", "--csv", str(target), "-o", "json")
        assert_failure(result, "invalid_api_response")
        assert not target.exists() and not list(
            tmp_path.glob(".workstream-contributions-*")
        )


def test_contributions_complete_limit_order_and_unique_awards(cli, tmp_path):
    with http_fixture() as (origin, response, _):
        first = evidence()["items"][0]
        second = deepcopy(first)
        second.update(contribution_id=identity(30), awards=[])
        valid = {"exported_at": STAMP, "items": [first, second]}
        response["body"] = json.dumps(valid).encode()
        assert cli(origin, TOKEN, "contributions", "-o", "json").returncode == 0
        for value in (
            {"exported_at": STAMP, "items": [second, first]},
            {
                "exported_at": STAMP,
                "items": [first, second | {"awards": first["awards"]}],
            },
            {"exported_at": STAMP, "items": None},
            valid | {"extra": "undocumented"},
        ):
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, TOKEN, "contributions", "-o", "json"),
                "invalid_api_response",
            )
        items = [
            second | {"contribution_id": identity(100 + index)} for index in range(1000)
        ]
        response["body"] = json.dumps({"exported_at": STAMP, "items": items}).encode()
        result = cli(origin, TOKEN, "contributions", "-o", "json")
        assert (
            result.returncode == 0 and len(json.loads(result.stdout)["items"]) == 1000
        )
        items.append(second | {"contribution_id": identity(1100)})
        response["body"] = json.dumps({"exported_at": STAMP, "items": items}).encode()
        assert_failure(
            cli(origin, TOKEN, "contributions", "-o", "json"), "invalid_api_response"
        )
        response["headers"] = {"Content-Type": "text/csv; charset=utf-8"}
        for index, value in enumerate(
            (
                {"exported_at": STAMP, "items": []},
                {"exported_at": STAMP, "items": [second]},
            )
        ):
            body = csv_bytes(value)
            response["body"] = body
            target = tmp_path / f"empty-{index}.csv"
            result = cli(
                origin, TOKEN, "contributions", "--csv", str(target), "-o", "json"
            )
            assert result.returncode == 0 and target.read_bytes() == body, result.stderr
