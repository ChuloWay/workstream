"""Behavioral checks for the shared record-ID generator, not timing benchmarks."""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing
from uuid import RFC_4122, UUID

import uuid6

from app.core.identifiers import new_record_id


def _batch(count: int) -> list[str]:
    return [str(new_record_id()) for _ in range(count)]


def test_record_identity_is_standard_uuid7_and_round_trips():
    value = new_record_id()
    assert type(value) is UUID
    assert value.version == 7
    assert value.variant == RFC_4122
    assert UUID(str(value)) == value
    assert UUID(bytes=value.bytes) == value


def test_frozen_and_regressing_clock_keeps_sequential_ids_distinct(monkeypatch):
    monkeypatch.setattr(uuid6, "_last_v7_timestamp", None)
    monkeypatch.setattr(uuid6.time, "time_ns", lambda: 1_700_000_000_000_000_000)
    first, second = new_record_id(), new_record_id()
    monkeypatch.setattr(uuid6.time, "time_ns", lambda: 1_600_000_000_000_000_000)
    third = new_record_id()
    assert first.int < second.int < third.int
    assert all(value.version == 7 for value in (first, second, third))


def test_threaded_generation_has_distinct_v7_values():
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = [value for batch in pool.map(_batch, [128] * 4) for value in batch]
    assert len(set(values)) == 512
    assert all(UUID(value).version == 7 for value in values)


def test_forked_generation_does_not_reuse_parent_id_stream():
    # Warm the generator before fork, as a prefork worker parent would.
    parent = new_record_id()
    with ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        values = [value for batch in pool.map(_batch, [128] * 2) for value in batch]
    assert len(set(values)) == 256
    assert str(parent) not in values
    assert all(UUID(value).version == 7 for value in values)
