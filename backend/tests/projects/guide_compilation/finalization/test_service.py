"""Finalization outcomes and strict PREP-before-product ordering."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.modules.authorization.api import AuthorizationDenied
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import _UnavailableAuthorization
from .support import scenario


@pytest.mark.parametrize("mode", ["missing", "nested", "pending"])
async def test_finalization_requires_root_transaction(mode):
    case = scenario()
    if mode == "missing":
        case.session.active = False
    elif mode == "nested":
        case.session.nested = True
    else:
        case.session.dirty.add(object())
    with pytest.raises(ProjectGuideSetupFinalizationError, match="source_state_unavailable"):
        await case.service.finalize(case.command)
    assert case.repo.calls == []
    assert case.auth.events == []


async def test_unavailable_authorization_denies_before_product_lock():
    case = scenario()
    case.service._authorization = _UnavailableAuthorization()
    with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
        await case.service.finalize(case.command)
    assert case.repo.calls == ["lookup"]


async def test_blocked_finalization_binds_only_sufficiency():
    case = scenario("guide_blocked")
    receipt = await case.service.finalize(case.command)
    assert receipt.setup_outcome == "sufficiency_blocked"
    assert receipt.sufficiency_report_id == case.auth.expected.sufficiency_report_id
    assert receipt.artifact_policy_id is None


async def test_ready_with_warnings_preserves_classification():
    case = scenario("draft_ready_with_warnings")
    receipt = await case.service.finalize(case.command)
    assert receipt.result_classification == "draft_ready_with_warnings"
    assert receipt.setup_outcome == "policy_draft_ready"


async def test_blocked_finalization_sets_guide_sufficiency_step():
    case = scenario("guide_blocked")
    await case.service.finalize(case.command)
    assert case.view.setup.current_step == "guide_sufficiency"


async def test_ready_finalization_sets_policy_derivation_step():
    case = scenario()
    await case.service.finalize(case.command)
    assert case.view.setup.current_step == "submission_artifact_policy_derivation"


async def test_consume_observes_no_product_mutation():
    case = scenario()
    await case.service.finalize(case.command)
    assert case.auth.observed_product_calls == ("lookup", "lock", "receipts")
    assert case.repo.calls == ["lookup", "lock", "receipts", "persist"]


async def test_prepared_authority_closes_once_on_success():
    case = scenario()
    await case.service.finalize(case.command)
    assert case.auth.events == ["prepare", "consume", "close"]
    assert case.auth.handles[0].closed


async def test_consume_denial_has_no_product_effect():
    case = scenario()
    case.auth.consume_error = AuthorizationDenied("denied")
    with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
        await case.service.finalize(case.command)
    assert "persist" not in case.repo.calls
    assert case.view.setup.status == "queued"


async def test_consume_exception_has_no_product_effect():
    case = scenario()
    case.auth.consume_error = RuntimeError("unexpected")
    with pytest.raises(RuntimeError, match="unexpected"):
        await case.service.finalize(case.command)
    assert "persist" not in case.repo.calls


@pytest.mark.parametrize("error", [AuthorizationDenied("denied"), RuntimeError("unexpected")])
async def test_prepared_authority_closes_once_on_consume_denial(error):
    case = scenario()
    case.auth.consume_error = error
    with pytest.raises((ProjectGuideSetupFinalizationError, RuntimeError)):
        await case.service.finalize(case.command)
    assert case.auth.events == ["prepare", "consume", "close"]


async def test_close_failure_precedes_product_mutation():
    case = scenario()
    case.auth.close_error = RuntimeError("close failed")
    with pytest.raises(RuntimeError, match="close failed"):
        await case.service.finalize(case.command)
    assert "persist" not in case.repo.calls
    assert case.auth.events == ["prepare", "consume", "close"]


async def test_prepared_authority_closes_once_on_unexpected_premutation_exception():
    case = scenario()
    case.repo.failure = RuntimeError("unexpected lock error")
    with pytest.raises(RuntimeError, match="unexpected lock error"):
        await case.service.finalize(case.command)
    assert case.auth.events == ["prepare", "close"]
    assert "persist" not in case.repo.calls


@pytest.mark.parametrize(
    "field",
    [
        "actor_profile_id",
        "identity_link_id",
        "scope_project_id",
        "resource_id",
        "service_identity",
        "action_id",
        "permission_id",
        "resource_type",
        "resource_context_digest",
    ],
)
async def test_wrong_authority_receipt_denies(field):
    case = scenario()
    value = (
        uuid4()
        if field.endswith("_id") and field not in {"action_id", "permission_id"}
        else "wrong"
    )
    if field == "resource_context_digest":
        value = "sha256:" + "f" * 64
    case.auth.receipt_transform = lambda receipt: replace(receipt, **{field: value})
    with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
        await case.service.finalize(case.command)
    assert "persist" not in case.repo.calls


async def test_database_error_is_bounded():
    case = scenario()
    case.repo.failure = SQLAlchemyError("private database text")
    with pytest.raises(ProjectGuideSetupFinalizationError, match="^storage_unavailable$"):
        await case.service.finalize(case.command)
    assert case.auth.events == ["prepare", "close"]
