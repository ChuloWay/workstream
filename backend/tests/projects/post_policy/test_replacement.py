"""A corrected unified generation replaces one policy chain without rewriting evidence."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_proposals import GuideProposalApproval, GuideProposalSelection
from app.modules.projects.api.post_policy import PostPolicyApproval, PostPolicyCorrection, PostPolicyDerive
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import proposal_case, read_package, finalize_corrected_attempt
from tests.projects.guide_compilation.proposals.test_postgresql import approve
from .pg_support import prepare_post_policy, operate


@pytest.mark.parametrize('origin', ['post_policy', 'unified'])
async def test_corrected_generation_replaces_policy_and_retains_original_receipts(clean_postgres_database, origin):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        setup = service_actor(values)
        derive, first = await prepare_post_policy(factory, command, actor, grant, setup)
        approval = PostPolicyApproval(target=first.target, idempotency_key=uuid4())
        approved = await operate(factory, actor, command.project_id, grant, 'approve', approval)
        if origin == 'post_policy':
            correction = await operate(factory, actor, command.project_id, grant, 'request_correction',
                PostPolicyCorrection(target=first.target, idempotency_key=uuid4(), reason='Reconsider these evaluation requirements'))
            successor = correction.correction
        else:
            from app.modules.projects.api.guide_proposals import GuideProposalCorrection
            from tests.projects.guide_compilation.proposals.test_postgresql import correct
            successor = await correct(factory, command, actor, grant, GuideProposalCorrection(
                target=first.target.proposal, idempotency_key=uuid4(), reason='Reconsider the complete guide proposal'))
        next_command = await finalize_corrected_attempt(factory, values, actor, successor)
        package = await read_package(factory, next_command, actor, grant)
        upstream = await approve(factory, next_command, actor, grant, GuideProposalApproval(
            target=package.target, idempotency_key=uuid4(),
            expected_previous_approval_operation_id=package.current_approval_operation_id,
            expected_previous_approval_output_digest=package.current_approval_output_digest))
        next_derive = PostPolicyDerive(selection=GuideProposalSelection(
            project_id=command.project_id, guide_id=command.guide_id, compilation_id=next_command.compilation_id),
            upstream_approval_operation_id=upstream.operation_id,
            upstream_approval_output_digest=canonical_json_hash(upstream.model_dump(mode='json')))
        second = await operate(factory, setup, command.project_id, None, 'derive', next_derive)
        assert second.target.predecessor_policy_id == first.target.policy_id
        assert second.target.policy_hash == first.target.policy_hash
        assert second.target.proposal.setup_generation == first.target.proposal.setup_generation + 1
        assert await operate(factory, setup, command.project_id, None, 'derive', derive) == first
        assert await operate(factory, actor, command.project_id, grant, 'approve', approval) == approved
        async with factory() as session:
            rows = (await session.execute(text(
                'SELECT id,lifecycle_status,approval_operation_id,supersession_operation_id FROM checker_policies ORDER BY lifecycle_status'
            ))).all()
            assert rows == [
                (str(second.target.policy_id), 'compiled', None, None),
                (str(first.target.policy_id), 'superseded', approved.operation_id,
                 correction.operation_id if origin == 'post_policy' else second.operation_id)]
        await operate(factory, actor, command.project_id, grant, 'request_correction',
            PostPolicyCorrection(target=second.target, idempotency_key=uuid4(), reason='Reconsider the next evaluation requirements'))
        # Both source rows are valid superseded history, so the earlier current-policy
        # uniqueness guard cannot mask the independent root/successor protections.
        # Direct SQL cannot fork either the root or a successor, independent of application locks.
        for policy, constraint in ((first, 'uq_post_policy_chain_root'), (second, 'uq_post_policy_chain_successor')):
            with pytest.raises(DBAPIError, match=constraint):
                async with factory() as session, session.begin():
                    await session.execute(text(
                        "INSERT INTO checker_policies SELECT (jsonb_populate_record(NULL::checker_policies, "
                        "to_jsonb(source)||jsonb_build_object('id',cast(:id as text)))).* "
                        "FROM checker_policies source WHERE id=:source"),
                        dict(id=str(uuid4()), source=str(policy.target.policy_id)))
