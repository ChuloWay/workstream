"""Explicit composition and adversarial absence-of-live-reachability proof."""

from pathlib import Path

import pytest

from app.adapters.auth import setup_finalization_authorization
from app.modules.authorization.project_setup_finalization import SetupFinalizationAuthorization
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from tests.projects.guide_compilation.finalization.support import scenario
from tests.projects.guide_compilation.finalization.test_structure import imports_and_calls

ROOT = Path(__file__).resolve().parents[3]


def assert_no_live_finalization(paths):
    imports, calls = imports_and_calls(paths)
    assert not any("finalization" in name.lower() for name in imports | calls)


async def test_finalization_authority_has_no_live_reachability():
    paths = tuple((ROOT / "app/modules").rglob("router.py")) + tuple(
        (ROOT / "app/workers").rglob("*.py")
    )
    assert paths
    assert_no_live_finalization(paths)
    case = scenario()
    adapter = setup_finalization_authorization(case.session)
    assert type(adapter) is SetupFinalizationAuthorization
    assert adapter._session is case.session
    service = GuideCompilationFinalizationService(case.session)
    service._repository = case.repo
    with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
        await service.finalize(case.command)
    assert case.repo.calls == ["lookup"]


@pytest.mark.parametrize(
    "source",
    [
        "from app.adapters.auth import setup_finalization_authorization as ordinary\nordinary(session)\n",
        "authority.prepare_setup_finalization(locator)\n",
    ],
)
def test_reachability_proof_rejects_injected_factory_or_call(tmp_path, source):
    path = tmp_path / "worker.py"
    path.write_text(source)
    with pytest.raises(AssertionError):
        assert_no_live_finalization((path,))


def test_authorization_owner_has_no_product_storage_or_provider_imports():
    paths = (
        ROOT / "app/modules/authorization/project_setup_finalization.py",
        ROOT / "app/modules/authorization/domain/project_setup_finalization.py",
    )
    imports, calls = imports_and_calls(paths)
    assert not any(
        name.startswith(
            (
                "app.modules.projects",
                "app.adapters.project_agents",
                "openai",
                "agents",
                "app.workers",
            )
        )
        for name in imports
    )
    assert calls.isdisjoint(
        {
            "commit",
            "begin",
            "compile_project_guide",
            "project_guide_sufficiency",
            "project_submission_artifact_policy",
        }
    )
