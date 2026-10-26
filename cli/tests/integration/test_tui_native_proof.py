"""Falsification tests for native proof selection, outcomes and receipt custody."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

import tui_native_proof
from tui_native_proof import ProofError, Reports, run_tests, validate, verify


BINDING = {
    "source": "a" * 40,
    "platform": "linux-amd64",
    "run_id": "1",
    "run_attempt": "2",
    "suite": "cli/tests/integration/test_tui_http.py",
}


def passing():
    return {
        "binding": BINDING,
        "finished": True,
        "exit_code": 0,
        "collected": ["test_suite.py::test_a", "test_suite.py::test_b"],
        "selected": ["test_suite.py::test_a", "test_suite.py::test_b"],
        "deselected": [],
        "collection_errors": [],
        "reports": [
            {
                "nodeid": node,
                "when": phase,
                "outcome": "passed",
                "has_wasxfail": False,
                "wasxfail": None,
            }
            for node in ["test_suite.py::test_a", "test_suite.py::test_b"]
            for phase in ["setup", "call", "teardown"]
        ],
    }


def test_valid_control():
    assert validate(passing(), BINDING) == 2


@pytest.mark.parametrize(
    "defect",
    [
        "omitted_test",
        "duplicate_node",
        "empty",
        "deselected",
        "selected_omission",
        "duplicate_report",
        "uncollected_report",
        "skip",
        "xfail",
        "xpass",
        "failure",
        "collection_error",
        "exit_failure",
        "interrupted",
        "binding",
        "missing_teardown",
        "phase_order",
    ],
)
def test_corrupt_evidence_fails_closed(defect):
    proof = deepcopy(passing())
    if defect == "omitted_test":
        proof["reports"] = proof["reports"][:3]
    elif defect == "duplicate_node":
        proof["collected"].append(proof["collected"][0])
    elif defect == "empty":
        proof.update(collected=[], selected=[], reports=[])
    elif defect == "deselected":
        proof["deselected"] = [proof["collected"][0]]
    elif defect == "selected_omission":
        proof["selected"].pop()
    elif defect == "duplicate_report":
        proof["reports"].append(proof["reports"][0])
    elif defect == "uncollected_report":
        proof["reports"][0]["nodeid"] = "test_other.py::test_unknown"
    elif defect in {"skip", "xfail", "xpass", "failure"}:
        call = proof["reports"][1]
        call["outcome"] = {
            "skip": "skipped",
            "xfail": "skipped",
            "xpass": "passed",
            "failure": "failed",
        }[defect]
        if defect in {"xfail", "xpass"}:
            call.update(has_wasxfail=True, wasxfail="")
    elif defect == "collection_error":
        proof["collection_errors"] = [{"nodeid": "broken.py", "outcome": "failed"}]
    elif defect == "exit_failure":
        proof["exit_code"] = 1
    elif defect == "interrupted":
        proof["finished"] = False
    elif defect == "binding":
        proof["binding"]["source"] = "b" * 40
    elif defect == "missing_teardown":
        proof["reports"].pop()
    elif defect == "phase_order":
        proof["reports"][0]["when"] = "call"
    with pytest.raises(ProofError):
        validate(proof, BINDING)


@pytest.mark.parametrize(
    ("body", "accepted"),
    [
        ("def test_ok(): assert True", True),
        ("def test_bad(): assert False", False),
        ("import pytest\ndef test_skip(): pytest.skip('')", False),
        ("import pytest\n@pytest.mark.xfail\ndef test_xfail(): assert False", False),
        (
            "import pytest\n@pytest.mark.xfail(strict=False)\ndef test_xpass(): pass",
            False,
        ),
        ("def test_interrupt(): raise KeyboardInterrupt", False),
        ("# no tests", False),
        ("raise RuntimeError('collection failure')", False),
    ],
)
def test_real_pytest_outcomes(tmp_path, monkeypatch, body, accepted):
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only -k nonexistent")
    monkeypatch.setenv("PYTEST_PLUGINS", "nonexistent_plugin")
    suite = tmp_path / f"test_{tmp_path.name}.py"
    suite.write_text(body + "\n", encoding="utf-8")
    output = tmp_path / "proof"
    if accepted:
        run_tests(suite, BINDING, output)
        assert verify(output, BINDING) == 1
    else:
        with pytest.raises(ProofError):
            run_tests(suite, BINDING, output)
        assert not (output / "completion.json").exists()
    evidence = json.loads((output / "reports.json").read_text())
    assert evidence["binding"] == BINDING
    if "test_xfail" in body or "test_xpass" in body:
        assert any(report["has_wasxfail"] for report in evidence["reports"])
    if "test_xpass" in body:
        assert evidence["exit_code"] == 0  # Non-strict XPASS evades exit/JUnit totals.


@pytest.mark.parametrize("selection", ["deselect", "silent_omit", "duplicate"])
def test_real_collection_modification(tmp_path, selection):
    suite = tmp_path / f"test_{tmp_path.name}.py"
    suite.write_text("def test_a(): pass\ndef test_b(): pass\n", encoding="utf-8")

    class Selection:
        def pytest_collection_modifyitems(self, config, items):
            if selection == "deselect":
                config.hook.pytest_deselected(items=[items.pop()])
            elif selection == "silent_omit":
                items.pop()
            else:
                items.append(items[0])

    with pytest.raises(ProofError):
        run_tests(suite, BINDING, tmp_path / "proof", plugins=[Selection()])
    assert not (tmp_path / "proof/completion.json").exists()
    evidence = json.loads((tmp_path / "proof/reports.json").read_text())
    assert evidence["exit_code"] == 0 and not evidence["collection_errors"]
    assert len(evidence["collected"]) == 2
    assert len(evidence["selected"]) == (3 if selection == "duplicate" else 1)
    assert bool(evidence["deselected"]) == (selection == "deselect")


def test_receipt_rejects_stale_binding_tamper_and_failed_retry(tmp_path):
    suite = tmp_path / f"test_{tmp_path.name}.py"
    suite.write_text("def test_ok(): pass\n", encoding="utf-8")
    output = tmp_path / "proof"
    run_tests(suite, BINDING, output)
    for key in ["source", "platform", "run_id", "run_attempt"]:
        changed = BINDING | {key: "different"}
        with pytest.raises(ProofError):
            verify(output, changed)
    with (output / "reports.json").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ProofError):
        verify(output, BINDING)
    run_tests(suite, BINDING, output)
    with pytest.raises(ProofError):
        run_tests(suite, BINDING, output, extra_args=["--collect-only"])
    assert not (output / "completion.json").exists()


def test_abort_before_pytest_return_never_completes(tmp_path, monkeypatch):
    output = tmp_path / "proof"
    output.mkdir()
    (output / "completion.json").write_text("stale", encoding="utf-8")

    def abort(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(pytest, "main", abort)
    with pytest.raises(KeyboardInterrupt):
        run_tests(Path("test_suite.py"), BINDING, output)
    assert not (output / "completion.json").exists()
    assert json.loads((output / "reports.json").read_text())["finished"] is False


def test_wasxfail_presence_is_not_lost():
    class Report:
        nodeid, when, outcome, wasxfail = "test.py::test_a", "call", "passed", ""

    observer = Reports()
    observer.pytest_runtest_logreport(Report())
    assert observer.reports[0]["has_wasxfail"] is True
    assert observer.reports[0]["wasxfail"] == ""


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (ProofError("receipt count differs"), "ProofError: receipt count differs"),
        (OSError("credential_canary_private_path"), "OSError"),
        (ValueError("credential_canary_private_payload"), "ValueError"),
    ],
)
def test_main_rejection_discloses_only_fixed_proof_reason(
    tmp_path, monkeypatch, capsys, error, detail
):
    monkeypatch.setattr(
        tui_native_proof.sys,
        "argv",
        [
            "tui_native_proof.py",
            "verify",
            "--output",
            str(tmp_path),
            "--source",
            BINDING["source"],
            "--platform",
            BINDING["platform"],
            "--run-id",
            BINDING["run_id"],
            "--run-attempt",
            BINDING["run_attempt"],
        ],
    )

    def reject(*args):
        raise error

    monkeypatch.setattr(tui_native_proof, "verify", reject)
    assert tui_native_proof.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == f"native terminal proof rejected: {detail}\n"
