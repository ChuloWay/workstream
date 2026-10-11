"""Built offline CSV conversion produces the exact server-accepted JSON source."""

from hashlib import sha256
import json

from app.modules.tasks.api.task_import import parse_task_import


def convert(cli, source, destination, *extra):
    return cli(
        "not-an-api-origin",
        "",
        "--output",
        "json",
        "project",
        "task-batch",
        "convert-csv",
        "--input",
        str(source),
        "--out",
        str(destination),
        *extra,
    )


def test_offline_conversion_server_contract_and_no_clobber(cli, tmp_path):
    source = tmp_path / "briefs.csv"
    source.write_text(
        "source_id,title,description,category,skill_tags,languages,tools\n"
        'brief-é,"Caption, français","First line\n日本語",caption,'
        "review;accuracy,fr;ja,editor\n",
        encoding="utf-8",
    )
    destination = tmp_path / "briefs.json"
    result = convert(cli, source, destination, "--label", "Multilingual briefs")
    assert result.returncode == 0 and result.stderr == "", result.stderr
    raw = destination.read_bytes()
    report = json.loads(result.stdout)
    assert report == {
        "json_path": str(destination),
        "sha256": "sha256:" + sha256(raw).hexdigest(),
        "byte_count": len(raw),
        "row_count": 1,
    }
    parsed = parse_task_import(raw)
    assert parsed.sha256 == report["sha256"]
    assert parsed.byte_count == report["byte_count"]
    task = parsed.document.tasks[0]
    assert task.external_task_id == "brief-é"
    assert task.title == "Caption, français"
    assert task.description == "First line\n日本語"
    assert task.task_type == "caption"
    assert task.skill_tags == ["review", "accuracy", "fr", "ja", "editor"]
    assert parsed.document.metadata.label == "Multilingual briefs"

    repeated = convert(cli, source, destination)
    assert repeated.returncode == 2
    assert json.loads(repeated.stderr)["error"]["code"] == "invalid_arguments"
    assert destination.read_bytes() == raw
    second = tmp_path / "second.json"
    assert (
        convert(cli, source, second, "--label", "Multilingual briefs").returncode == 0
    )
    assert second.read_bytes() == raw


def test_invalid_csv_does_not_create_or_modify_output(cli, tmp_path):
    source = tmp_path / "briefs.csv"
    destination = tmp_path / "briefs.json"
    for raw in (
        b"external_task_id,title,description\na,T,D\na,T,D\n",
        b"external_task_id,title,description\na,T,D\xff\n",
        b"external_task_id,title,description\na,T,D\x00\n",
        b"external_task_id,title,description\na,T\n",
        b'external_task_id,title,description\na,"broken,D\n',
        b"external_task_id,title,description,unknown\na,T,D,x\n",
    ):
        source.write_bytes(raw)
        result = convert(cli, source, destination)
        assert result.returncode == 2
        assert json.loads(result.stderr)["error"]["code"] == "invalid_task_import_csv"
        assert not destination.exists()


def test_csv_500_vs_501_rows(cli, tmp_path):
    source = tmp_path / "briefs.csv"
    source.write_text(
        "external_task_id,title,description\n"
        + "".join(f"brief-{index},Task,Instructions\n" for index in range(500)),
        encoding="utf-8",
    )
    destination = tmp_path / "briefs.json"
    result = convert(cli, source, destination)
    assert result.returncode == 0, result.stderr
    assert len(parse_task_import(destination.read_bytes()).document.tasks) == 500
    with source.open("a", encoding="utf-8") as stream:
        stream.write("brief-501,Task,Instructions\n")
    refused = tmp_path / "refused.json"
    result = convert(cli, source, refused)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "invalid_task_import_csv"
    assert not refused.exists()
