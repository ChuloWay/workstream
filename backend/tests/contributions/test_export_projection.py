"""Owner-port projection proof; real authority/snapshot proof remains integration work."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.identifiers import new_record_id
from app.modules.actors.api.contribution_labels import ContributionActorLabel
from app.modules.compensation.api.awards import CompensationAwardFacts
from app.modules.compensation.api.instruments import CompensationInstrumentType
from app.modules.contributions.api.records import (
    ContributionExportTooLarge, ContributionExportUnavailable, ContributionReadRequest,
)
from app.modules.contributions.records.read_facts import ContributionReadFacts, FrozenContributionAward
from app.modules.contributions.records.read_service import ContributionReadService
from app.modules.contributions.api.source_reads import (
    ContributionAcceptanceSourceFacts, ContributionTaskSourceFacts,
)

TIME = datetime(2026, 10, 10, tzinfo=UTC)


def facts(*, compensated=False):
    project, task, actor, submission, policy, acceptance = (new_record_id() for _ in range(6))
    definition = FrozenContributionAward(id=new_record_id(), instrument="money", unit="USD",
                                          quantity=Decimal("123.456789012345678901"))
    record = ContributionReadFacts(
        id=new_record_id(), project_id=project, task_id=task, submission_id=submission,
        contributor_id=actor, contribution_type="accepted_submission", source_review_id=None,
        source_review_lease_id=None, source_final_acceptance_id=acceptance,
        source_task_assignment_id=new_record_id(), artifact_hash="sha256:" + "a" * 64,
        contribution_policy_version_id=policy, recorded_at=TIME, policy_version_number=1,
        compensation_mode="compensated" if compensated else "unpaid",
        award_definitions=(definition,) if compensated else (),
    )
    awards = () if not compensated else (CompensationAwardFacts(
        id=new_record_id(), project_id=project, contribution_record_id=record.id,
        contributor_id=actor, contribution_policy_version_id=policy,
        award_definition_id=definition.id, adapter_binding_id=new_record_id(),
        instrument_type=CompensationInstrumentType.MONEY, unit_code="USD",
        quantity=definition.quantity, created_at=TIME, correlation_id=new_record_id(),
    ),)
    return SimpleNamespace(
        record=record, awards=awards,
        task=ContributionTaskSourceFacts(project_id=project, task_id=task, title="Task",
                                       source_type="manual", source_ref=None, external_task_id=None),
        actor=ContributionActorLabel(actor_profile_id=actor, display_name="Ada"),
        acceptance=ContributionAcceptanceSourceFacts(
            id=acceptance, project_id=project, task_id=task, submission_id=submission,
            acceptance_source="task_post_submit_route", accepted_submitter_id=actor,
            accepted_at=TIME, source_review_id=None, source_routing_manifest_id=new_record_id(),
        ),
    )


class Ports:
    def __init__(self, value):
        self.value, self.authorized = value, False

    async def authorize(self, request):
        self.authorized = True

    async def read(self, request):
        assert self.authorized, "owner load preceded authority"
        return (self.value.record,)

    async def read_contribution_awards(self, selected):
        assert selected == (self.value.record.id,)
        return self.value.awards

    async def read_contribution_tasks(self, selected):
        assert selected == ((self.value.record.project_id, self.value.record.task_id),)
        return (self.value.task,)

    async def read_contribution_labels(self, selected):
        assert selected == (self.value.record.contributor_id,)
        return (self.value.actor,)

    async def read_final_acceptances(self, selected):
        assert selected == ((self.value.record.project_id, self.value.record.source_final_acceptance_id),)
        return (self.value.acceptance,)


def service(ports):
    return ContributionReadService(authorization=ports, records=ports, awards=ports,
                                   acceptances=ports, tasks=ports, actors=ports)


def request(value):
    return ContributionReadRequest(audience="self", actor_profile_id=value.record.contributor_id)


@pytest.mark.parametrize("compensated", [False, True])
async def test_projection_preserves_source_and_exact_unpaid_or_money_set(compensated):
    value = facts(compensated=compensated)
    response = await service(Ports(value)).read(request(value))
    item, = response.items
    assert item.source_final_acceptance_id == value.acceptance.id
    assert item.acceptance_routing_manifest_id == value.acceptance.source_routing_manifest_id
    assert item.accepted_at == value.acceptance.accepted_at
    assert item.recorded_at == value.record.recorded_at
    assert [award.quantity for award in item.awards] == [format(award.quantity, "f") for award in value.awards]
    assert "adapter_binding_id" not in item.model_dump(mode="json")


@pytest.mark.parametrize("field", ["project_id", "contributor_id", "contribution_policy_version_id", "unit_code", "quantity", "award_definition_id"])
async def test_crossed_award_lineage_or_rounded_amount_cannot_be_exported(field):
    value = facts(compensated=True)
    changed = {"unit_code": "EUR", "quantity": Decimal("123.46")}.get(field, new_record_id())
    value.awards = (value.awards[0].model_copy(update={field: changed}),)
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))


async def test_missing_award_or_foreign_contributor_loader_result_is_unavailable():
    value = facts(compensated=True)
    value.awards = ()
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))
    value = facts()
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(ContributionReadRequest(
            audience="self", actor_profile_id=new_record_id(),
        ))


async def test_crossed_source_time_or_task_projection_cannot_change_identity():
    value = facts()
    value.acceptance = value.acceptance.model_copy(update={"submission_id": new_record_id()})
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))
    value = facts()
    value.task = value.task.model_copy(update={"project_id": new_record_id()})
    with pytest.raises(ContributionExportUnavailable):
        await service(Ports(value)).read(request(value))


async def test_explicit_over_limit_refusal_is_not_reclassified_as_unavailability():
    value = facts()

    class TooLarge(Ports):
        async def read(self, request):
            assert self.authorized
            raise ContributionExportTooLarge("narrow the filters")

        async def read_contribution_awards(self, selected):
            pytest.fail("over-limit response loaded award data")

    with pytest.raises(ContributionExportTooLarge, match="narrow"):
        await service(TooLarge(value)).read(request(value))


async def test_faulty_over_limit_loader_cannot_start_owner_projections():
    value = facts()

    class OverLimit(Ports):
        async def read(self, request):
            assert self.authorized
            return tuple(self.value.record.model_copy(update={"id": new_record_id()})
                         for _ in range(1001))

        async def read_contribution_awards(self, selected):
            pytest.fail("over-limit loader started owner projections")

    with pytest.raises(ContributionExportTooLarge):
        await service(OverLimit(value)).read(request(value))


async def test_completed_review_retains_its_source_without_an_acceptance_time():
    value = facts()
    review_id, lease_id = new_record_id(), new_record_id()
    value.record = value.record.model_copy(update={
        "contribution_type": "completed_review", "source_review_id": review_id,
        "source_review_lease_id": lease_id, "source_final_acceptance_id": None,
        "source_task_assignment_id": None,
    })

    class ReviewPorts(Ports):
        async def read_final_acceptances(self, selected):
            assert selected == ()
            return ()

    response = await service(ReviewPorts(value)).read(request(value))
    item, = response.items
    assert (item.source_review_id, item.source_review_lease_id) == (review_id, lease_id)
    assert item.recorded_at == TIME
    assert item.accepted_at is item.acceptance_source is None
    assert item.acceptance_review_id is item.acceptance_routing_manifest_id is None


async def test_complete_money_and_points_set_retains_each_original_identity():
    value = facts(compensated=True)
    definition = FrozenContributionAward(id=new_record_id(), instrument="project_points",
                                          unit="FLOW", quantity=Decimal("12345"))
    value.record = value.record.model_copy(update={
        "award_definitions": value.record.award_definitions + (definition,),
    })
    points = value.awards[0].model_copy(update={
        "id": new_record_id(), "award_definition_id": definition.id,
        "instrument_type": CompensationInstrumentType.PROJECT_POINTS,
        "unit_code": "FLOW", "quantity": definition.quantity,
    })
    value.awards += (points,)
    response = await service(Ports(value)).read(request(value))
    item, = response.items
    assert {(award.award_id, award.award_definition_id, award.quantity) for award in item.awards} == {
        (award.id, award.award_definition_id, format(award.quantity, "f")) for award in value.awards
    }


async def test_human_acceptance_review_reference_does_not_replace_contribution_source():
    value = facts()
    review_id = new_record_id()
    value.acceptance = value.acceptance.model_copy(update={
        "acceptance_source": "human_review", "source_review_id": review_id,
        "source_routing_manifest_id": None,
    })
    response = await service(Ports(value)).read(request(value))
    item, = response.items
    assert item.contribution_type == "accepted_submission"
    assert item.acceptance_review_id == review_id
    assert item.source_review_id is item.source_review_lease_id is None
    assert item.source_final_acceptance_id == value.acceptance.id
