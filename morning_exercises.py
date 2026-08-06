"""
Strukturyzacja rutyny ćwiczeń rehabilitacyjnych (odręczne notatki: „Rano - ćwiczenia”).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Mapping, Sequence

logger = logging.getLogger(__name__)

ROUTINE_TITLE: Final[str] = "Rano - ćwiczenia"


class ScheduleFrequency(str, Enum):
    """Częstotliwość wykonywania ćwiczenia."""

    MORNING = "morning"
    MORNING_EVENING = "morning_evening"
    THROUGHOUT_DAY = "throughout_day"


@dataclass(frozen=True)
class Exercise:
    """Pojedyncze ćwiczenie z instrukcją i harmonogramem."""

    number: int
    title: str
    instructions: str
    frequency: ScheduleFrequency
    daily_repetitions: int = 1
    tips: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"numer ćwiczenia musi być >= 1, otrzymano: {self.number}")
        if not self.title.strip():
            raise ValueError("tytuł ćwiczenia nie może być pusty")
        if not self.instructions.strip():
            raise ValueError("instrukcja ćwiczenia nie może być pusta")
        if self.daily_repetitions < 1:
            raise ValueError(
                f"daily_repetitions musi być >= 1, otrzymano: {self.daily_repetitions}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "instructions": self.instructions,
            "frequency": self.frequency.value,
            "daily_repetitions": self.daily_repetitions,
            "tips": list(self.tips),
        }


@dataclass(frozen=True)
class MorningExerciseRoutine:
    """Pełna rutyna porannych ćwiczeń z notatek."""

    title: str
    exercises: tuple[Exercise, ...]

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("tytuł rutiny nie może być pusty")
        if not self.exercises:
            raise ValueError("rutina musi zawierać co najmniej jedno ćwiczenie")
        numbers = [ex.number for ex in self.exercises]
        if len(numbers) != len(set(numbers)):
            raise ValueError("numery ćwiczeń muszą być unikalne")
        if numbers != sorted(numbers):
            raise ValueError("ćwiczenia muszą być uporządkowane według numeru")

    def exercise_by_number(self, number: int) -> Exercise:
        for ex in self.exercises:
            if ex.number == number:
                return ex
        raise KeyError(f"brak ćwiczenia o numerze {number}")

    def total_daily_sessions(self) -> int:
        return sum(ex.daily_repetitions for ex in self.exercises)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "exercises": [ex.to_dict() for ex in self.exercises],
            "total_daily_sessions": self.total_daily_sessions(),
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def _default_routine_exercises() -> tuple[Exercise, ...]:
    return (
        Exercise(
            number=1,
            title="Zginanie kolana na brzuchu (oparcie na palcach)",
            instructions=(
                "Leżeć na brzuchu, opieramy się dużymi palcami. "
                "Zginamy i prostujemy kolano, podnosząc je."
            ),
            frequency=ScheduleFrequency.MORNING,
            daily_repetitions=1,
        ),
        Exercise(
            number=2,
            title="Zginanie kolana z poduszką pod nogami",
            instructions=(
                "Leżymy na brzuchu, poduszka pod nogami (stopa na podłodze). "
                "Gdy stopa jest zgięta do siebie, powoli zginamy kolano."
            ),
            frequency=ScheduleFrequency.MORNING_EVENING,
            daily_repetitions=2,
            tips=(
                "Kolano nie ucieka na bok.",
                "Nie unosimy pośladków.",
            ),
        ),
        Exercise(
            number=3,
            title="Napinanie pośladków przy ścianie",
            instructions=(
                "Stoimy przodem do ściany. Ręce oparte o ścianę na szerokość barków. "
                "Tułów i miednica powinny być prosto. "
                "Stopy na zewnątrz na początku, a potem stopy do środka — "
                "napinamy i rozluźniamy pośladki."
            ),
            frequency=ScheduleFrequency.THROUGHOUT_DAY,
            daily_repetitions=3,
            tips=("Wykonuj w ciągu dnia.",),
        ),
    )


def default_morning_routine() -> MorningExerciseRoutine:
    """Zwraca rutinę odpowiadającą odręcznym notatkom „Rano - ćwiczenia”."""
    return MorningExerciseRoutine(
        title=ROUTINE_TITLE,
        exercises=_default_routine_exercises(),
    )


def _parse_frequency(raw: str) -> ScheduleFrequency:
    try:
        return ScheduleFrequency(raw)
    except ValueError:
        valid = ", ".join(sorted(f.value for f in ScheduleFrequency))
        raise ValueError(f"nieznana częstotliwość '{raw}', oczekiwane: {valid}") from None


def exercise_from_dict(data: Mapping[str, Any]) -> Exercise:
    """Deserializuje ćwiczenie z dict (np. JSON)."""
    try:
        number = int(data["number"])
        title = str(data["title"])
        instructions = str(data["instructions"])
        frequency = _parse_frequency(str(data["frequency"]))
        daily_repetitions = int(data.get("daily_repetitions", 1))
        tips_raw = data.get("tips", [])
        if not isinstance(tips_raw, Sequence) or isinstance(tips_raw, (str, bytes)):
            raise TypeError("pole 'tips' musi być listą ciągów")
        tips = tuple(str(t) for t in tips_raw)
        return Exercise(
            number=number,
            title=title,
            instructions=instructions,
            frequency=frequency,
            daily_repetitions=daily_repetitions,
            tips=tips,
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Błąd deserializacji ćwiczenia: %s", exc)
        raise ValueError(f"nieprawidłowe dane ćwiczenia: {exc}") from exc


def routine_from_dict(data: Mapping[str, Any]) -> MorningExerciseRoutine:
    """Deserializuje rutinę z dict (np. JSON)."""
    try:
        title = str(data["title"])
        exercises_raw = data["exercises"]
        if not isinstance(exercises_raw, Sequence) or isinstance(exercises_raw, (str, bytes)):
            raise TypeError("pole 'exercises' musi być listą")
        exercises = tuple(exercise_from_dict(item) for item in exercises_raw)
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Błąd deserializacji rutiny: %s", exc)
        raise ValueError(f"nieprawidłowe dane rutiny: {exc}") from exc
    return MorningExerciseRoutine(title=title, exercises=exercises)


def routine_from_json(raw: str) -> MorningExerciseRoutine:
    """Deserializuje rutinę z łańcucha JSON."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Błąd parsowania JSON rutiny: %s", exc)
        raise ValueError(f"nieprawidłowy JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON rutiny musi być obiektem")
    return routine_from_dict(payload)


def format_routine_for_display(routine: MorningExerciseRoutine) -> str:
    """Formatuje rutinę jako czytelny tekst (np. do logu lub konsoli)."""
    lines: list[str] = [routine.title, ""]
    for ex in routine.exercises:
        lines.append(f"{ex.number}. {ex.title}")
        lines.append(f"   {ex.instructions}")
        if ex.tips:
            for tip in ex.tips:
                lines.append(f"   • {tip}")
        freq_label = {
            ScheduleFrequency.MORNING: "rano",
            ScheduleFrequency.MORNING_EVENING: "rano i wieczorem",
            ScheduleFrequency.THROUGHOUT_DAY: "w ciągu dnia",
        }[ex.frequency]
        reps = ex.daily_repetitions
        lines.append(f"   Częstotliwość: {freq_label} ({reps}× dziennie)")
        lines.append("")
    lines.append(f"Łączna liczba sesji dziennie: {routine.total_daily_sessions()}")
    return "\n".join(lines)
