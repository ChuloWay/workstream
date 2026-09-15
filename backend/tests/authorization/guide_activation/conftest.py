"""Activation cannot call inference, document access or runtime evaluators."""

from tests.authorization.post_policy.pg_support import forbid_runtime_calls as forbid_runtime_calls
