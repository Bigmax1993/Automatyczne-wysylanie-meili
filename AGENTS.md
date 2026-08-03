# AGENTS.md

## Cursor Cloud specific instructions

This repo is a **Python 3 CLI email-automation pipeline** (SerpAPI lead collection → OpenAI
cleaning/validation → Gmail SMTP send). There is **no web server or long-running service**;
everything runs as one-shot CLI scripts. The primary entry point is
`clean_validate_send_pipeline.py`. Full docs: `README.md` and `docs/DOKUMENTACJA_PROJEKTU.md`
(both in Polish). Environment variables are documented in `env.example`.

### Environment

- Dependencies are installed into a project virtualenv at `.venv` (gitignored). The startup
  update script creates/refreshes it, so activate it before running anything:
  `source .venv/bin/activate`.
- System packages `python3-venv` and `python3-tk` are required and are baked into the VM
  snapshot. `python3-tk` is only needed so `tests/test_pipeline_launcher_gui.py` can import
  `pipeline_launcher_gui.py` (it does `import tkinter`); without it those tests error out.

### Testing

- Run the Python suite exactly as CI does (`.github/workflows/main.yml`):
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DRY_RUN=1 python -m pytest tests -v --tb=short`.
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` is important — third-party pytest plugins can interfere
  with the subprocess/import tests.
- Expect ~253 passed and ~14 skipped on Linux. The skips are the **PowerShell/Pester** tests
  (`tests/powershell/*.Tests.ps1`) — they need Windows + Pester and cannot run here. The
  Python `test_run_*_ps1.py` tests only parse the `.ps1` text and do run on Linux.
- Tests mock OpenAI and never hit the network or SMTP, so **no API keys are needed** to run
  the suite.

### Running the pipeline (no linter is configured; CI runs pytest only)

- Fully offline, no secrets: `--validate-only` reads a CSV/XLSX and reports how many rows are
  sendable / blocked / invalid (exercises table reading, column mapping, email validation,
  domain blocklist). Recognized email column headers include `E-mail rekrutacyjny`, `Email`,
  `E-mail`; company header is `Firma`. Example:
  `python clean_validate_send_pipeline.py --input <file.xlsx> --validate-only --skip-extra-contacts`.
- A real clean/send run needs `OPENAI_API_KEY` (cleaning + subject/body generation) and, for
  actual sending, `GMAIL_APP_PASSWORD` + `GMAIL_SENDER_EMAIL`. Use `--dry-run` to skip SMTP.
  `--dry-run` still calls OpenAI, so it still needs `OPENAI_API_KEY`.
- The `pipeline_launcher_gui.py` Tkinter GUI only shells out to the PowerShell scripts, which
  are Windows-only, so the GUI is not runnable end-to-end on this Linux VM.
