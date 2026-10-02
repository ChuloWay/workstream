"""Caller-owned packet persistence; authorization and byte access stay separate."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.artifacts.api.review_packet import (
    ReviewGuideMember,
    ReviewPacketMembership,
    ReviewPacketMembershipRequest,
    ReviewPacketMembershipUnavailable,
    ReviewSubmissionMember,
)
from app.modules.reviews.models import ReviewLease, ReviewQueueEntry
from app.modules.reviews.packet.models import ReviewPacketGuideItem, ReviewPacketManifest
from app.modules.reviews.packet.schemas import ReviewPacketConflict, ReviewPacketStored


class ReviewPacketRepository:
    """Freeze one normalized packet per lease without committing or authorizing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(self, lease_id: UUID, membership: ReviewPacketMembership) -> ReviewPacketStored:
        project_id = membership.request.project_id
        lease = await self._session.scalar(
            select(ReviewLease)
            .where(
                ReviewLease.id == lease_id,
                ReviewLease.project_id == str(project_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if lease is None:
            raise ReviewPacketMembershipUnavailable()
        queue = await self._session.scalar(
            select(ReviewQueueEntry)
            .where(
                ReviewQueueEntry.id == lease.review_queue_entry_id,
                ReviewQueueEntry.project_id == str(project_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        existing = await self.read(project_id, lease_id)
        if existing is not None:
            if existing.membership != membership:
                raise ReviewPacketConflict()
            return existing
        if (
            queue is None
            or lease.status != "active"
            or queue.queue_state != "leased"
            or queue.active_lease_id != lease.id
        ):
            raise ReviewPacketMembershipUnavailable()
        packet = ReviewPacketManifest(
            id=new_record_id(),
            review_lease_id=lease_id,
            review_queue_entry_id=queue.id,
            packet_manifest_generation=lease.attempt_generation,
            packet_manifest_digest=canonical_json_hash(membership.model_dump(mode="json")),
            **{
                key: str(value) if isinstance(value, UUID) else value
                for key, value in membership.request.model_dump().items()
            },
            submission_binding_id=str(membership.submission.binding_id),
            submission_logical_role=membership.submission.logical_role,
            submission_media_type=membership.submission.media_type,
        )
        self._session.add(packet)
        await self._session.flush()
        self._session.add_all(
            [
                ReviewPacketGuideItem(
                    packet_id=packet.id,
                    **{
                        key: str(value) if isinstance(value, UUID) else value
                        for key, value in member.model_dump().items()
                    },
                )
                for member in membership.guide_documents
            ]
        )
        await self._session.flush()
        return ReviewPacketStored(
            packet_id=packet.id,
            review_lease_id=lease_id,
            review_queue_entry_id=queue.id,
            packet_manifest_generation=packet.packet_manifest_generation,
            packet_manifest_digest=packet.packet_manifest_digest,
            created_at=packet.created_at,
            membership=membership,
        )

    async def read(self, project_id: UUID, lease_id: UUID) -> ReviewPacketStored | None:
        """Project-qualified metadata only; no current authority or availability claim."""
        packet = await self._session.scalar(
            select(ReviewPacketManifest)
            .where(
                ReviewPacketManifest.project_id == str(project_id),
                ReviewPacketManifest.review_lease_id == lease_id,
            )
            .execution_options(populate_existing=True)
        )
        if packet is None:
            return None
        members = (
            await self._session.scalars(
                select(ReviewPacketGuideItem)
                .where(
                    ReviewPacketGuideItem.packet_id == packet.id,
                )
                .order_by(ReviewPacketGuideItem.item_order)
            )
        ).all()
        return ReviewPacketStored(
            packet_id=packet.id,
            review_lease_id=packet.review_lease_id,
            review_queue_entry_id=packet.review_queue_entry_id,
            packet_manifest_generation=packet.packet_manifest_generation,
            packet_manifest_digest=packet.packet_manifest_digest,
            created_at=packet.created_at,
            membership=ReviewPacketMembership(
                request=ReviewPacketMembershipRequest(
                    **{
                        key: UUID(str(getattr(packet, key)))
                        if key.endswith("_id")
                        else getattr(packet, key)
                        for key in ReviewPacketMembershipRequest.model_fields
                    }
                ),
                submission=ReviewSubmissionMember(
                    binding_id=UUID(packet.submission_binding_id),
                    logical_role=packet.submission_logical_role,
                    media_type=packet.submission_media_type,
                ),
                guide_documents=tuple(
                    ReviewGuideMember(
                        **{
                            key: UUID(str(getattr(member, key)))
                            if key.endswith("_id")
                            else getattr(member, key)
                            for key in ReviewGuideMember.model_fields
                        }
                    )
                    for member in members
                ),
            ),
        )
