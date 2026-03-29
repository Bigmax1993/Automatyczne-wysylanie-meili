#!/usr/bin/env python3
"""
Proste GUI (Tkinter) do uruchamiania pipeline przez run_with_env.ps1.

Uruchomienie z konsoli:
  python pipeline_launcher_gui.py

Bez okna konsoli (Windows):
  pythonw pipeline_launcher_gui.py
"""

from __future__ import annotations

import locale
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Mapping
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

PROJECT_DIR = Path(__file__).resolve().parent
RUN_WITH_ENV = PROJECT_DIR / "run_with_env.ps1"
VERSION_FILE = PROJECT_DIR / "VERSION"
LOCAL_ENV = PROJECT_DIR / "local_env.ps1"


def read_version(version_path: Path) -> str:
    """Czyta wersję z pliku (np. VERSION); przy błędzie zwraca '?'."""
    try:
        return version_path.read_text(encoding="utf-8").strip() or "?"
    except OSError:
        return "?"


def _read_version() -> str:
    return read_version(VERSION_FILE)


def env_status_line(var_name: str, environ: Mapping[str, str] | None = None) -> str:
    """Jedna linia statusu zmiennej (bez ujawniania wartości)."""
    env: Mapping[str, str] = os.environ if environ is None else environ
    v = env.get(var_name)
    if not v or not str(v).strip():
        return f"{var_name}: (brak w tej sesji)"
    s = str(v).strip()
    return f"{var_name}: ustawiony, {len(s)} znaków"


def build_powershell_run_with_env_args(
    run_with_env_script: Path,
    *,
    check_only: bool = False,
    skip_build: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Argumenty dla subprocess: powershell.exe … -File run_with_env.ps1 [przełączniki]."""
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(run_with_env_script.resolve()),
    ]
    if check_only:
        args.append("-CheckOnly")
    if skip_build:
        args.append("-SkipBuild")
    if dry_run:
        args.append("-DryRun")
    return args


def format_run_start_banner(ps_args: list[str]) -> str:
    """Tekst nagłówka w logu: tylko przełączniki po -File <ścieżka> (indeksy 6+)."""
    tail = ps_args[6:] if len(ps_args) > 6 else []
    return " ".join(tail)


class PipelineLauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Pipeline mailing — {_read_version()}")
        self.geometry("900x640")
        self.minsize(640, 480)

        self._proc: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._out_queue: queue.Queue[str] = queue.Queue()
        self._run_token = 0

        self._build_ui()
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        head = ttk.Label(
            main,
            text=f"Katalog projektu: {PROJECT_DIR}\n"
            f"Wersja pipeline: {_read_version()}",
            justify=tk.LEFT,
        )
        head.pack(anchor=tk.W, **pad)

        status_fr = ttk.LabelFrame(main, text="Status", padding=8)
        status_fr.pack(fill=tk.X, **pad)
        self._status_local = ttk.Label(status_fr, text="")
        self._status_local.pack(anchor=tk.W)
        self._status_keys = ttk.Label(status_fr, text="", justify=tk.LEFT)
        self._status_keys.pack(anchor=tk.W)
        ttk.Button(status_fr, text="Odśwież status", command=self._refresh_status).pack(
            anchor=tk.W, pady=(6, 0)
        )
        self._refresh_status()

        run_fr = ttk.LabelFrame(main, text="Uruchomienie", padding=8)
        run_fr.pack(fill=tk.X, **pad)

        row1 = ttk.Frame(run_fr)
        row1.pack(fill=tk.X)
        ttk.Button(
            row1,
            text="Test OpenAI (-CheckOnly)",
            command=lambda: self._start_run(check_only=True),
        ).pack(side=tk.LEFT, padx=(0, 6), pady=2)
        ttk.Button(
            row1,
            text="Pełny pipeline (SerpAPI + clean + wysyłka)",
            command=lambda: self._start_run(),
        ).pack(side=tk.LEFT, padx=6, pady=2)
        row2 = ttk.Frame(run_fr)
        row2.pack(fill=tk.X)
        ttk.Button(
            row2,
            text="Bez SerpAPI (-SkipBuild)",
            command=lambda: self._start_run(skip_build=True),
        ).pack(side=tk.LEFT, padx=(0, 6), pady=2)
        ttk.Button(
            row2,
            text="Bez SerpAPI, dry-run (-SkipBuild -DryRun)",
            command=lambda: self._start_run(skip_build=True, dry_run=True),
        ).pack(side=tk.LEFT, padx=6, pady=2)

        row3 = ttk.Frame(run_fr)
        row3.pack(fill=tk.X, pady=(6, 0))
        self._stop_btn = ttk.Button(row3, text="Zatrzymaj", command=self._stop_run, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row3, text="Wyczyść log", command=self._clear_log).pack(side=tk.LEFT, padx=6)

        folders_fr = ttk.LabelFrame(main, text="Foldery", padding=8)
        folders_fr.pack(fill=tk.X, **pad)
        docs = Path.home() / "Documents"
        ttk.Button(
            folders_fr,
            text="Logi pipeline (Documents\\pipeline_logs)",
            command=lambda: self._open_path(docs / "pipeline_logs"),
        ).pack(side=tk.LEFT, padx=(0, 6), pady=2)
        ttk.Button(
            folders_fr,
            text="Kontakty (Documents\\kontakty)",
            command=lambda: self._open_path(docs / "kontakty"),
        ).pack(side=tk.LEFT, padx=6, pady=2)
        ttk.Button(
            folders_fr,
            text="Katalog projektu",
            command=lambda: self._open_path(PROJECT_DIR),
        ).pack(side=tk.LEFT, padx=6, pady=2)

        log_fr = ttk.LabelFrame(main, text="Wyjście (stdout/stderr)", padding=4)
        log_fr.pack(fill=tk.BOTH, expand=True, **pad)
        self._log = scrolledtext.ScrolledText(log_fr, height=18, wrap=tk.WORD, font=("Consolas", 9))
        self._log.pack(fill=tk.BOTH, expand=True)

    def _refresh_status(self) -> None:
        if LOCAL_ENV.is_file():
            self._status_local.config(text="local_env.ps1: znaleziony", foreground="")
        else:
            self._status_local.config(
                text="local_env.ps1: BRAK — skopiuj z local_env.ps1.example",
                foreground="darkred",
            )
        keys = "\n".join(
            [
                env_status_line("OPENAI_API_KEY"),
                env_status_line("GMAIL_APP_PASSWORD"),
                env_status_line("GMAIL_SENDER_EMAIL"),
                env_status_line("SERPAPI_API_KEY"),
            ]
        )
        self._status_keys.config(
            text="Zmienne w tej sesji (GUI dziedziczy po uruchomieniu z terminala):\n" + keys
        )

    def _open_path(self, p: Path) -> None:
        p = p.resolve()
        if not p.exists():
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Folder", f"Nie można utworzyć:\n{p}\n{e}")
                return
        try:
            if sys.platform == "win32":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except OSError as e:
            messagebox.showerror("Folder", str(e))

    def _clear_log(self) -> None:
        self._log.delete("1.0", tk.END)

    def _append_log(self, text: str) -> None:
        self._log.insert(tk.END, text)
        self._log.see(tk.END)

    def _poll_queue(self) -> None:
        try:
            while True:
                line = self._out_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _start_run(
        self,
        *,
        check_only: bool = False,
        skip_build: bool = False,
        dry_run: bool = False,
    ) -> None:
        if self._proc is not None and self._proc.poll() is None:
            messagebox.showinfo("Pipeline", "Zadanie już działa. Zatrzymaj je lub poczekaj na koniec.")
            return
        if not RUN_WITH_ENV.is_file():
            messagebox.showerror("Błąd", f"Brak pliku:\n{RUN_WITH_ENV}")
            return
        if not LOCAL_ENV.is_file():
            messagebox.showerror(
                "Brak local_env.ps1",
                "Skopiuj local_env.ps1.example → local_env.ps1 i uzupełnij klucze.",
            )
            return

        args = build_powershell_run_with_env_args(
            RUN_WITH_ENV,
            check_only=check_only,
            skip_build=skip_build,
            dry_run=dry_run,
        )

        self._run_token += 1
        token = self._run_token
        self._append_log(f"\n--- Start: {format_run_start_banner(args)} ---\n")

        # Dekodowanie zgodne z konsolą Windows (np. cp1250) — mniej „krzaków” niż wymuszony UTF-8.
        child_enc = locale.getpreferredencoding(False) or "utf-8"

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        try:
            self._proc = subprocess.Popen(
                args,
                cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding=child_enc,
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as e:
            messagebox.showerror("Uruchomienie", str(e))
            return

        self._stop_btn.config(state=tk.NORMAL)

        def reader() -> None:
            assert self._proc and self._proc.stdout
            try:
                for line in self._proc.stdout:
                    if token != self._run_token:
                        break
                    self._out_queue.put(line)
            finally:
                try:
                    self._proc.stdout.close()
                except Exception:
                    pass
                code = self._proc.wait()
                self._out_queue.put(f"\n--- Koniec, kod wyjścia: {code} ---\n")

        self._reader_thread = threading.Thread(target=reader, daemon=True)
        self._reader_thread.start()

        def on_done() -> None:
            if self._reader_thread:
                self._reader_thread.join(timeout=0.5)
            self._proc = None
            self._stop_btn.config(state=tk.DISABLED)

        def watch() -> None:
            if self._proc is not None and self._proc.poll() is None:
                self.after(200, watch)
            else:
                on_done()

        self.after(300, watch)

    def _stop_run(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            return
        self._run_token += 1
        try:
            self._proc.terminate()
        except OSError:
            pass
        self._append_log("\n--- Przerwano przez użytkownika ---\n")

    def _on_close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            if not messagebox.askyesno("Zamknij", "Pipeline wciąż działa. Zatrzymać i zamknąć?"):
                return
            self._stop_run()
        self.destroy()


def main() -> None:
    app = PipelineLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
