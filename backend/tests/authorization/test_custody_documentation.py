"""Current ART and REV documentation matches canonical authorization custody."""

from pathlib import Path

from tests.authorization.catalogue_fixtures import ART_CUSTODY_EXPECTATIONS, REV_CUSTODY_EXPECTATIONS


ART_ACTIVATION_CUSTODY_EXPECTATIONS = {
    "artifact.task_import_source.declare": "PILOT-02A",
    "artifact.task_import_source.upload": "PILOT-02A",
    "artifact.task_import_source.read": "PILOT-02A",
    "artifact.binding.read": "WS-AUTH-001-ART-02D-OPERATOR",
    "artifact.replica.read": "WS-AUTH-001-ART-02D-OPERATOR",
    "artifact.receipt.read": "WS-AUTH-001-ART-02D-OPERATOR",
    "artifact.verification_job.read": "WS-AUTH-001-ART-02D-OPERATOR",
    "artifact.verification_job.retry": "WS-AUTH-001-ART-02D-OPERATOR",
    "artifact.recovery_attempt.read": "WS-AUTH-001-ART-02D-OPERATOR",
    "artifact.audit.read": "WS-AUTH-001-ART-02D-OPERATOR",
    "operations.artifact_storage_admission.read": "WS-AUTH-001-ART-02D-OPERATOR",
    "artifact.verification.execute": "WS-AUTH-001-ART-02D-INTERNAL",
    "artifact.pending_work.scan": "WS-AUTH-001-ART-02D-INTERNAL",
    "artifact.put_attempt.resolve": "WS-AUTH-001-ART-02D-INTERNAL",
    "artifact.guide_source.ingest": "WS-XINT-002-04A",
    "artifact.guide_source.read": "WS-XINT-002-04B",
    "artifact.submission_bundle.prepare": "WS-XINT-002-05A",
    "artifact.pre_submit.checker_input.materialize": "WS-XINT-002-06A",
    "artifact.submission.binding.create": "WS-AUTH-001-ART-05",
    "artifact.post_submit.checker_input.materialize": "WS-XINT-002-06B",
    "artifact.checker_output.write": "WS-XINT-002-06B",
    "artifact.review_packet.materialize": "WS-XINT-002-07A",
    "artifact.review_evidence.binding.create": "Future REV-owned activation, not approved for v0.1",
    "artifact.checker_output.binding.create": "WS-XINT-002-06B",
}

def _parse_custody_table(document: Path, expected_actions: set[str]) -> dict[str, str]:
    rows = document.read_text(encoding="utf-8").splitlines()
    for header_index, row in enumerate(rows):
        if row not in {
            "| AUTH activation custodian | Exact planned ActionIds |",
            "| AUTH activation custodian | Exact ActionIds and current availability |",
            "| AUTH activation chunk | Exact planned ActionIds |",
            "| AUTH activation chunk | Exact ActionIds and current availability |",
        }:
            continue
        parsed: dict[str, str] = {}
        duplicates: set[str] = set()
        for table_row in rows[header_index + 2 :]:
            if not table_row.startswith("|"):
                break
            cells = [cell.strip() for cell in table_row.split("|")]
            assert len(cells) == 4
            owner = cells[1].strip("`")
            for action in cells[2].split("`")[1::2]:
                if action in parsed:
                    duplicates.add(action)
                parsed[action] = owner
        assert duplicates == set()
        if set(parsed) == expected_actions:
            return parsed
    raise AssertionError(f"exact custody table missing from {document}")

def test_art_custody_documentation_matches_the_independent_activation_fixture() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    custody_documents = (
        repository_root / "docs/spec_authorization_service.md",
        repository_root / "docs/engineering/authorization_activation_custody.md",
    )
    expected_custody = ART_ACTIVATION_CUSTODY_EXPECTATIONS
    expected_owner_counts = {
        "PILOT-02A": 3,
        "WS-AUTH-001-ART-02D-OPERATOR": 8,
        "WS-AUTH-001-ART-02D-INTERNAL": 3,
        "WS-XINT-002-04B": 1,
        "WS-XINT-002-04A": 1,
        "WS-XINT-002-05A": 1,
        "WS-XINT-002-06A": 1,
        "WS-AUTH-001-ART-05": 1,
        "WS-XINT-002-06B": 3,
        "WS-XINT-002-07A": 1,
        "Future REV-owned activation, not approved for v0.1": 1,
    }

    for document in custody_documents:
        parsed = _parse_custody_table(document, set(expected_custody))
        assert parsed == expected_custody
        assert {
            owner: sum(parsed_owner == owner for parsed_owner in parsed.values())
            for owner in set(parsed.values())
        } == expected_owner_counts

    spec = repository_root / "docs/spec_authorization_service.md"
    spec_rows = spec.read_text(encoding="utf-8").splitlines()
    parsed_permissions: dict[str, str] = {}
    for row in spec_rows:
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) < 6:
            continue
        action = cells[1].strip("`")
        if action in ART_CUSTODY_EXPECTATIONS:
            assert action not in parsed_permissions
            parsed_permissions[action] = cells[2].strip("`")
    assert parsed_permissions == {
        action: permission
        for action, (permission, _owner, _availability) in ART_CUSTODY_EXPECTATIONS.items()
    }

    operations = (repository_root / "docs/operations_authorization_service.md").read_text(
        encoding="utf-8"
    )
    assert "all 22 ART rows to ten exact activation custodians" in operations
    assert "the original 19 REV\nrows to seven exact AUTH custodians" in operations
    assert "v0.1 baseline.\nThe REV transfer adds no migration." in operations
    assert "does not grant Operator" in operations
    assert "verification retry remains independently gated" in operations
    assert "Catalogue entries and explicit runtime composition determine availability" in operations
    assert "a planned action is not activated by its presence in the catalogue" in operations

def test_rev_custody_documentation_matches_the_independent_catalogue_fixture() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    custody_documents = (
        repository_root / "docs/spec_authorization_service.md",
        repository_root / "docs/engineering/authorization_activation_custody.md",
    )
    expected_custody = {
        action: owner
        for action, (_permission, owner, _availability) in REV_CUSTODY_EXPECTATIONS.items()
    }
    expected_owner_counts = {
        "WS-AUTH-001-REV-05": 2,
        "WS-AUTH-001-REV-06": 5,
        "WS-AUTH-001-REV-07": 3,
        "WS-AUTH-001-REV-08": 1,
        "WS-AUTH-001-REV-09A": 1,
        "WS-AUTH-001-REV-11": 5,
        "WS-AUTH-001-REV-12": 2,
        "WS-XINT-003-08A": 2,
        "WS-XINT-003-08B": 1,
    }
    for document in custody_documents:
        parsed = _parse_custody_table(document, set(expected_custody))
        assert parsed == expected_custody
        assert {
            owner: sum(parsed_owner == owner for parsed_owner in parsed.values())
            for owner in set(parsed.values())
        } == expected_owner_counts

    spec_rows = (
        (repository_root / "docs/spec_authorization_service.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    parsed_permissions: dict[str, str] = {}
    for row in spec_rows:
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) < 5:
            continue
        action = cells[1].strip("`")
        if action in REV_CUSTODY_EXPECTATIONS:
            assert action not in parsed_permissions
            parsed_permissions[action] = cells[2].strip("`")
    assert parsed_permissions == {
        action: permission
        for action, (permission, _owner, _availability) in REV_CUSTODY_EXPECTATIONS.items()
    }

    operations = (repository_root / "docs/operations_authorization_service.md").read_text(
        encoding="utf-8"
    )
    assert "the original 19 REV\nrows to seven exact AUTH custodians" in operations
    assert "all 23 REV actions remain planned and unavailable" in operations
    assert "registers the four additional actions" in operations
