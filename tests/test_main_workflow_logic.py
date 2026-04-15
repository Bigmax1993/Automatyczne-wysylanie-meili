from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "main.yml"


def _workflow_text() -> str:
    return WORKFLOW_FILE.read_text(encoding="utf-8")


def test_workflow_pipeline_manual_runs_do_not_depend_on_run_pipeline_input() -> None:
    raw = _workflow_text()
    assert "github.event_name == 'workflow_dispatch'" in raw
    assert "github.event.inputs.run_pipeline == 'true'" in raw


def test_workflow_pipeline_manual_runs_require_explicit_run_pipeline_switch() -> None:
    raw = _workflow_text()
    assert "pipeline:" in raw
    assert "(github.event_name == 'workflow_dispatch' && github.event.inputs.run_pipeline == 'true')" in raw
    assert "always() &&" not in raw
    assert "needs: [test-python, test-powershell]" in raw


def test_workflow_serpapi_job_runs_only_on_sunday_schedule() -> None:
    raw = _workflow_text()
    assert "serpapi-sunday:" in raw
    assert "github.event_name == 'schedule' && github.event.schedule == '0 19 * * 0'" in raw
    assert "github.event.inputs.skip_build == 'false'" not in raw
