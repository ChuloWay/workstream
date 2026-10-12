"""Approved bindings resolve to exact immutable external registry facts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.identifiers import new_record_id
from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CapabilityParameter,
    CompilationStage,
    PostSubmissionBindingProposal,
    PreSubmissionBindingProposal,
    RequirementDisposition,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    ExternalCheckerSchema,
    external_checker_json_hash,
    ExternalCheckerRegistryUnavailable,
)
from app.modules.checkers.api.external_policy import (
    ExternalCheckerPolicyError,
    LockedWorkstreamDefault,
    MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS,
    SELECTED_POST_MATERIALIZATION_BUDGET_MS,
    compile_external_checker_policies,
    selected_post_submit_execution_budget_ms,
    selected_pre_submit_execution_budget_ms,
)
from app.modules.checkers.api.external import EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
from app.modules.artifacts.preparation import ArtifactPreparationLimits
from tests.checkers.external.support import registry_spec
from tests.projects.guide_compilation.helpers import result


def _entry(
    capability_id: str,
    phase: str,
    configuration_schema=None,
    *,
    deadline_ms: int | None = None,
) -> ExternalCheckerRegistryEntry:
    changes = {"capability_id": capability_id}
    if configuration_schema is not None:
        changes["configuration_schema"] = configuration_schema
    spec = registry_spec(phase).model_copy(update=changes)
    if deadline_ms is not None:
        spec = spec.model_copy(
            update={"resources": spec.resources.model_copy(update={"deadline_ms": deadline_ms})}
        )
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
            (entry.capability_id, entry.capability_version, entry.phase): entry for entry in entries
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
    entries = (
        _entry("acme.safe_archive", "pre_submit"),
        _entry("acme.quality_review", "post_submit"),
    )
    registry = _Registry(entries)

    pre, post = await compile_external_checker_policies(_proposal(), registry)

    assert pre.workstream_default.checker_id == "workstream.default"
    assert [(item.requirement_id, item.registry.registry_entry_id) for item in pre.entries] == [
        ("safe_archive", entries[0].registry_entry_id)
    ]
    assert [(item.requirement_id, item.registry.registry_entry_id) for item in post.entries] == [
        ("quality_review", entries[1].registry_entry_id)
    ]
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
async def test_compilation_refuses_requirement_and_registry_digest_substitution():
    proposal = _proposal()
    wrong_requirement = proposal.model_copy(
        update={
            "pre_submit_bindings": (
                proposal.pre_submit_bindings[0].model_copy(
                    update={"requirement_id": "quality_review"}
                ),
            )
        }
    )
    with pytest.raises(ExternalCheckerPolicyError, match="does not cover"):
        await compile_external_checker_policies(
            wrong_requirement,
            _Registry((_entry("acme.safe_archive", "pre_submit"),)),
        )

    entry = _entry("acme.safe_archive", "pre_submit")
    corrupt = entry.model_copy(update={"entry_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="entry digest"):
        await compile_external_checker_policies(proposal, _Registry((corrupt,)))


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
    assert selected_pre_submit_execution_budget_ms(pre, artifact_deadline_ms=150_000) == 150_000
    with pytest.raises(ExternalCheckerPolicyError, match="exceeds ART"):
        selected_pre_submit_execution_budget_ms(pre, artifact_deadline_ms=149_999)


@pytest.mark.asyncio
async def test_selected_post_maximum_fits_default_art_custody_and_rejects_overrun():
    image_deadline = (
        MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS
        - SELECTED_POST_MATERIALIZATION_BUDGET_MS
        - EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
    )
    _, policy = await compile_external_checker_policies(
        _proposal(),
        _Registry(
            (
                _entry("acme.safe_archive", "pre_submit"),
                _entry(
                    "acme.quality_review",
                    "post_submit",
                    deadline_ms=image_deadline,
                ),
            )
        ),
    )
    limits = ArtifactPreparationLimits()

    assert selected_post_submit_execution_budget_ms(
        policy,
        artifact_deadline_ms=int(limits.total_deadline_seconds * 1000),
    ) == MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS
    assert (
        limits.total_deadline_seconds + limits.cleanup_margin_seconds
        < limits.reservation_ttl_seconds
    )
    with pytest.raises(ExternalCheckerPolicyError, match="ART custody"):
        selected_post_submit_execution_budget_ms(
            policy,
            artifact_deadline_ms=MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS - 1,
        )

    too_slow = policy.model_copy(
        update={
            "entries": (
                policy.entries[0].model_copy(
                    update={
                        "registry": _entry(
                            "acme.quality_review",
                            "post_submit",
                            deadline_ms=image_deadline + 1,
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ExternalCheckerPolicyError, match="durable worker"):
        selected_post_submit_execution_budget_ms(too_slow)


@pytest.mark.asyncio
async def test_pre_configuration_is_schema_checked_and_locked_as_json():
    document = {
        "type": "object",
        "properties": {
            "threshold": {"type": "integer", "minimum": 1},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["threshold", "tags"],
        "additionalProperties": False,
    }
    schema = ExternalCheckerSchema(
        schema_id="acme.pre.configuration", schema_version="v1", document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    registry = _Registry((
        _entry("acme.safe_archive", "pre_submit", schema),
        _entry("acme.quality_review", "post_submit"),
    ))
    proposal = _proposal()
    parameters = (
        CapabilityParameter(name="threshold", value=3),
        CapabilityParameter(name="tags", value=("alpha", "beta")),
    )
    binding = proposal.pre_submit_bindings[0].model_copy(update={"parameters": parameters})
    configured = proposal.model_copy(update={"pre_submit_bindings": (binding,)})
    pre, _ = await compile_external_checker_policies(configured, registry)
    assert pre.entries[0].configuration == {"threshold": 3, "tags": ["alpha", "beta"]}
    assert pre.entries[0].configuration_sha256 == external_checker_json_hash(
        {"threshold": 3, "tags": ["alpha", "beta"]}
    )
    for invalid in ((), (CapabilityParameter(name="threshold", value="three"),)):
        wrong = binding.model_copy(update={"parameters": invalid})
        with pytest.raises(ValueError):
            await compile_external_checker_policies(
                proposal.model_copy(update={"pre_submit_bindings": (wrong,)}), registry,
            )


def test_pre_configuration_preserves_retained_empty_binding_and_rejects_duplicates():
    binding = _proposal().pre_submit_bindings[0]
    retained = {
        "requirement_id": "safe_archive", "capability_id": "acme.safe_archive",
        "capability_version": "v1.2.3", "stage": "pre_submit",
    }
    assert binding.model_dump(mode="json") == retained
    assert PreSubmissionBindingProposal.model_validate(retained).model_dump(mode="json") == retained
    duplicate = CapabilityParameter(name="threshold", value=3)
    with pytest.raises(ValueError, match="unique"):
        PreSubmissionBindingProposal.model_validate(retained | {"parameters": (duplicate, duplicate)})
