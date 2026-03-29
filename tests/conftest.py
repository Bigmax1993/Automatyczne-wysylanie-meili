"""
Wspólne fixture pytest — m.in. stabilne logowanie między testami.

Testy modułów: patrz tests/test_*.py, e2e/, integration/, regression/.
Skrypty PowerShell: tests/test_run_pipeline_ps1.py, tests/test_run_with_env_ps1.py;
subprocess env: tests/test_contact_mailer_env_subprocess.py; Pester: tests/powershell/*.Tests.ps1.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _rehydrate_root_logging_after_test() -> None:
    """
    Po każdym teście resetuje konfigurację logging (root) i ponownie wywołuje setup,
    żeby moduły importujące contact_mailer / SerpAPI nie zostawiały pustego roota.
    """
    yield
    import pipeline_logging as pl

    pl.reset_logging_state_for_tests()
    pl.setup_logging("pytest")
