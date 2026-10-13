"""Built source CLI preserves exact bytes and treats uncertain PUTs as writes."""

from hashlib import sha256
import json

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_proposal_http import OTHER
from test_http_boundary import PROJECT, TOKEN, http_fixture

SOURCE = OTHER
RAW = (
    b'{\n "schema_version":"workstream.task_import.v1", "tasks":['
    b'{"external_task_id":"brief-1","title":"Caption","description":"Brief"}]}\n'
)


def source(status="verified"):
    return {
        "source_id": SOURCE,
        "project_id": PROJECT,
        "sha256": "sha256:" + sha256(RAW).hexdigest(),
        "byte_count": len(RAW),
        "media_type": "application/json",
        "status": status,
        "created_at": "2026-10-11T12:00:00Z",
    }


def invoke(
    cli, origin, operation, path=None, *, project=PROJECT, target=SOURCE, **kwargs
):
    args = ["-o", "json", "project", "task-batch", operation, project]
    if operation != "source-declare":
        args.append(target)
    if path is not None:
        args.extend(("--input", str(path)))
    if operation == "source-declare":
        args.extend(("--idempotency-key", KEY))
    return cli(origin, TOKEN, *args, **kwargs)


def test_source_operations_are_separate_exact_requests(cli, tmp_path):
    path = tmp_path / "briefs.json"
    path.write_bytes(RAW)
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(source("declared")).encode())
        result = invoke(cli, origin, "source-declare", path)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == source("declared")
        assert response["commands"] == [
            (
                "application/json",
                [KEY],
                {"sha256": source()["sha256"], "byte_count": len(RAW)},
            )
        ]
        response.update(status=200, body=json.dumps(source()).encode())
        result = invoke(cli, origin, "source-upload", path)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == source()
        assert response["raw_commands"][-1] == RAW
        assert response["commands"][-1][0:2] == ("application/json", None)
        result = invoke(cli, origin, "source-status")
        assert result.returncode == 0 and json.loads(result.stdout) == source()
        prefix = f"/api/v1/projects/{PROJECT}/task-import-sources"
        assert requests == [
            ("POST", prefix, "Bearer " + TOKEN),
            ("PUT", f"{prefix}/{SOURCE}/content", "Bearer " + TOKEN),
            ("GET", f"{prefix}/{SOURCE}", "Bearer " + TOKEN),
        ]


def test_source_invalid_requests_never_contact_server(cli, tmp_path):
    path = tmp_path / "briefs.json"
    with http_fixture() as (origin, _response, requests):
        for raw in (
            RAW.replace(b'"title":"Caption"', b'"title":"Caption","title":"x"'),
            RAW.replace(
                b'"description":"Brief"', b'"description":"Brief","created_by":"x"'
            ),
            RAW.replace(
                b'"external_task_id":"brief-1"', b'"external_task_id":" brief-1"'
            ),
            RAW.replace(b'"title":"Caption"', b'"title":null'),
            RAW + b"{}",
            b" ",
        ):
            path.write_bytes(raw)
            for operation in ("source-declare", "source-upload"):
                assert invoke(cli, origin, operation, path).returncode == 2
        path.write_bytes(RAW)
        assert (
            invoke(cli, origin, "source-upload", path, target="../private").returncode
            == 2
        )
        assert (
            invoke(cli, origin, "source-status", project="../private").returncode == 2
        )
        assert requests == []


def test_source_crossed_or_malformed_receipts_are_uncertain_writes(cli, tmp_path):
    path = tmp_path / "briefs.json"
    path.write_bytes(RAW)
    with http_fixture() as (origin, response, requests):
        variants = [
            source() | {"project_id": SOURCE},
            source() | {"source_id": PROJECT},
            source() | {"sha256": "sha256:" + "f" * 64},
            source() | {"byte_count": len(RAW) + 1},
            source() | {"media_type": "text/csv"},
            source() | {"status": "imported"},
            source() | {"storage_key": "private"},
        ]
        for body in variants:
            response.update(status=200, body=json.dumps(body).encode())
            result = invoke(cli, origin, "source-upload", path)
            assert result.returncode == 1 and result.stdout == ""
            error = json.loads(result.stderr)["error"]
            assert error["code"] == "invalid_api_response"
            assert error["outcome_unknown"] is True
        assert len(requests) == len(variants)


def test_source_put_error_envelope_and_connection_loss(cli, tmp_path):
    path = tmp_path / "briefs.json"
    path.write_bytes(RAW)
    with http_fixture() as (origin, response, requests):
        response.update(status=403, body=json.dumps(canonical_error()).encode())
        denied = invoke(cli, origin, "source-upload", path)
        assert denied.returncode == 1
        assert not json.loads(denied.stderr)["error"].get("outcome_unknown", False)
        for status, body in (
            (403, b'{"error":{"code":"permission_not_granted"}}'),
            (500, json.dumps(canonical_error()).encode()),
        ):
            response.update(status=status, body=body)
            result = invoke(cli, origin, "source-upload", path)
            assert result.returncode == 1
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response.update(drop=True)
        result = invoke(cli, origin, "source-upload", path)
        assert result.returncode == 1
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 4
        assert response["raw_commands"] == [RAW] * 4


def test_source_put_http2_goaway_never_replays_bytes(cli, tmp_path):
    path = tmp_path / "briefs.json"
    path.write_bytes(RAW)
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = invoke(cli, origin, "source-upload", path, extra_env=env)
    assert connections == ["h2"] and bodies == [RAW]
    assert result.returncode == 1
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "service_unavailable" and error["outcome_unknown"] is True
