# -*- coding: utf-8 -*-
"""
Jednorazowa konfiguracja OAuth do uploadu na folder „Mój dysk” (GitHub Actions).

1. Google Cloud → APIs & Services → Credentials → Create OAuth client ID → Desktop app
2. Pobierz JSON → zapisz jako secrets/gdrive-oauth-client.json
3. python scripts/gdrive_oauth_setup.py
4. Skrypt ustawi secrets GitHub: GDRIVE_OAUTH_CLIENT_ID, GDRIVE_OAUTH_CLIENT_SECRET, GDRIVE_OAUTH_REFRESH_TOKEN
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = ["https://www.googleapis.com/auth/drive"]
DEFAULT_CLIENT = ROOT / "secrets" / "gdrive-oauth-client.json"
DEFAULT_REPO = "Bigmax1993/wyszukiwarka-materialow-budowlanych-ukraina"


def _client_config_from_env() -> dict | None:
    cid = (os.environ.get("GDRIVE_OAUTH_CLIENT_ID") or "").strip()
    csec = (os.environ.get("GDRIVE_OAUTH_CLIENT_SECRET") or "").strip()
    if cid and csec:
        return {
            "client_id": cid,
            "client_secret": csec,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    return None


def _resolve_client_config(path: Path) -> dict:
    if path.is_file():
        return _load_client_config(path)
    cfg = _client_config_from_env()
    if cfg:
        return cfg
    raise SystemExit(
        f"Brak {path} oraz env GDRIVE_OAUTH_CLIENT_ID / GDRIVE_OAUTH_CLIENT_SECRET"
    )


def _load_client_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "installed" in data:
        return data["installed"]
    if "web" in data:
        return data["web"]
    raise SystemExit("JSON musi zawierac sekcje installed lub web (OAuth client).")


def main() -> int:
    parser = argparse.ArgumentParser(description="OAuth setup dla uploadu Google Drive z CI")
    parser.add_argument("--client-json", type=Path, default=DEFAULT_CLIENT)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPO", DEFAULT_REPO))
    parser.add_argument(
        "--sync-workflow",
        default=os.environ.get("GDRIVE_SYNC_WORKFLOW", "Sync wyniki Google Drive UA"),
    )
    parser.add_argument("--no-github", action="store_true", help="Tylko wypisz tokeny, bez gh secret set")
    args = parser.parse_args()

    if not args.client_json.is_file() and not _client_config_from_env():
        print(f"Brak pliku: {args.client_json}")
        print("Utworz OAuth Desktop client w Google Cloud i pobierz JSON,")
        print("albo ustaw env GDRIVE_OAUTH_CLIENT_ID + GDRIVE_OAUTH_CLIENT_SECRET.")
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("pip install google-auth-oauthlib")
        return 1

    cfg = _resolve_client_config(args.client_json)
    client_config = {
        "installed": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "redirect_uris": cfg.get("redirect_uris", ["http://localhost"]),
            "auth_uri": cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    print("Otwieram przegladarke — zaloguj sie na konto Google z dostepem do folderu UA...")
    creds = flow.run_local_server(port=0, open_browser=True)
    if not creds.refresh_token:
        print("Brak refresh_token — usun dostep aplikacji w https://myaccount.google.com/permissions i sprobuj ponownie.")
        return 1

    client_id = cfg["client_id"]
    client_secret = cfg["client_secret"]
    refresh = creds.refresh_token

    print("\n=== Tokeny (zapisz w GitHub Secrets) ===")
    print(f"GDRIVE_OAUTH_CLIENT_ID={client_id}")
    print("GDRIVE_OAUTH_CLIENT_SECRET=***")
    print(f"GDRIVE_OAUTH_REFRESH_TOKEN={refresh[:20]}...")

    if args.no_github:
        return 0

    for name, value in (
        ("GDRIVE_OAUTH_CLIENT_ID", client_id),
        ("GDRIVE_OAUTH_CLIENT_SECRET", client_secret),
        ("GDRIVE_OAUTH_REFRESH_TOKEN", refresh),
    ):
        subprocess.run(
            ["gh", "secret", "set", name, "-R", args.repo],
            input=value,
            text=True,
            check=True,
        )
        print(f"OK: gh secret set {name}")

    subprocess.run(
        ["gh", "workflow", "run", args.sync_workflow, "-R", args.repo],
        check=False,
    )
    print(f"\nGotowe. Sprawdz Actions: https://github.com/{args.repo}/actions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
