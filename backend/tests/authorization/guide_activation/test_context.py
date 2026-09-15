"""Complete immutable owner facts and exact AUTH digest parity."""

from uuid import uuid4

import pytest

from app.modules.authorization.catalogue import ACTION_BY_ID, SERVICE_ACTIONS_BY_IDENTITY, ActionId, ActionAvailability
from app.modules.authorization.domain.guide_activation import activation_resource, ProjectGuideActivationResourceContext
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.projects.api.guide_activation import GuideActivationFacts
from .support import activation_facts


def test_exact_action_and_digest_parity():
    facts = activation_facts()
    resource = activation_resource(facts)
    assert authorization_resource_digest(resource) == facts.digest
    assert ACTION_BY_ID[ActionId.PROJECT_GUIDE_ACTIVATE].availability is ActionAvailability.ACTIVE
    assert all(ActionId.PROJECT_GUIDE_ACTIVATE not in actions for actions in SERVICE_ACTIONS_BY_IDENTITY.values())
    refreshed = facts.model_copy(update={"locator": facts.locator.model_copy(update={"request_id": uuid4()})})
    assert authorization_resource_digest(activation_resource(refreshed)) == facts.digest


@pytest.mark.parametrize("field", ["resource_type", "resource_id", "scope_project_id"])
def test_resource_substitution_rejects(field):
    resource = activation_resource(activation_facts())
    values = resource.model_dump()
    values[field] = "foreign" if field == "resource_type" else uuid4()
    with pytest.raises(ValueError):
        ProjectGuideActivationResourceContext(**values)


@pytest.mark.parametrize("field", ["project_id", "guide_id", "operation_id"])
def test_locator_must_match_receipt(field):
    facts = activation_facts()
    facts = facts.model_copy(update={"locator": facts.locator.model_copy(update={field: uuid4()})})
    with pytest.raises(ValueError, match="identity mismatch"):
        activation_resource(facts)


@pytest.mark.parametrize("field", list(GuideActivationFacts.model_fields))
def test_required_facts_cannot_be_omitted(field):
    facts = activation_facts().model_dump()
    del facts[field]
    with pytest.raises(ValueError):
        GuideActivationFacts.model_validate(facts)


@pytest.mark.parametrize("path,value", [
    (("receipt", "command", "target", "proposal", "setup_generation"), 0),
    (("receipt", "command", "target", "proposal", "component_hashes", "pre_submit_hash"), "bad"),
    (("receipt", "command", "review", "generation"), True),
    (("receipt", "command", "target", "upstream", "target_digest"), "sha256:" + "b" * 64),
    (("receipt", "contribution", "contribution_policy_version_id"), uuid4()),
])
def test_nested_unvalidated_instances_reject(path, value):
    facts = activation_facts()

    def tamper(model, fields):
        return model.model_copy(update={fields[0]: value if len(fields) == 1 else tamper(getattr(model, fields[0]), fields[1:])})

    with pytest.raises(ValueError):
        activation_resource(tamper(facts, path))


def test_constructed_wrapper_cannot_bypass_digest_validation():
    resource = activation_resource(activation_facts()).model_copy(update={"resource_id": uuid4()})
    with pytest.raises(ValueError, match="identity mismatch"):
        authorization_resource_digest(resource)


def test_lookalike_contracts_cannot_supply_facts_or_locator():
    from types import SimpleNamespace
    from app.modules.authorization.domain.guide_activation import activation_selectors

    facts = activation_facts()
    with pytest.raises(ValueError, match="invalid activation facts"):
        activation_resource(SimpleNamespace(**facts.model_dump()))
    with pytest.raises(ValueError, match="invalid activation locator"):
        activation_selectors(SimpleNamespace(**facts.locator.model_dump()))
    resource = activation_resource(facts).model_copy(update={"facts": None})
    with pytest.raises(ValueError, match="invalid activation facts"):
        authorization_resource_digest(resource)
