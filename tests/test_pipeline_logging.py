"""Testy modułu pipeline_logging (konfiguracja stdlib logging)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import pipeline_logging as pl


def test_reset_logging_state_clears_handlers() -> None:
    pl.reset_logging_state_for_tests()
    pl.setup_logging("t_reset")
    root = logging.getLogger()
    assert len(root.handlers) >= 1
    pl.reset_logging_state_for_tests()
    assert root.handlers == []


def test_setup_logging_second_call_is_idempotent(capsys) -> None:
    pl.reset_logging_state_for_tests()
    pl.setup_logging("first")
    n = len(logging.getLogger().handlers)
    pl.setup_logging("second")
    assert len(logging.getLogger().handlers) == n
    logging.getLogger("probe").info("idempotent_ok")
    assert "idempotent_ok" in capsys.readouterr().out


def test_setup_logging_respects_pipeline_log_level(monkeypatch, capsys) -> None:
    pl.reset_logging_state_for_tests()
    monkeypatch.setenv("PIPELINE_LOG_LEVEL", "WARNING")
    pl.setup_logging("lvl")
    logging.getLogger("x").info("ukryte")
    logging.getLogger("x").warning("widoczne")
    out = capsys.readouterr().out
    assert "ukryte" not in out
    assert "widoczne" in out


def test_setup_logging_file_handler_when_enabled(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "sub" / "app.log"
    pl.reset_logging_state_for_tests()
    monkeypatch.setenv("PIPELINE_LOG_TO_FILE", "1")
    monkeypatch.setenv("PIPELINE_LOG_FILE", str(log_path))
    monkeypatch.setenv("PIPELINE_LOG_LEVEL", "INFO")
    pl.setup_logging("filetest")
    logging.getLogger("fileprobe").info("zapis_do_pliku")
    for h in logging.getLogger().handlers:
        try:
            h.flush()
        except Exception:
            pass
    assert log_path.is_file()
    text = log_path.read_text(encoding="utf-8")
    assert "zapis_do_pliku" in text


def test_stdout_proxy_forwards_to_sys_stdout(capsys) -> None:
    pl.reset_logging_state_for_tests()
    pl.setup_logging("proxy")
    logging.getLogger("stdout_probe").warning("proxy_line")
    assert "proxy_line" in capsys.readouterr().out


def test_stdout_proxy_supports_isatty() -> None:
    proxy = pl._StdoutProxy()
    assert hasattr(proxy, "isatty")
    assert isinstance(proxy.isatty(), bool)
