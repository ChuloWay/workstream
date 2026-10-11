"""Approved bindings resolve to exact immutable external registry facts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.identifiers import new_record_id
from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CompilationStage,
    PostSubmissionBindingProposal,
    PreSubmissionBindingProposal,
    RequirementDisposition,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistryUnavailable,
)
from app.modules.checkers.api.external_policy import (
    ExternalCheckerPolicyError,
    LockedWorkstreamDefault,
    compile_external_checker_policies,
    selected_pre_submit_execution_budget_ms,
)
from tests.checkers.external.support import registry_spec
from tests.projects.guide_compilation.helpers import result


def _entry(capability_id: str, phase: str) -> ExternalCheckerRegistryEntry:
    spec = registry_spec(phase).model_copy(update={"capability_id": capability_id})
    # Revalidate after changing one digest-bound specification field.
    spec = type(spec).model_validate(spec.model_dump())
    return ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=new_record_id(),
        entry_digest=spec.spec_digest,
        registration_operation_id=uuid4(),
        registered_by_actor_profile_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        created_at=datetime.now(UTC),
    )


class _Registry:
    def __init__(self, entries):
        self.entries = {
            (entry.capability_id, entry.capability_version, entry.phase): entry
            for entry in entries
        }
        self.calls = []

    async def read_identity(self, **identity):
        self.calls.append(identity)
        try:
            return self.entries[
                (
                    identity["capability_id"],
                    identity["capability_version"],
                    identity["phase"],
                )
            ]
        except KeyError as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc


def _proposal():
    pre = AtomicGuideRequirement(
        requirement_id="safe_archive",
        statement="Inspect the delivered archive.",
        disposition=RequirementDisposition.SUPPORTED_PRE_SUBMIT,
    )
    post = AtomicGuideRequirement(
        requirement_id="quality_review",
        statement="Evaluate the submitted work.",
        disposition=RequirementDisposition.SUPPORTED_POST_SUBMIT,
    )
    return result().model_copy(
        update={
            "requirements": (pre, post),
            "pre_submit_bindings": (
                PreSubmissionBindingProposal(
                    requirement_id=pre.requirement_id,
                    capability_id="acme.safe_archive",
                    capability_version="v1.2.3",
                    stage=CompilationStage.PRE_SUBMIT,
                ),
            ),
            "post_submit_bindings": (
                PostSubmissionBindingProposal(
                    requirement_id=post.requirement_id,
                    capability_id="acme.quality_review",
                    capability_version="v1.2.3",
                    stage=CompilationStage.POST_SUBMIT,
                ),
            ),
        }
    )


@pytest.mark.asyncio
async def test_compilation_locks_exact_phase_registry_entries_and_default():
    entries = (_entry("acme.safe_archive", "pre_submit"),
               _entry("acme.quality_review", "post_submit"))
    registry = _Registry(entries)

    pre, post = await compile_external_checker_policies(_proposal(), registry)

    assert pre.workstream_default.checker_id == "workstream.default"
    assert [(item.requirement_id, item.registry.registry_entry_id)
            for item in pre.entries] == [("safe_archive", entries[0].registry_entry_id)]
    assert [(item.requirement_id, item.registry.registry_entry_id)
            for item in post.entries] == [("quality_review", entries[1].registry_entry_id)]
    assert pre.entries[0].configuration == {}
    assert post.entries[0].configuration == {}
    assert [call["phase"] for call in registry.calls] == ["pre_submit", "post_submit"]


@pytest.mark.asyncio
async def test_compilation_refuses_missing_or_wrong_phase_registry_identity():
    proposal = _proposal()
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await compile_external_checker_policies(proposal, _Registry(()))

    wrong = _entry("acme.safe_archive", "post_submit")
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await compile_external_checker_policies(proposal, _Registry((wrong,)))

    class _SubstitutedRegistry:
        async def read_identity(self, **_identity):
            return _entry("acme.substituted", "pre_submit")

    with pytest.raises(ExternalCheckerPolicyError, match="identity"):
        await compile_external_checker_policies(proposal, _SubstitutedRegistry())


@pytest.mark.asyncio
async def test_compilation_refuses_blocked_capability_coverage():
    proposal = _proposal().model_copy(
        update={
            "status": "guide_blocked",
            "submission_artifact_policy": None,
            "capability_suggestions": (),
        }
    )
    with pytest.raises(ExternalCheckerPolicyError, match="coverage"):
        await compile_external_checker_policies(proposal, _Registry(()))


def test_locked_default_refuses_substituted_behavior_digest():
    with pytest.raises(ValueError, match="behavior"):
        LockedWorkstreamDefault(behavior_sha256="sha256:" + "0" * 64)


@pytest.mark.asyncio
async def test_selected_pre_budget_binds_ordered_deadlines_to_art_custody():
    pre, _ = await compile_external_checker_policies(
        _proposal(),
        _Registry(
            (
                _entry("acme.safe_archive", "pre_submit"),
                _entry("acme.quality_review", "post_submit"),
            )
        ),
    )
    assert selected_pre_submit_execution_budget_ms(
        pre, artifact_deadline_ms=150_000
    ) == 150_000
    with pytest.raises(ExternalCheckerPolicyError, match="exceeds ART"):
        selected_pre_submit_execution_budget_ms(
            pre, artifact_deadline_ms=149_999
        )
