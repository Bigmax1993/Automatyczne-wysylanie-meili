"""
Śledzenie dziennego postępu ćwiczeń i harmonogram przypomnień.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from morning_exercises import (
    default_morning_routine,
    Exercise,
    MorningExerciseRoutine,
)

logger = logging.getLogger(__name__)

_DEFAULT_STATE_DIR: Final[Path] = Path.home() / ".morning_exercises"
STATE_PATH: Final[Path] = Path(
    os.environ.get("MORNING_EXERCISES_STATE_PATH", str(_DEFAULT_STATE_DIR / "progress.json"))
)


@dataclass(frozen=True)
class ExerciseProgress:
    """Postęp jednego ćwiczenia w bieżącym dniu."""

    exercise: Exercise
    completed: int
    target: int

    @property
    def remaining(self) -> int:
        return max(0, self.target - self.completed)

    @property
    def is_complete(self) -> bool:
        return self.completed >= self.target


@dataclass
class DailyProgressState:
    """Stan postępu zapisywany w pliku JSON."""

    day: str
    counts: dict[int, int]
    fired_reminders: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "counts": self.counts,
            "fired_reminders": self.fired_reminders,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DailyProgressState:
        day = str(data.get("day", ""))
        counts_raw = data.get("counts", {})
        fired_raw = data.get("fired_reminders", [])
        counts: dict[int, int] = {}
        if isinstance(counts_raw, Mapping):
            for key, value in counts_raw.items():
                counts[int(key)] = int(value)
        fired: list[str] = []
        if isinstance(fired_raw, Sequence) and not isinstance(fired_raw, (str, bytes)):
            fired = [str(item) for item in fired_raw]
        return cls(day=day, counts=counts, fired_reminders=fired)


@dataclass(frozen=True)
class ReminderSlot:
    """Jedno przypomnienie o ćwiczeniu w określonym czasie."""

    key: str
    at: time
    exercise_number: int
    min_completed_before: int

    def should_fire(self, progress: DailyProgressState, now: datetime) -> bool:
        if self.key in progress.fired_reminders:
            return False
        if now.time() < self.at:
            return False
        done = progress.counts.get(self.exercise_number, 0)
        return done <= self.min_completed_before


def default_reminder_slots() -> tuple[ReminderSlot, ...]:
    """Domyślny harmonogram przypomnień zgodny z notatkami."""
    return (
        ReminderSlot("morning_ex1", time(7, 0), 1, 0),
        ReminderSlot("morning_ex2", time(7, 0), 2, 0),
        ReminderSlot("midday_ex3_1", time(10, 0), 3, 0),
        ReminderSlot("afternoon_ex3_2", time(14, 0), 3, 1),
        ReminderSlot("evening_ex2", time(20, 0), 2, 1),
        ReminderSlot("evening_ex3_3", time(18, 0), 3, 2),
    )


def _today_iso() -> str:
    return date.today().isoformat()


def _empty_state_for_today() -> DailyProgressState:
    return DailyProgressState(day=_today_iso(), counts={}, fired_reminders=[])


class ExerciseTracker:
    """Odczyt/zapis postępu i rejestrowanie wykonanych sesji."""

    def __init__(
        self,
        routine: MorningExerciseRoutine | None = None,
        state_path: Path | None = None,
    ) -> None:
        self._routine = routine or default_morning_routine()
        self._state_path = state_path or STATE_PATH

    @property
    def routine(self) -> MorningExerciseRoutine:
        return self._routine

    @property
    def state_path(self) -> Path:
        return self._state_path

    def load_state(self) -> DailyProgressState:
        path = self._state_path
        if not path.is_file():
            return _empty_state_for_today()
        try:
            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("stan musi być obiektem JSON")
            state = DailyProgressState.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Nie można wczytać stanu z %s: %s — tworzę nowy", path, exc)
            return _empty_state_for_today()
        if state.day != _today_iso():
            return _empty_state_for_today()
        return state

    def save_state(self, state: DailyProgressState) -> None:
        path = self._state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(
                json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Nie można zapisać stanu do %s: %s", path, exc)
            raise

    def progress_snapshot(self, state: DailyProgressState | None = None) -> tuple[ExerciseProgress, ...]:
        current = state or self.load_state()
        items: list[ExerciseProgress] = []
        for exercise in self._routine.exercises:
            completed = current.counts.get(exercise.number, 0)
            items.append(
                ExerciseProgress(
                    exercise=exercise,
                    completed=completed,
                    target=exercise.daily_repetitions,
                )
            )
        return tuple(items)

    def record_completion(self, exercise_number: int) -> ExerciseProgress:
        exercise = self._routine.exercise_by_number(exercise_number)
        state = self.load_state()
        current = state.counts.get(exercise_number, 0)
        if current >= exercise.daily_repetitions:
            return ExerciseProgress(
                exercise=exercise,
                completed=current,
                target=exercise.daily_repetitions,
            )
        state.counts[exercise_number] = current + 1
        self.save_state(state)
        return ExerciseProgress(
            exercise=exercise,
            completed=state.counts[exercise_number],
            target=exercise.daily_repetitions,
        )

    def is_day_complete(self, state: DailyProgressState | None = None) -> bool:
        return all(item.is_complete for item in self.progress_snapshot(state))

    def total_completed(self, state: DailyProgressState | None = None) -> int:
        return sum(item.completed for item in self.progress_snapshot(state))

    def total_target(self) -> int:
        return self._routine.total_daily_sessions()

    def pending_reminders(
        self,
        now: datetime | None = None,
        slots: Sequence[ReminderSlot] | None = None,
        state: DailyProgressState | None = None,
    ) -> tuple[ReminderSlot, ...]:
        current = state or self.load_state()
        moment = now or datetime.now()
        schedule = slots or default_reminder_slots()
        return tuple(slot for slot in schedule if slot.should_fire(current, moment))

    def mark_reminder_fired(self, reminder_key: str) -> DailyProgressState:
        state = self.load_state()
        if reminder_key not in state.fired_reminders:
            state.fired_reminders.append(reminder_key)
            self.save_state(state)
        return state

    def format_reminder_message(self, slot: ReminderSlot) -> str:
        exercise = self._routine.exercise_by_number(slot.exercise_number)
        return (
            f"Czas na ćwiczenie {exercise.number}: {exercise.title}\n\n"
            f"{exercise.instructions}"
        )


def frequency_label(exercise: Exercise) -> str:
    from morning_exercises import ScheduleFrequency

    mapping = {
        ScheduleFrequency.MORNING: "rano",
        ScheduleFrequency.MORNING_EVENING: "rano i wieczorem",
        ScheduleFrequency.THROUGHOUT_DAY: "w ciągu dnia",
    }
    return mapping[exercise.frequency]
