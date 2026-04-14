from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_FILE = PROJECT_ROOT / ".github" / "workflows" / "main.yml"


def _workflow_text() -> str:
    return WORKFLOW_FILE.read_text(encoding="utf-8")


def test_workflow_pipeline_manual_runs_do_not_depend_on_run_pipeline_input() -> None:
    raw = _workflow_text()
    assert "github.event_name == 'workflow_dispatch'" in raw
    assert "github.event.inputs.run_pipeline == 'true'" not in raw


def test_workflow_pipeline_uses_always_to_handle_skipped_serpapi_job() -> None:
    raw = _workflow_text()
    assert "pipeline:" in raw
    assert "always() &&" in raw
    assert "needs.serpapi-sunday.result == 'success' || needs.serpapi-sunday.result == 'skipped'" in raw


def test_workflow_serpapi_job_respects_skip_build_input() -> None:
    raw = _workflow_text()
    assert "github.event.inputs.skip_build == 'false'" in raw
    assert "serpapi-sunday:" in raw
