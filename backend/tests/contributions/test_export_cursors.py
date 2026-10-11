"""Continuation cannot expand actor/query scope or outlive one export."""

import base64
from datetime import UTC, datetime, timedelta
import json

import pytest

from app.core.identifiers import new_record_id
from app.modules.contributions.api.records import ContributionReadRequest
from app.modules.contributions.records.cursors import (
    ContributionCursor, ContributionCursorCodec, InvalidContributionCursor, contribution_query_digest,
)

NOW = datetime(2026, 10, 11, 16, tzinfo=UTC)
SECRET = b"a" * 32


def selected():
    return ContributionReadRequest(audience="self", actor_profile_id=new_record_id())


def state():
    return ContributionCursor(new_record_id(), NOW, NOW + timedelta(minutes=15),
                              NOW - timedelta(days=1), new_record_id())


def test_cursor_roundtrip_retains_exact_membership_position_and_scope():
    codec, request, position = ContributionCursorCodec(SECRET), selected(), state()
    digest = contribution_query_digest(request)
    token = codec.encode(position, query_digest=digest)
    assert len(token) < 4096
    assert codec.decode(token, query_digest=digest, now=NOW) == position
    assert contribution_query_digest(request.model_copy(update={"cursor": token})) == digest


@pytest.mark.parametrize("field,value", [
    ("actor_profile_id", new_record_id()), ("audience", "project"),
    ("project_id", new_record_id()), ("output_format", "csv"), ("page_size", 1),
    ("contribution_type", "completed_review"), ("recorded_from", NOW),
    ("recorded_before", NOW),
])
def test_cursor_cannot_cross_actor_audience_filters_or_output(field, value):
    codec, request = ContributionCursorCodec(SECRET), selected()
    token = codec.encode(state(), query_digest=contribution_query_digest(request))
    other = request.model_copy(update={field: value})
    with pytest.raises(InvalidContributionCursor):
        codec.decode(token, query_digest=contribution_query_digest(other), now=NOW)


@pytest.mark.parametrize("elapsed", [-1, 900, 901])
def test_cursor_rejects_future_origin_or_expiry(elapsed):
    codec, request = ContributionCursorCodec(SECRET), selected()
    digest = contribution_query_digest(request)
    token = codec.encode(state(), query_digest=digest)
    with pytest.raises(InvalidContributionCursor):
        codec.decode(token, query_digest=digest, now=NOW + timedelta(seconds=elapsed))


@pytest.mark.parametrize("mutation", ["payload", "signature", "duplicate", "extra", "boolean_version"])
def test_forged_envelopes_are_refused_without_echoing_input(mutation):
    codec, request = ContributionCursorCodec(SECRET), selected()
    digest = contribution_query_digest(request)
    token = codec.encode(state(), query_digest=digest)
    envelope = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    if mutation == "payload":
        envelope["p"]["export"] = str(new_record_id())
    elif mutation == "signature":
        envelope["s"] = "A" * 43
    elif mutation == "extra":
        envelope["extra"] = True
    elif mutation == "boolean_version":
        envelope["p"]["v"] = True
    raw = json.dumps(envelope)
    if mutation == "duplicate":
        raw = raw.replace('"v": 1', '"v": 1, "v": 1')
    forged = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    with pytest.raises(InvalidContributionCursor) as error:
        codec.decode(forged, query_digest=digest, now=NOW)
    assert str(error.value) == "Invalid contribution export cursor"


@pytest.mark.parametrize("value", ["", "x" * 4097, "abc=", "abc.def", "abc\n", "💰", "a"])
def test_malformed_or_unbounded_cursor_is_refused(value):
    with pytest.raises(InvalidContributionCursor):
        ContributionCursorCodec(SECRET).decode(value, query_digest="irrelevant", now=NOW)


def test_signing_key_rotation_refuses_old_cursor():
    request = selected()
    digest = contribution_query_digest(request)
    token = ContributionCursorCodec(SECRET).encode(state(), query_digest=digest)
    with pytest.raises(InvalidContributionCursor):
        ContributionCursorCodec(b"b" * 32).decode(token, query_digest=digest, now=NOW)
