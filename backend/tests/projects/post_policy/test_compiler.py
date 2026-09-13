"""Real saved-result compiler and discriminating selection enforcement proof."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.interfaces.project_agents import ProjectGuideCompilationResult
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.post_policy.compiler import compile_saved_post_policy
from tests.projects.guide_compilation.helpers import result


def selected_result():
    body = result().model_dump(mode="json")
    body['requirements'] = [dict(requirement_id='criteria', statement='Task acceptance criteria are present',
                                 disposition='supported_post_submit', platform_coverage=None, evidence_refs=[])]
    body['post_submit_bindings'] = [dict(requirement_id='criteria', capability_id='check_acceptance_criteria_present',
                                        capability_version='v0.1', stage='post_submit', parameters=[])]
    return body


def compile_body(body, catalogue=None):
    return compile_saved_post_policy(project_id=uuid4(), guide_version='guide-one',
                                     result=ProjectGuideCompilationResult.model_validate(body),
                                     catalogue=catalogue or current_post_submit_catalogue())


def test_shared_requirements_compile_once_with_all_bindings_preserved():
    body = selected_result()
    body['requirements'].append(body['requirements'][0] | dict(requirement_id='criteria-two'))
    body['post_submit_bindings'].append(body['post_submit_bindings'][0] | dict(requirement_id='criteria-two'))
    compiled = compile_body(body)
    assert compiled.required_checkers == ['check_acceptance_criteria_present']
    assert len(compiled.entries) == 9
    assert len(body['post_submit_bindings']) == 2
    assert compiled.entries[-1].configuration.model_dump() == {}


@pytest.mark.parametrize('change', ['missing', 'unknown', 'stage', 'version', 'default', 'configuration', 'disposition', 'duplicate_requirement'])
def test_compiler_revalidates_each_malformed_binding(change):
    body = selected_result()
    assert len(compile_body(body).entries) == 9
    binding = body['post_submit_bindings'][0]
    if change == 'missing':
        body['post_submit_bindings'] = []
    elif change == 'unknown':
        binding['capability_id'] = 'unsupported'
    elif change == 'stage':
        binding['stage'] = 'pre_submit'
    elif change == 'version':
        binding['capability_version'] = 'wrong'
    elif change == 'default':
        binding['capability_id'] = 'check_submission_packet'
    elif change == 'configuration':
        binding['parameters'] = [dict(name='disable', value=True)]
    elif change == 'disposition':
        body['requirements'][0]['disposition'] = 'human_review'
    else:
        body['requirements'].append(deepcopy(body['requirements'][0]))
    with pytest.raises(ValueError):
        compile_body(body)


def test_compiler_rejects_a_real_compiler_that_omits_the_required_selection(monkeypatch):
    from app.modules.projects.post_policy import compiler
    from app.modules.projects.post_submit_policy import compile_project_post_submit_checker_spec

    def missing_selection(**kwargs):
        kwargs['spec'] = kwargs['spec'] | dict(required_checkers=[])
        return compile_project_post_submit_checker_spec(**kwargs)

    monkeypatch.setattr(compiler, 'compile_project_post_submit_checker_spec', missing_selection)
    with pytest.raises(ValueError, match='omits or changes a required binding'):
        compile_body(selected_result())


@pytest.mark.parametrize('index', [0, 8])
def test_disabled_default_or_selected_capability_is_unavailable(index):
    from tests.checkers.post_submit.support import altered_catalogue

    with pytest.raises(ValueError, match='unavailable'):
        compile_body(selected_result(), altered_catalogue(index=index, state='disabled'))


def test_blocked_result_never_yields_a_policy():
    body = selected_result()
    body['status'] = 'guide_blocked'
    body['submission_artifact_policy'] = None
    body['requirements'].append(dict(requirement_id='gap', statement='The guide lacks necessary task context',
                                     disposition='guide_blocker', platform_coverage=None, evidence_refs=[]))
    with pytest.raises(ValueError, match='blocked guide cannot project'):
        compile_body(body)
