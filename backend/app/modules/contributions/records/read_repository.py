"""Canonical contribution/rule projection, pre-filtered before any response bound."""

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contributions.api.records import (
    MAX_EXPORT_CONTRIBUTIONS,
    ContributionExportTooLarge,
    ContributionExportUnavailable,
    ContributionReadRequest,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition, ContributionPolicyVersion, ContributionRule,
)
from app.modules.contributions.records.models import ContributionRecord
from app.modules.contributions.records.read_facts import ContributionReadFacts, FrozenContributionAward


class ContributionReadRepository:
    """Read immutable facts and frozen terms in the caller's authorized snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        """Share transaction ownership; no economic insert/update or commit is exposed."""
        self._session = session

    async def read(self, request: ContributionReadRequest) -> tuple[ContributionReadFacts, ...]:
        """Probe one excess contribution before loading its complete definition sets."""
        request = ContributionReadRequest.model_validate(request)
        query = select(ContributionRecord, ContributionPolicyVersion.version_number,
                       ContributionRule.id, ContributionRule.compensation_mode).outerjoin(
            ContributionPolicyVersion,
            and_(ContributionPolicyVersion.id == ContributionRecord.contribution_policy_version_id,
                 ContributionPolicyVersion.project_id == ContributionRecord.project_id),
        ).outerjoin(ContributionRule, and_(
            ContributionRule.contribution_policy_version_id == ContributionRecord.contribution_policy_version_id,
            ContributionRule.project_id == ContributionRecord.project_id,
            ContributionRule.contribution_type == ContributionRecord.contribution_type,
        ))
        if request.audience == "self":
            query = query.where(ContributionRecord.contributor_id == str(request.actor_profile_id))
        if request.project_id is not None:
            query = query.where(ContributionRecord.project_id == str(request.project_id))
        if request.contribution_type is not None:
            query = query.where(ContributionRecord.contribution_type == request.contribution_type)
        if request.recorded_from is not None:
            query = query.where(ContributionRecord.created_at >= request.recorded_from)
        if request.recorded_before is not None:
            query = query.where(ContributionRecord.created_at < request.recorded_before)
        rows = (await self._session.execute(query.order_by(
            ContributionRecord.created_at, ContributionRecord.id,
        ).limit(MAX_EXPORT_CONTRIBUTIONS + 1))).all()
        if len(rows) > MAX_EXPORT_CONTRIBUTIONS:
            raise ContributionExportTooLarge("Contribution export exceeds 1000 records; narrow the filters")
        if not rows:
            return ()
        if any(version is None or rule is None or mode is None for _, version, rule, mode in rows):
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        rule_ids = {rule for _, _, rule, _ in rows}
        definitions = (await self._session.scalars(select(ContributionAwardDefinition).where(
            ContributionAwardDefinition.contribution_rule_id.in_(rule_ids),
        ).order_by(ContributionAwardDefinition.instrument_type))).all()
        by_rule = {rule_id: [] for rule_id in rule_ids}
        for definition in definitions:
            by_rule[definition.contribution_rule_id].append(FrozenContributionAward(
                id=definition.id, instrument=definition.instrument_type,
                unit=definition.unit_code, quantity=definition.quantity,
            ))
        return tuple(self._facts(row, version, mode, tuple(by_rule[rule]))
                     for row, version, rule, mode in rows)

    @staticmethod
    def _facts(row, version, mode, definitions) -> ContributionReadFacts:
        """Validate the exact stored source shape without deriving new recognition."""
        return ContributionReadFacts(
            id=row.id, project_id=UUID(row.project_id), task_id=UUID(row.task_id),
            submission_id=UUID(row.submission_id), contribution_type=row.contribution_type,
            contributor_id=UUID(row.contributor_id), source_review_id=row.source_review_id,
            source_review_lease_id=row.source_review_lease_id,
            source_final_acceptance_id=row.source_final_acceptance_id,
            source_task_assignment_id=(None if row.source_task_assignment_id is None
                                       else UUID(row.source_task_assignment_id)),
            artifact_hash=row.artifact_hash,
            contribution_policy_version_id=row.contribution_policy_version_id,
            recorded_at=row.created_at, policy_version_number=version,
            compensation_mode=mode, award_definitions=definitions,
        )
