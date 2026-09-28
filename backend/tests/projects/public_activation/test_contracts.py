"""Admission and response values protect the public activation boundary."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.deps.auth import get_auth_verification_result
from app.api.deps.api_controls import enforce_authorization_read_rate_limit
from app.api.deps.authorization import get_authorization_actor
from app.api.deps.guide_proposal_http import proposal_http_error
from app.db.session import get_db_session
from app.main import create_app
from app.modules.authorization.api import AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid
from app.modules.projects.api.guide_activation import GuideActivationInput
from app.modules.projects.api.guide_activation_context import GuideActivationContext
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService


@pytest.mark.parametrize('keys', [[], [('Idempotency-Key','invalid')], [('Idempotency-Key',str(uuid4())),('idempotency-key',str(uuid4()))]])
async def test_header_rejection_before_identity_and_product_sql(keys):
    app = create_app()
    app.dependency_overrides[get_auth_verification_result] = lambda: SimpleNamespace(token=SimpleNamespace(subject_kind='human'))
    app.dependency_overrides[enforce_authorization_read_rate_limit] = lambda: None
    def forbidden():
        pytest.fail('invalid key reached actor or product database')
    app.dependency_overrides[get_authorization_actor] = forbidden
    app.dependency_overrides[get_db_session] = forbidden
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.post(f'/api/v1/projects/{uuid4()}/guides/{uuid4()}/activate', json={}, headers=keys)
    assert response.status_code == 422


def test_public_activation_exposes_only_client_selections():
    schema = create_app().openapi()
    operation = schema['paths']['/api/v1/projects/{project_id}/guides/{guide_id}/activate']['post']
    assert operation['x-workstream-action-id'] == 'project.guide.activate'
    assert any(p['name']=='Idempotency-Key' and p['required'] for p in operation['parameters'])
    assert not {'idempotency_key','actor_profile_id','authority','authorization_decision_event_id'} & GuideActivationInput.model_fields.keys()


@pytest.mark.parametrize('incomplete', [
    {'expected_previous_active_guide_id': str(uuid4())},
    {'expected_previous_active_guide_generation': 1},
    {'post_approval_operation_id': str(uuid4())},
    {'post_approval_output_digest': 'sha256:'+'a'*64},
])
def test_context_never_admits_half_a_selection(incomplete):
    baseline = dict(guide_mutation_generation=1,review=None,revision=None,contribution=None,
        expected_previous_active_guide_id=None,expected_previous_active_guide_generation=None,
        post_approval_operation_id=None,post_approval_output_digest=None)
    assert GuideActivationContext(**baseline)
    with pytest.raises(ValidationError):
        GuideActivationContext(**(baseline | incomplete))


@pytest.mark.parametrize('failure,status', [(AuthorizationDenied,404),(AuthorizationUnavailable,503),(PreparedAuthorizationInvalid,503)])
async def test_shared_authority_error_boundary_preserves_retryability(failure,status):
    with pytest.raises(GuideProposalError) as result:
        async with GuideProposalService._bounded_errors():
            raise failure('private internals')
    error = proposal_http_error(result.value)
    assert error.status_code == status
    assert 'private internals' not in str(error.detail)
