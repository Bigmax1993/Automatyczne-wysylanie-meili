"""Testy morning_exercises_gui (funkcje bez pełnego Tk mainloop)."""

from __future__ import annotations

import pytest

from morning_exercises_tracker import ExerciseTracker


@pytest.fixture(scope="module")
def meg():
    try:
        import morning_exercises_gui as m
    except ModuleNotFoundError as exc:
        if exc.name == "tkinter":
            pytest.skip("tkinter nie jest dostępny w tym środowisku")
        raise
    return m


def test_app_builds_with_custom_tracker(tmp_path, meg) -> None:
    try:
        tracker = ExerciseTracker(state_path=tmp_path / "state.json")
        app = meg.MorningExercisesApp(tracker=tracker)
        assert app.title() == tracker.routine.title
        app.destroy()
    except Exception as exc:
        if "no display" in str(exc).lower() or "tcl" in str(exc).lower():
            pytest.skip(f"brak wyświetlacza: {exc}")
        raise
