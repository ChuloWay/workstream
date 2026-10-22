"""Shape guards of the compensation-unit audit vocabulary migration."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[2] / "alembic/versions/0058_compensation_unit_create.py"


def _migration():
    spec = importlib.util.spec_from_file_location("migration_0058", _PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Op:
    def __init__(self, definition: str) -> None:
        self.definition, self.statements = definition, []

    def execute(self, statement) -> None:
        self.statements.append(str(statement))

    def get_bind(self):
        definition = self.definition

        class _Result:
            def scalar_one(self) -> str:
                return definition

        class _Bind:
            def execute(self, *args, **kwargs):
                return _Result()

        return _Bind()


def _definition(module, copies: int = 2, extra: str = "") -> str:
    return "CHECK (" + " OR ".join([module._ANCHOR] * copies) + extra + ")"


def test_upgrade_adds_the_action_pair_after_both_anchors_then_the_event_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _migration()
    op = _Op(_definition(module))
    monkeypatch.setattr(module, "op", op)

    module.upgrade()

    added = next(s for s in op.statements if "ADD CONSTRAINT" in s)
    assert added.count("'contribution.compensation_unit.create'::text") == 2
    assert added.count("'compensation.policy.manage'::text") == 4
    assert any("CREATE TABLE public.project_compensation_unit_creation_events" in s
               for s in op.statements)
    assert sum("CREATE TRIGGER" in s for s in op.statements) == 2


@pytest.mark.parametrize(
    "definition",
    [
        lambda m: _definition(m, copies=1),
        lambda m: _definition(m, extra=" OR 'contribution.compensation_unit.create'"),
    ],
)
def test_upgrade_refuses_an_unexpected_constraint_before_any_change(
    monkeypatch: pytest.MonkeyPatch, definition
) -> None:
    module = _migration()
    op = _Op(definition(module))
    monkeypatch.setattr(module, "op", op)

    with pytest.raises(RuntimeError, match="constraint shape changed"):
        module.upgrade()
    assert not any("DROP CONSTRAINT" in s for s in op.statements)


def test_downgrade_is_refused() -> None:
    with pytest.raises(RuntimeError, match="cannot be downgraded"):
        _migration().downgrade()
