"""Testy morning_exercises_tracker (postęp dzienny i przypomnienia)."""

from __future__ import annotations

from datetime import datetime, time
from pathlib import Path

import pytest

from morning_exercises import default_morning_routine
from morning_exercises_tracker import (
    DailyProgressState,
    ExerciseTracker,
    ReminderSlot,
    default_reminder_slots,
)


def test_record_completion_increments_and_caps(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    tracker = ExerciseTracker(state_path=state_file)
    first = tracker.record_completion(3)
    assert first.completed == 1
    assert first.target == 3

    tracker.record_completion(3)
    third = tracker.record_completion(3)
    assert third.completed == 3
    fourth = tracker.record_completion(3)
    assert fourth.completed == 3


def test_new_day_resets_progress(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    tracker = ExerciseTracker(state_path=state_file)
    tracker.record_completion(1)
    state_file.write_text(
        '{"day": "1999-01-01", "counts": {"1": 1}, "fired_reminders": []}',
        encoding="utf-8",
    )
    snapshot = tracker.progress_snapshot()
    assert snapshot[0].completed == 0


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    tracker = ExerciseTracker(state_path=state_file)
    tracker.record_completion(2)
    loaded = tracker.load_state()
    assert loaded.counts[2] == 1


def test_is_day_complete_when_all_targets_met(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    tracker = ExerciseTracker(state_path=state_file)
    assert tracker.is_day_complete() is False
    tracker.record_completion(1)
    tracker.record_completion(2)
    tracker.record_completion(2)
    tracker.record_completion(3)
    tracker.record_completion(3)
    tracker.record_completion(3)
    assert tracker.is_day_complete() is True
    assert tracker.total_completed() == 6


def test_pending_reminders_only_after_time(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    tracker = ExerciseTracker(state_path=state_file)
    slot = ReminderSlot("test", time(9, 0), 1, 0)
    before = datetime(2026, 8, 6, 8, 30)
    after = datetime(2026, 8, 6, 9, 5)
    state = tracker.load_state()
    assert tracker.pending_reminders(now=before, slots=[slot], state=state) == ()
    pending = tracker.pending_reminders(now=after, slots=[slot], state=state)
    assert pending == (slot,)


def test_reminder_not_repeated_after_fired(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    tracker = ExerciseTracker(state_path=state_file)
    slot = ReminderSlot("test", time(9, 0), 1, 0)
    now = datetime(2026, 8, 6, 10, 0)
    state = tracker.load_state()
    tracker.mark_reminder_fired("test")
    state = tracker.load_state()
    assert tracker.pending_reminders(now=now, slots=[slot], state=state) == ()


def test_reminder_skipped_when_exercise_already_done(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    tracker = ExerciseTracker(state_path=state_file)
    tracker.record_completion(1)
    slot = ReminderSlot("morning_ex1", time(7, 0), 1, 0)
    now = datetime(2026, 8, 6, 8, 0)
    state = tracker.load_state()
    assert tracker.pending_reminders(now=now, slots=[slot], state=state) == ()


def test_default_reminder_slots_count() -> None:
    assert len(default_reminder_slots()) == 6


def test_daily_progress_state_from_dict() -> None:
    state = DailyProgressState.from_dict(
        {"day": "2026-08-06", "counts": {"1": 1, "3": 2}, "fired_reminders": ["a"]}
    )
    assert state.day == "2026-08-06"
    assert state.counts[1] == 1
    assert state.counts[3] == 2
    assert state.fired_reminders == ["a"]


def test_corrupt_state_file_starts_fresh(tmp_path: Path) -> None:
    state_file = tmp_path / "progress.json"
    state_file.write_text("{broken", encoding="utf-8")
    tracker = ExerciseTracker(state_path=state_file)
    assert tracker.load_state().counts == {}


def test_format_reminder_message_contains_title(tmp_path: Path) -> None:
    tracker = ExerciseTracker(state_path=tmp_path / "p.json")
    slot = default_reminder_slots()[0]
    text = tracker.format_reminder_message(slot)
    routine = default_morning_routine()
    exercise = routine.exercise_by_number(slot.exercise_number)
    assert exercise.title in text
    assert exercise.instructions in text
