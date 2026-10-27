"""Opt-in, controlled-provider nested Smol recovery proof on an owned node.

The operator must provide a fresh composition root and short child HOME root
for exactly one WORKSTREAM_TS_SMOL_RECOVERY_CASE. Never run beside another VM
qualification. This reuses the composition's real grants, ART and PostgreSQL.
"""
import os

from smol_recovery import NestedTrialRecovery
from terminal_systems_smol_composition import (
    test_production_service_executes_project_trial_under_smol_with_real_custody as run_composition,
)


async def test_active_nested_trial_recovery(
    tmp_path, isolated_database_env, admin_access, monkeypatch
):
    recovery = NestedTrialRecovery(os.environ["WORKSTREAM_TS_SMOL_RECOVERY_CASE"])
    await run_composition(
        tmp_path, isolated_database_env, admin_access, monkeypatch, recovery=recovery
    )
    assert recovery.completed is True
