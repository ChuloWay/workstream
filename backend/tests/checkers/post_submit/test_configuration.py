"""No arbitrary post-submit configuration or implicit version selection."""

import pytest
from pydantic import ValidationError

from tests.checkers.post_submit.support import altered_catalogue, catalogue


def test_binding_uses_registered_configuration():
    definition = catalogue().definition("check_acceptance_criteria_present", "v0.1")
    assert definition.validate_configuration({}).model_dump() == {}
    with pytest.raises(ValidationError, match="Extra inputs"):
        definition.validate_configuration({"script": "arbitrary"})
    with pytest.raises(ValueError, match="unavailable"):
        altered_catalogue(state="disabled").definition(
            "check_acceptance_criteria_present", "v0.1"
        ).validate_configuration({})


@pytest.mark.parametrize(
    "name,version", [("unknown", "v0.1"), ("check_acceptance_criteria_present", "unsupported")]
)
def test_missing_exact_definition_does_not_select_latest(name, version):
    with pytest.raises(ValueError, match="capability or version is unavailable"):
        catalogue().definition(name, version)
