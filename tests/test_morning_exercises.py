"""Testy modułu morning_exercises (rutina ćwiczeń z notatek)."""

from __future__ import annotations

import json
import pytest

from morning_exercises import (
    default_morning_routine,
    exercise_from_dict,
    format_routine_for_display,
    MorningExerciseRoutine,
    routine_from_dict,
    routine_from_json,
    ScheduleFrequency,
)


def test_default_routine_matches_handwritten_notes() -> None:
    routine = default_morning_routine()
    assert routine.title == "Rano - ćwiczenia"
    assert len(routine.exercises) == 3

    ex1 = routine.exercise_by_number(1)
    assert "brzuchu" in ex1.instructions
    assert "dużymi palcami" in ex1.instructions
    assert ex1.frequency == ScheduleFrequency.MORNING
    assert ex1.daily_repetitions == 1

    ex2 = routine.exercise_by_number(2)
    assert "poduszka" in ex2.instructions
    assert ex2.frequency == ScheduleFrequency.MORNING_EVENING
    assert ex2.daily_repetitions == 2
    assert "Kolano nie ucieka na bok." in ex2.tips
    assert "Nie unosimy pośladków." in ex2.tips

    ex3 = routine.exercise_by_number(3)
    assert "ściany" in ex3.instructions
    assert "pośladki" in ex3.instructions
    assert ex3.frequency == ScheduleFrequency.THROUGHOUT_DAY
    assert ex3.daily_repetitions == 3


def test_total_daily_sessions() -> None:
    routine = default_morning_routine()
    assert routine.total_daily_sessions() == 6


def test_json_roundtrip() -> None:
    routine = default_morning_routine()
    restored = routine_from_json(routine.to_json())
    assert restored.title == routine.title
    assert len(restored.exercises) == len(routine.exercises)
    for original, loaded in zip(routine.exercises, restored.exercises, strict=True):
        assert original.number == loaded.number
        assert original.title == loaded.title
        assert original.instructions == loaded.instructions
        assert original.frequency == loaded.frequency
        assert original.daily_repetitions == loaded.daily_repetitions
        assert original.tips == loaded.tips


def test_exercise_from_dict_invalid_raises() -> None:
    with pytest.raises(ValueError, match="nieprawidłowe dane ćwiczenia"):
        exercise_from_dict({"number": 0, "title": "x", "instructions": "y", "frequency": "morning"})


def test_routine_from_json_invalid_raises() -> None:
    with pytest.raises(ValueError, match="nieprawidłowy JSON"):
        routine_from_json("{not json")


def test_routine_duplicate_exercise_numbers_rejected() -> None:
    data = {
        "title": "Test",
        "exercises": [
            {
                "number": 1,
                "title": "A",
                "instructions": "instr",
                "frequency": "morning",
            },
            {
                "number": 1,
                "title": "B",
                "instructions": "instr",
                "frequency": "morning",
            },
        ],
    }
    with pytest.raises(ValueError, match="unikalne"):
        routine_from_dict(data)


def test_format_routine_for_display_contains_key_sections() -> None:
    text = format_routine_for_display(default_morning_routine())
    assert "Rano - ćwiczenia" in text
    assert "Łączna liczba sesji dziennie: 6" in text
    assert "pośladków przy ścianie" in text


def test_to_dict_serializes_frequency_as_string() -> None:
    routine = default_morning_routine()
    payload = routine.to_dict()
    assert payload["exercises"][2]["frequency"] == "throughout_day"
    json.dumps(payload, ensure_ascii=False)
