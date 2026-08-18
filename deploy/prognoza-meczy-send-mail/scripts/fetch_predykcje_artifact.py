#!/usr/bin/env python3
"""Pobierz predykcje_2026.xlsx z artifactu ostatniego udanego pipeline.yml."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_WORKFLOW = "pipeline.yml"
DEFAULT_ARTIFACT = "predykcje-xlsx"
DEFAULT_OUTPUT = "predykcje_2026.xlsx"
API_ROOT = "https://api.github.com"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _api_request(url: str, token: str) -> bytes:
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "prognoza-meczy-fetch-artifact",
        },
    )
    with urlopen(req, timeout=60) as resp:
        return resp.read()


def _api_json(url: str, token: str) -> dict | list:
    return json.loads(_api_request(url, token).decode("utf-8"))


def _parse_github_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def find_latest_successful_run(
    *,
    repo: str,
    token: str,
    workflow: str,
    branch: str,
    max_age_days: int,
) -> dict:
    params = urlencode(
        {
            "status": "success",
            "branch": branch,
            "per_page": "20",
        }
    )
    url = f"{API_ROOT}/repos/{repo}/actions/workflows/{workflow}/runs?{params}"
    payload = _api_json(url, token)
    runs = payload.get("workflow_runs") or []
    if not runs:
        raise RuntimeError(
            f"Brak udanego runu {workflow} na gałęzi {branch}. "
            "Najpierw uruchom workflow „Pipeline niedziela”."
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    for run in runs:
        created = _parse_github_time(run["created_at"])
        if created >= cutoff:
            return run

    latest = runs[0]
    raise RuntimeError(
        f"Ostatni udany run {workflow} (#{latest['run_number']}) jest starszy niż "
        f"{max_age_days} dni ({latest['html_url']}). Uruchom pipeline ponownie."
    )


def find_artifact_id(*, repo: str, token: str, run_id: int, artifact_name: str) -> int:
    url = f"{API_ROOT}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100"
    payload = _api_json(url, token)
    for artifact in payload.get("artifacts") or []:
        if artifact.get("name") == artifact_name and not artifact.get("expired"):
            return int(artifact["id"])
    raise RuntimeError(
        f"Run {run_id} nie ma aktywnego artifactu „{artifact_name}”. "
        "Uruchom pipeline ponownie."
    )


def download_artifact_zip(*, repo: str, token: str, artifact_id: int) -> bytes:
    url = f"{API_ROOT}/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    return _api_request(url, token)


def extract_xlsx(zip_bytes: bytes, output_name: str, dest: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        members = [name for name in zf.namelist() if name.endswith(output_name)]
        if not members:
            raise RuntimeError(
                f"Artifact nie zawiera pliku {output_name}. "
                f"Zawartość: {', '.join(zf.namelist()) or '(pusty)'}"
            )
        member = members[0]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(member))
    return dest


def fetch_predykcje_xlsx(
    *,
    repo: str,
    token: str,
    workflow: str = DEFAULT_WORKFLOW,
    branch: str = "main",
    artifact_name: str = DEFAULT_ARTIFACT,
    output_name: str = DEFAULT_OUTPUT,
    dest: Path,
    max_age_days: int = 8,
) -> dict[str, str | int]:
    run = find_latest_successful_run(
        repo=repo,
        token=token,
        workflow=workflow,
        branch=branch,
        max_age_days=max_age_days,
    )
    run_id = int(run["id"])
    artifact_id = find_artifact_id(
        repo=repo,
        token=token,
        run_id=run_id,
        artifact_name=artifact_name,
    )
    zip_bytes = download_artifact_zip(repo=repo, token=token, artifact_id=artifact_id)
    out_path = extract_xlsx(zip_bytes, output_name, dest)
    return {
        "run_id": run_id,
        "run_number": int(run["run_number"]),
        "artifact_id": artifact_id,
        "output": str(out_path.resolve()),
        "run_url": str(run["html_url"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=_env("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=_env("GITHUB_TOKEN"))
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--artifact", default=DEFAULT_ARTIFACT)
    parser.add_argument("--output-name", default=DEFAULT_OUTPUT)
    parser.add_argument("--dest", type=Path, default=Path(DEFAULT_OUTPUT))
    parser.add_argument("--max-age-days", type=int, default=8)
    parser.add_argument(
        "--fallback",
        type=Path,
        help="Użyj tego pliku z repozytorium, gdy brak artifactu (tylko ręczne testy).",
    )
    args = parser.parse_args(argv)

    if not args.repo or not args.token:
        print("Brak GITHUB_REPOSITORY lub GITHUB_TOKEN.", file=sys.stderr)
        return 2

    try:
        info = fetch_predykcje_xlsx(
            repo=args.repo,
            token=args.token,
            workflow=args.workflow,
            branch=args.branch,
            artifact_name=args.artifact,
            output_name=args.output_name,
            dest=args.dest,
            max_age_days=args.max_age_days,
        )
    except (RuntimeError, HTTPError) as exc:
        if args.fallback and args.fallback.is_file():
            args.dest.write_bytes(args.fallback.read_bytes())
            print(
                f"UWAGA: artifact niedostępny ({exc}); użyto fallback: {args.fallback}",
                file=sys.stderr,
            )
            print(str(args.dest.resolve()))
            return 0
        print(str(exc), file=sys.stderr)
        return 1

    print(
        f"Pobrano {args.output_name} z pipeline run #{info['run_number']} "
        f"(artifact {info['artifact_id']}, {info['run_url']})"
    )
    print(info["output"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
