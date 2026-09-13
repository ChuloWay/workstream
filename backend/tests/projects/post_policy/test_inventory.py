"""Only the explicit hidden post-policy owners enter the protected partition."""

import pytest
from scripts import behavior_ownership as ownership
from tests.test_behavior_ownership import _partition


def test_post_policy_partition_is_exact_and_additive():
    expected = {
        'backend/app/modules/authorization/api/post_policy.py',
        'backend/app/modules/projects/api/post_policy.py',
        *{f'backend/app/modules/projects/post_policy/{name}.py' for name in (
            'compiler', 'correction', 'custody', 'models', 'repository', 'service')},
    }
    assert ownership.POL_06A_PARTITION_TARGETS == expected
    retained = 'backend/app/core/config.py'
    before = _partition([retained])
    ownership._validate_additive_partition_transition(_partition(sorted({retained, *expected})), before)
    for invalid in (expected, {retained, *expected, 'backend/app/modules/projects/post_policy/extra.py'}):
        with pytest.raises(ownership.BehaviorOwnershipError, match='untrusted_partition_change'):
            ownership._validate_additive_partition_transition(_partition(sorted(invalid)), before)
