#!/usr/bin/env python3
"""
GUI (Tkinter) do rutiny „Rano - ćwiczenia”: instrukcje, postęp dzienny i przypomnienia.

Uruchomienie:
  python3 morning_exercises_gui.py

Bez okna konsoli (Windows):
  pythonw morning_exercises_gui.py
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from morning_exercises import default_morning_routine, format_routine_for_display
from morning_exercises_tracker import (
    ExerciseProgress,
    ExerciseTracker,
    ReminderSlot,
    default_reminder_slots,
    frequency_label,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 60_000


class MorningExercisesApp(tk.Tk):
    def __init__(self, tracker: ExerciseTracker | None = None) -> None:
        super().__init__()
        self._tracker = tracker or ExerciseTracker()
        self._routine = self._tracker.routine
        self._reminder_slots = default_reminder_slots()
        self._exercise_frames: dict[int, dict[str, tk.Widget]] = {}

        self.title(self._routine.title)
        self.geometry("760x700")
        self.minsize(560, 480)

        self._build_ui()
        self._refresh_progress()
        self._poll_reminders()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 4}
        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(
            main,
            text=f"{self._routine.title}\nPlik postępu: {self._tracker.state_path}",
            justify=tk.LEFT,
        )
        header.pack(anchor=tk.W, **pad)

        self._summary = ttk.Label(main, text="", font=("", 11, "bold"))
        self._summary.pack(anchor=tk.W, **pad)

        controls = ttk.Frame(main)
        controls.pack(fill=tk.X, **pad)
        self._reminders_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            controls,
            text="Przypomnienia w aplikacji",
            variable=self._reminders_var,
        ).pack(side=tk.LEFT)
        ttk.Button(controls, text="Odśwież", command=self._refresh_progress).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        ttk.Button(controls, text="Pełna rutina (tekst)", command=self._show_full_routine).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        canvas = tk.Canvas(main, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar.pack(fill=tk.Y, side=tk.RIGHT)

        for exercise in self._routine.exercises:
            self._build_exercise_card(scroll_frame, exercise)

        self._status = ttk.Label(main, text="", wraplength=720, justify=tk.LEFT)
        self._status.pack(anchor=tk.W, pady=(8, 0))

    def _build_exercise_card(self, parent: ttk.Frame, exercise) -> None:
        frame = ttk.LabelFrame(
            parent,
            text=f"{exercise.number}. {exercise.title}",
            padding=10,
        )
        frame.pack(fill=tk.X, padx=4, pady=6)

        instructions = ttk.Label(frame, text=exercise.instructions, wraplength=680, justify=tk.LEFT)
        instructions.pack(anchor=tk.W)

        if exercise.tips:
            for tip in exercise.tips:
                ttk.Label(frame, text=f"• {tip}", wraplength=680, justify=tk.LEFT).pack(anchor=tk.W)

        meta = (
            f"Częstotliwość: {frequency_label(exercise)} "
            f"({exercise.daily_repetitions}× dziennie)"
        )
        ttk.Label(frame, text=meta).pack(anchor=tk.W, pady=(4, 0))

        progress = ttk.Label(frame, text="")
        progress.pack(anchor=tk.W, pady=(4, 0))

        action_row = ttk.Frame(frame)
        action_row.pack(anchor=tk.W, pady=(6, 0))
        done_btn = ttk.Button(
            action_row,
            text="Oznacz jako wykonane",
            command=lambda n=exercise.number: self._mark_done(n),
        )
        done_btn.pack(side=tk.LEFT)

        self._exercise_frames[exercise.number] = {
            "frame": frame,
            "progress": progress,
            "button": done_btn,
        }

    def _mark_done(self, exercise_number: int) -> None:
        try:
            result = self._tracker.record_completion(exercise_number)
        except KeyError:
            messagebox.showerror("Błąd", f"Nieznane ćwiczenie: {exercise_number}")
            return
        except OSError as exc:
            logger.exception("Zapis postępu nie powiódł się")
            messagebox.showerror("Błąd zapisu", str(exc))
            return

        self._refresh_progress()
        if result.is_complete:
            messagebox.showinfo(
                "Gotowe",
                f"Ćwiczenie {result.exercise.number} ukończone na dziś "
                f"({result.completed}/{result.target}).",
            )
        else:
            messagebox.showinfo(
                "Zapisano",
                f"Ćwiczenie {result.exercise.number}: {result.completed}/{result.target} na dziś.",
            )

    def _refresh_progress(self) -> None:
        snapshot = self._tracker.progress_snapshot()
        completed_total = self._tracker.total_completed()
        target_total = self._tracker.total_target()
        self._summary.config(
            text=f"Postęp dziś: {completed_total}/{target_total} sesji"
        )

        for item in snapshot:
            widgets = self._exercise_frames[item.exercise.number]
            progress_label = widgets["progress"]
            button = widgets["button"]
            progress_label.config(text=f"Wykonane: {item.completed}/{item.target}")
            if item.is_complete:
                button.state(["disabled"])
            else:
                button.state(["!disabled"])

        if self._tracker.is_day_complete():
            self._status.config(text="Wszystkie ćwiczenia na dziś ukończone. Dobra robota!")
        else:
            next_slots = self._upcoming_reminder_text()
            self._status.config(text=next_slots)

    def _upcoming_reminder_text(self) -> str:
        now = datetime.now()
        state = self._tracker.load_state()
        pending = [
            slot
            for slot in self._reminder_slots
            if slot.key not in state.fired_reminders and slot.at >= now.time()
        ]
        if not pending:
            return "Brak zaplanowanych przypomnień na resztę dnia (lub już wykonane)."
        first = min(pending, key=lambda s: s.at)
        ex = self._routine.exercise_by_number(first.exercise_number)
        return (
            f"Następne przypomnienie: {first.at.strftime('%H:%M')} — "
            f"ćwiczenie {ex.number} ({ex.title})"
        )

    def _show_full_routine(self) -> None:
        messagebox.showinfo(self._routine.title, format_routine_for_display(self._routine))

    def _poll_reminders(self) -> None:
        if self._reminders_var.get():
            self._check_reminders()
        self.after(POLL_INTERVAL_MS, self._poll_reminders)

    def _check_reminders(self) -> None:
        now = datetime.now()
        state = self._tracker.load_state()
        pending = self._tracker.pending_reminders(now=now, slots=self._reminder_slots, state=state)
        for slot in pending:
            message = self._tracker.format_reminder_message(slot)
            if messagebox.askokcancel("Przypomnienie — ćwiczenia", message):
                try:
                    self._tracker.record_completion(slot.exercise_number)
                    self._refresh_progress()
                except (KeyError, OSError) as exc:
                    logger.exception("Oznaczenie po przypomnieniu nie powiodło się")
                    messagebox.showerror("Błąd", str(exc))
            self._tracker.mark_reminder_fired(slot.key)

    def _on_close(self) -> None:
        self.destroy()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if sys.platform == "win32":
        try:
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = MorningExercisesApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
