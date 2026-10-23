"""Recorded external adapter composition only for the isolated drill worker."""

from app.workers import project_setup
from app.workers.celery_app import celery_app  # noqa: F401
from experiments.pilot04_external_checker_runtime.guide_runtime import create_recorded_runtime
from guide_compilation_e2e import scripted_guide_document_parser_factory

# Selected explicitly by the drill's celery -A, before prefork startup. Neither
# production app nor ordinary tests import this entry point. Inference and parser
# behavior are scripted; production ART reads and PROJECTS access receipts remain active.
project_setup.create_project_guide_runtime = create_recorded_runtime
project_setup.guide_document_parser_factory = scripted_guide_document_parser_factory
