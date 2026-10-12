"""Predecessor rules require selected custody, never a substitute context hash."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.identifiers import new_record_id
from app.modules.artifacts.api import SubmissionBundlePreparationRejected
from app.modules.artifacts.submission_admission import PreparedSubmissionBundlePreparationCommand


def _command(admission):
    return PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(scalar=AsyncMock(return_value=admission)),
        authority=SimpleNamespace(),
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=Mock(),
    )


def _task():
    return SimpleNamespace(predecessor=SimpleNamespace(submission_id=new_record_id()))


@pytest.mark.asyncio
async def test_predecessor_uses_only_its_selected_rules_commitment():
    admission = SimpleNamespace(
        selected_pre_submit_run_id=new_record_id(),
        pre_submit_evidence_set_id=None,
        selected_rules_sha256="sha256:" + "1" * 64,
        locked_policy_context_hash="sha256:" + "2" * 64,
    )
    command = _command(admission)
    assert await command._load_predecessor_rules(_task()) == admission.selected_rules_sha256


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ("admission", "run", "rules", "contradictory_evidence"))
async def test_missing_selected_predecessor_custody_rejects(missing):
    admission = SimpleNamespace(
        selected_pre_submit_run_id=new_record_id(),
        pre_submit_evidence_set_id=None,
        selected_rules_sha256="sha256:" + "1" * 64,
        locked_policy_context_hash="sha256:" + "2" * 64,
    )
    if missing == "admission":
        admission = None
    elif missing == "run":
        admission.selected_pre_submit_run_id = None
    elif missing == "rules":
        admission.selected_rules_sha256 = None
    else:
        admission.pre_submit_evidence_set_id = new_record_id()
    command = _command(admission)
    with pytest.raises(SubmissionBundlePreparationRejected) as rejected:
        await command._load_predecessor_rules(_task())
    assert str(rejected.value) == "submission_canonical_predecessor_unavailable"


@pytest.mark.asyncio
async def test_initial_submission_needs_no_predecessor_rules():
    command = _command(None)
    assert await command._load_predecessor_rules(SimpleNamespace(predecessor=None)) is None
    command._session.scalar.assert_not_called()
