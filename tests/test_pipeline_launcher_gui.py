"""
Testy modułu pipeline_launcher_gui: funkcje czyste oraz powiązanie GUI → subprocess.

Część testów Tk wymaga wyświetlacza; na CI bez X11 mogą być pomijane (TclError).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def plg():
    """Import modułu GUI (ładuje tkinter)."""
    import pipeline_launcher_gui as m

    return m


# --- read_version ---


def test_read_version_from_file(tmp_path: Path) -> None:
    import pipeline_launcher_gui as plg

    p = tmp_path / "VERSION"
    p.write_text("  2.3.4\n", encoding="utf-8")
    assert plg.read_version(p) == "2.3.4"


def test_read_version_empty_file_returns_question_mark(tmp_path: Path) -> None:
    import pipeline_launcher_gui as plg

    p = tmp_path / "VERSION"
    p.write_text("   \n", encoding="utf-8")
    assert plg.read_version(p) == "?"


def test_read_version_missing_file(tmp_path: Path) -> None:
    import pipeline_launcher_gui as plg

    assert plg.read_version(tmp_path / "nie_ma") == "?"


# --- env_status_line ---


def test_env_status_line_missing(plg) -> None:
    env = {}
    assert plg.env_status_line("OPENAI_API_KEY", env) == "OPENAI_API_KEY: (brak w tej sesji)"


def test_env_status_line_whitespace_only(plg) -> None:
    env = {"OPENAI_API_KEY": "  \t  "}
    assert plg.env_status_line("OPENAI_API_KEY", env) == "OPENAI_API_KEY: (brak w tej sesji)"


def test_env_status_line_set(plg) -> None:
    env = {"OPENAI_API_KEY": "sk-test-12345"}
    assert plg.env_status_line("OPENAI_API_KEY", env) == "OPENAI_API_KEY: ustawiony, 13 znaków"


def test_env_status_line_uses_os_environ_when_none(plg, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "x")
    assert "ustawiony" in plg.env_status_line("GMAIL_APP_PASSWORD")


# --- build_powershell_run_with_env_args ---


def test_build_powershell_minimal(plg, tmp_path: Path) -> None:
    script = tmp_path / "run_with_env.ps1"
    script.write_text("#", encoding="utf-8")
    args = plg.build_powershell_run_with_env_args(script)
    assert args[:5] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    assert args[5] == str(script.resolve())
    assert len(args) == 6


@pytest.mark.parametrize(
    "check_only,skip_build,dry_run,expected_tail",
    [
        (True, False, False, ["-CheckOnly"]),
        (False, True, False, ["-SkipBuild"]),
        (False, False, True, ["-DryRun"]),
        (False, True, True, ["-SkipBuild", "-DryRun"]),
        (True, True, True, ["-CheckOnly", "-SkipBuild", "-DryRun"]),
    ],
)
def test_build_powershell_switches(
    plg,
    tmp_path: Path,
    check_only: bool,
    skip_build: bool,
    dry_run: bool,
    expected_tail: list[str],
) -> None:
    script = tmp_path / "x.ps1"
    script.touch()
    args = plg.build_powershell_run_with_env_args(
        script,
        check_only=check_only,
        skip_build=skip_build,
        dry_run=dry_run,
    )
    assert args[6:] == expected_tail


# --- format_run_start_banner ---


def test_format_run_start_banner(plg) -> None:
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", r"C:\p\run.ps1", "-SkipBuild"]
    assert plg.format_run_start_banner(args) == "-SkipBuild"


def test_format_run_start_banner_empty_tail(plg) -> None:
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", r"C:\p\run.ps1"]
    assert plg.format_run_start_banner(args) == ""


# --- Ścieżki projektu (kontrakt z run_with_env.ps1) ---


def test_project_paths_point_inside_repo(plg) -> None:
    assert plg.PROJECT_DIR.resolve() == PROJECT_ROOT.resolve()
    assert plg.RUN_WITH_ENV == plg.PROJECT_DIR / "run_with_env.ps1"
    assert plg.LOCAL_ENV == plg.PROJECT_DIR / "local_env.ps1"
    assert plg.VERSION_FILE == plg.PROJECT_DIR / "VERSION"


def test_run_with_env_script_exists_in_repo(plg) -> None:
    assert plg.RUN_WITH_ENV.is_file(), "Brak run_with_env.ps1 — GUI nie wystartuje pipeline"


def test_run_with_env_ps1_declares_same_switches_as_gui(plg) -> None:
    """Kontrakt: nazwy przełączników PowerShell zgadzają się z tym, co wysyła GUI."""
    text = plg.RUN_WITH_ENV.read_text(encoding="utf-8", errors="replace")
    assert "[switch]$CheckOnly" in text
    assert "[switch]$SkipBuild" in text
    assert "[switch]$DryRun" in text


# --- Integracja: _start_run → subprocess.Popen (mock) ---


def _tk_skip_if_no_display() -> None:
    pytest.importorskip("tkinter")
    import tkinter as tk

    try:
        r = tk.Tk()
        r.withdraw()
        r.destroy()
    except tk.TclError:
        pytest.skip("Brak wyświetlacza / Tk")


def _pipeline_app_or_skip(plg):
    """Tworzy okno GUI; przy TclError (np. drugi test w tej samej sesji / uszkodzone tk) — skip."""
    import tkinter as tk

    try:
        return plg.PipelineLauncherApp()
    except tk.TclError as e:
        pytest.skip(f"Tk / TclError: {e}")


@pytest.mark.skipif(sys.platform != "win32", reason="Tworzenie okna Tk + mock Popen — środowisko Windows")
def test_gui_start_run_invokes_popen_with_skipbuild(plg, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _tk_skip_if_no_display()

    rw = tmp_path / "run_with_env.ps1"
    le = tmp_path / "local_env.ps1"
    rw.write_text("# mock", encoding="utf-8")
    le.write_text("$x=1", encoding="utf-8")

    monkeypatch.setattr(plg, "RUN_WITH_ENV", rw)
    monkeypatch.setattr(plg, "LOCAL_ENV", le)
    monkeypatch.setattr(plg, "PROJECT_DIR", tmp_path)

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.wait.return_value = 0

    class _EmptyStdout:
        def __iter__(self):
            return iter(())

        def close(self) -> None:
            pass

    mock_proc.stdout = _EmptyStdout()

    mock_popen = MagicMock(return_value=mock_proc)

    with patch.object(plg.subprocess, "Popen", mock_popen):
        with patch.object(plg.messagebox, "showinfo"):
            with patch.object(plg.messagebox, "showerror", side_effect=AssertionError("showerror nie powinno być wywołane")):
                app = _pipeline_app_or_skip(plg)
                app.withdraw()
                try:
                    app._start_run(skip_build=True)
                    time.sleep(0.35)
                finally:
                    app.destroy()

    mock_popen.assert_called_once()
    cargs, ckwargs = mock_popen.call_args
    assert ckwargs.get("cwd") == str(tmp_path)
    popen_args = cargs[0]
    expected = plg.build_powershell_run_with_env_args(rw, skip_build=True)
    assert popen_args == expected


@pytest.mark.skipif(sys.platform != "win32", reason="Tk + messagebox — Windows")
def test_gui_start_run_blocked_when_local_env_missing(plg, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _tk_skip_if_no_display()

    rw = tmp_path / "run_with_env.ps1"
    rw.write_text("#", encoding="utf-8")
    monkeypatch.setattr(plg, "RUN_WITH_ENV", rw)
    monkeypatch.setattr(plg, "LOCAL_ENV", tmp_path / "brak_local_env.ps1")
    monkeypatch.setattr(plg, "PROJECT_DIR", tmp_path)

    errors: list[tuple[str, str]] = []

    def capture_error(title: str, msg: str) -> None:
        errors.append((title, msg))

    mock_popen = MagicMock()
    with patch.object(plg.subprocess, "Popen", mock_popen):
        with patch.object(plg.messagebox, "showerror", side_effect=capture_error):
            app = _pipeline_app_or_skip(plg)
            app.withdraw()
            try:
                app._start_run()
            finally:
                app.destroy()

    mock_popen.assert_not_called()
    assert errors
    assert "local_env" in errors[0][1].lower() or "local_env" in errors[0][0].lower()
