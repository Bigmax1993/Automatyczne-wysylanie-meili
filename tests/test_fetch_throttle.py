"""Testy fetch_throttle (odstępy HTTP per host)."""

from __future__ import annotations

import pytest

import fetch_throttle as ft


def test_clear_host_throttle_clears_internal_map() -> None:
    ft.clear_host_throttle()
    ft.throttle_hostname_before_http("https://example.com/path")
    assert "example.com" in ft._host_last_monotonic
    ft.clear_host_throttle()
    assert len(ft._host_last_monotonic) == 0


def test_zero_interval_skips_sleep(monkeypatch) -> None:
    ft.clear_host_throttle()
    monkeypatch.setattr(ft, "WEB_FETCH_MIN_INTERVAL_PER_HOST_SEC", 0.0)
    slept: list[float] = []
    monkeypatch.setattr(ft.time, "sleep", lambda s: slept.append(s))
    ft.throttle_hostname_before_http("https://a.example.org/x")
    ft.throttle_hostname_before_http("https://a.example.org/y")
    assert slept == []


def test_empty_or_invalid_url_no_sleep(monkeypatch) -> None:
    ft.clear_host_throttle()
    monkeypatch.setattr(ft, "WEB_FETCH_MIN_INTERVAL_PER_HOST_SEC", 5.0)
    slept: list[float] = []
    monkeypatch.setattr(ft.time, "sleep", lambda s: slept.append(s))
    ft.throttle_hostname_before_http("")
    ft.throttle_hostname_before_http("ftp://")
    assert slept == []


def test_second_request_to_same_host_triggers_sleep(monkeypatch) -> None:
    ft.clear_host_throttle()
    monkeypatch.setattr(ft, "WEB_FETCH_MIN_INTERVAL_PER_HOST_SEC", 10.0)
    slept: list[float] = []
    monkeypatch.setattr(ft.time, "sleep", lambda s: slept.append(s))
    # now, end_first, now_second, end_second
    times = iter([0.0, 100.0, 105.0, 106.0])

    def fake_mono() -> float:
        return next(times)

    monkeypatch.setattr(ft.time, "monotonic", fake_mono)
    ft.throttle_hostname_before_http("https://slow.example.net/page")
    ft.throttle_hostname_before_http("https://slow.example.net/other")
    assert slept == [10.0, 5.0]
