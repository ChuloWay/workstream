"""Closed post-policy AUTH lineage replaces obsolete unfinished setup-step inputs."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.authorization.api.post_policy import ProjectPostSubmitCheckerPolicyMutationResourceContext

HASH = 'sha256:' + 'a' * 64


def resource():
    ids = {key: uuid4() for key in (
        'resource_id', 'scope_project_id', 'guide_id', 'source_snapshot_id', 'setup_run_id',
        'compilation_id', 'finalization_id', 'upstream_approval_operation_id', 'effective_policy_id',
        'pre_submit_policy_id', 'projection_operation_id', 'operation_id',
    )}
    hashes = {key: HASH for key in (
        'source_snapshot_hash', 'result_hash', 'post_component_hash', 'requirement_inventory_hash',
        'catalogue_manifest_hash', 'upstream_approval_output_digest', 'effective_policy_hash',
        'pre_submit_bundle_hash', 'request_digest', 'target_digest', 'policy_hash',
    )}
    return dict(**ids, **hashes, checker_policy_id=ids['resource_id'],
                resource_type='project_post_submit_checker_policy_mutation', guide_version='guide-one',
                setup_generation=1, target_kind='derive', execution_kind='setup_service', lifecycle_status='compiled')


@pytest.mark.parametrize('field', ['finalization_id', 'upstream_approval_operation_id', 'upstream_approval_output_digest',
                                   'policy_hash', 'post_component_hash', 'requirement_inventory_hash', 'setup_run_id'])
def test_post_policy_resource_requires_each_independent_commitment(field):
    value = resource()
    ProjectPostSubmitCheckerPolicyMutationResourceContext(**value)
    del value[field]
    with pytest.raises(ValidationError, match='Field required'):
        ProjectPostSubmitCheckerPolicyMutationResourceContext(**value)


def test_post_policy_resource_rejects_old_step_and_crossed_actor_or_selector():
    value = resource()
    for change in (dict(setup_service_custody={}), dict(execution_kind='human'), dict(checker_policy_id=uuid4())):
        with pytest.raises(ValidationError):
            ProjectPostSubmitCheckerPolicyMutationResourceContext(**(value | change))
