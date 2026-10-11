"""Canonical contribution/rule projection, pre-filtered before any response bound."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, delete, func, insert, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contributions.api.records import (
    InvalidContributionCursor,
    ContributionExportTooLarge,
    ContributionExportUnavailable,
    ContributionReadRequest,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition, ContributionPolicyVersion, ContributionRule,
)
from app.modules.contributions.records.models import ContributionRecord
from app.core.identifiers import new_record_id
from app.modules.contributions.records.cursors import ContributionCursor, ContributionCursorCodec, contribution_query_digest
from app.modules.contributions.records.models import ContributionExportMember, ContributionExportMembership
from app.modules.contributions.records.read_facts import ContributionReadFacts, ContributionReadPage, FrozenContributionAward


class ContributionReadRepository:
    """Read immutable facts and frozen terms in the caller's authorized snapshot."""

    def __init__(self, session: AsyncSession, *, cursor_codec: ContributionCursorCodec | None) -> None:
        """Share transaction ownership; no economic insert/update or commit is exposed."""
        self._session = session
        self._cursor_codec = cursor_codec

    @staticmethod
    def _selection(query, request):
        """Share original selection with membership capture and canonical page loading."""
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
        return query

    async def _membership(self, request):
        """Capture once or prove the signed, sealed original selection after fresh AUTH."""
        now = await self._session.scalar(select(func.clock_timestamp()))
        digest = contribution_query_digest(request)
        position = None
        if request.cursor is not None:
            if self._cursor_codec is None:
                raise ContributionExportUnavailable("Contribution export pagination unavailable")
            position = self._cursor_codec.decode(request.cursor, query_digest=digest, now=now)
            header = await self._session.scalar(select(ContributionExportMembership).where(
                ContributionExportMembership.id == position.export_id,
            ).with_for_update(read=True, key_share=True))
            if header is None or not header.sealed or (
                header.actor_profile_id, header.query_digest, header.exported_at, header.expires_at,
                header.audience, header.project_id, header.output_format, header.page_size,
                header.contribution_type, header.recorded_from, header.recorded_before,
            ) != (str(request.actor_profile_id), digest, position.exported_at, position.expires_at,
                  request.audience, None if request.project_id is None else str(request.project_id),
                  request.output_format, request.page_size, request.contribution_type,
                  request.recorded_from, request.recorded_before):
                raise InvalidContributionCursor("Invalid contribution export cursor")
            return header, position
        selected = self._selection(select(ContributionRecord.id, ContributionRecord.created_at), request)
        count = await self._session.scalar(select(func.count()).select_from(selected.limit(100001).subquery()))
        if count > 100000:
            raise ContributionExportTooLarge("Contribution export exceeds 100000 records; narrow the filters")
        if count > request.page_size and self._cursor_codec is None:
            raise ContributionExportUnavailable("Contribution export pagination unavailable")
        # Private expired membership only. Current page headers are protected by
        # key-share locks; economic records are never targets of this cleanup.
        expired = select(ContributionExportMembership.id).where(
            ContributionExportMembership.expires_at <= now,
        ).order_by(ContributionExportMembership.expires_at, ContributionExportMembership.id).limit(100)
        expired_ids = tuple(await self._session.scalars(expired.with_for_update(skip_locked=True)))
        if expired_ids:
            await self._session.execute(delete(ContributionExportMembership).where(
                ContributionExportMembership.id.in_(expired_ids),
            ))
        header = ContributionExportMembership(
            id=new_record_id(), actor_profile_id=str(request.actor_profile_id), query_digest=digest,
            exported_at=now, expires_at=now + timedelta(minutes=15), member_count=count, sealed=False,
            audience=request.audience, project_id=None if request.project_id is None else str(request.project_id),
            output_format=request.output_format, page_size=request.page_size,
            contribution_type=request.contribution_type, recorded_from=request.recorded_from,
            recorded_before=request.recorded_before,
        )
        self._session.add(header)
        await self._session.flush()
        capture = self._selection(select(literal(header.id), ContributionRecord.id,
                                         ContributionRecord.created_at), request)
        await self._session.execute(insert(ContributionExportMember).from_select(
            ["export_id", "contribution_id", "recorded_at"], capture,
        ))
        header.sealed = True
        await self._session.flush()
        return header, position

    async def read(self, request: ContributionReadRequest) -> ContributionReadPage:
        """Read complete award definitions for a bounded original-membership page."""
        request = ContributionReadRequest.model_validate(request)
        header, position = await self._membership(request)
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
        query = self._selection(query, request).join(ContributionExportMember, and_(
            ContributionExportMember.contribution_id == ContributionRecord.id,
            ContributionExportMember.recorded_at == ContributionRecord.created_at,
            ContributionExportMember.export_id == header.id,
        ))
        if position is not None:
            query = query.where(tuple_(ContributionRecord.created_at, ContributionRecord.id) >
                                tuple_(position.last_recorded_at, position.last_contribution_id))
        rows = (await self._session.execute(query.order_by(
            ContributionRecord.created_at, ContributionRecord.id,
        ).limit(request.page_size + 1))).all()
        more = len(rows) > request.page_size
        rows = rows[:request.page_size]
        next_cursor = None
        if more:
            last = rows[-1][0]
            next_cursor = self._cursor_codec.encode(ContributionCursor(
                header.id, header.exported_at, header.expires_at, last.created_at, last.id,
            ), query_digest=header.query_digest)
        if not rows:
            return ContributionReadPage(records=(), exported_at=header.exported_at, next_cursor=None)
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
        return ContributionReadPage(
            records=tuple(self._facts(row, version, mode, tuple(by_rule[rule]))
                          for row, version, rule, mode in rows),
            exported_at=header.exported_at, next_cursor=next_cursor,
        )

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
