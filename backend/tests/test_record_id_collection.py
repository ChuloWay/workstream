"""Collection identities stay stable without replacing runtime UUID generation."""

import sys
from types import ModuleType, SimpleNamespace
from uuid import RFC_4122

import pytest

from app.core import identifiers
from scripts import run_test_lanes as runner
from scripts import validate_test_lane_evidence as validator


@pytest.mark.parametrize("collector", [runner, validator])
def test_record_collection_stability_subset_and_runtime_restoration(monkeypatch, tmp_path, collector):
    root = runner.ROOT
    original = identifiers.new_record_id
    monkeypatch.setenv(runner.HEAD_ENV, "e" * 40)
    monkeypatch.setenv(validator.VALIDATOR_HEAD_ENV, "e" * 40)
    monkeypatch.setenv(validator.VALIDATOR_ROOT_ENV, str(root))
    monkeypatch.delenv(runner.COLLECTED_ENV, raising=False)
    monkeypatch.delenv(validator.VALIDATOR_COLLECTION_ENV, raising=False)

    def collect(names):
        modules = []
        collector.pytest_sessionstart(object())
        try:
            values = {}
            for name in names:
                module = ModuleType(f"tests.record_collection_{name}")
                module.__file__ = str(root / "tests" / f"record_collection_{name}.py")
                monkeypatch.setitem(sys.modules, module.__name__, module)
                modules.append(module)
                exec(compile(
                    "from app.core.identifiers import new_record_id\n"
                    "VALUES = [new_record_id(), new_record_id()]\n",
                    module.__file__, "exec",
                ), module.__dict__)
                values[name] = module.VALUES
            collector.pytest_collection_finish(SimpleNamespace(items=[]))
            assert identifiers.new_record_id is original
            for module in modules:
                assert module.new_record_id is original
                assert module.new_record_id() != module.new_record_id()
            return values
        finally:
            collector.pytest_sessionfinish(object(), 0)

    whole = collect(("first", "second"))
    assert whole == collect(("first", "second"))
    assert whole["second"] == collect(("second",))["second"]
    assert len(set(whole["first"] + whole["second"])) == 4
    assert all(value.version == 7 and value.variant == RFC_4122 for values in whole.values() for value in values)


@pytest.mark.parametrize("collector", [runner, validator])
def test_record_generator_restored_if_collection_fails(monkeypatch, collector):
    original = identifiers.new_record_id
    monkeypatch.setenv(runner.HEAD_ENV, "a" * 40)
    monkeypatch.setenv(validator.VALIDATOR_HEAD_ENV, "a" * 40)
    monkeypatch.setenv(validator.VALIDATOR_ROOT_ENV, str(runner.ROOT))
    collector.pytest_sessionstart(object())
    assert identifiers.new_record_id is not original
    collector.pytest_sessionfinish(object(), 2)
    assert identifiers.new_record_id is original
