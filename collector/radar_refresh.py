#!/usr/bin/env python3
"""Run the complete local radar refresh and notify on meaningful job changes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
STATUS_PATH = ROOT / "data" / "refresh_status.json"
STEP_TIMEOUT_SECONDS = {
    "jobs_collect": 20 * 60,
    "jobs_export": 2 * 60,
    "events": 5 * 60,
    "social": 5 * 60,
    "markets": 5 * 60,
    "feishu": 60,
    "online_publish": 5 * 60,
}


def command_steps(dry_run: bool) -> list[tuple[str, list[str], bool]]:
    python = sys.executable
    if dry_run:
        return [
            ("jobs_collect", [python, str(ROOT / "jobscan.py"), "collect", "--dry-run"], True),
            ("events", [python, str(ROOT / "intel_scan.py"), "events", "--dry-run"], False),
            ("social", [python, str(ROOT / "intel_scan.py"), "social", "--dry-run"], False),
            ("markets", [python, str(ROOT / "market_scan.py"), "--dry-run"], False),
            ("feishu", [python, str(ROOT / "feishu_notify.py"), "--dry-run", "--limit", "3"], False),
        ]
    return [
        ("jobs_collect", [python, str(ROOT / "jobscan.py"), "collect"], True),
        ("jobs_export", [python, str(ROOT / "jobscan.py"), "export-site"], True),
        ("events", [python, str(ROOT / "intel_scan.py"), "events"], False),
        ("social", [python, str(ROOT / "intel_scan.py"), "social"], False),
        ("markets", [python, str(ROOT / "market_scan.py")], False),
        ("feishu", [python, str(ROOT / "feishu_notify.py")], False),
    ]


def _output_lines(value: str | bytes | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value.strip().splitlines()


def run_step(name: str, command: list[str], required: bool) -> dict[str, Any]:
    started = time.monotonic()
    timeout_seconds = STEP_TIMEOUT_SECONDS[name]
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
        return_code = completed.returncode
        output_lines = _output_lines(completed.stdout)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        return_code = 124
        output_lines = _output_lines(exc.stdout or exc.output)
        output_lines.append(f"step timed out after {timeout_seconds}s")
        timed_out = True
    return {
        "name": name,
        "required": required,
        "returnCode": return_code,
        "timedOut": timed_out,
        "timeoutSeconds": timeout_seconds,
        "durationSeconds": round(time.monotonic() - started, 2),
        "outputTail": output_lines[-8:],
    }


def run_refresh(dry_run: bool = False, request_id: str | None = None) -> tuple[dict[str, Any], int]:
    started = dt.datetime.now(dt.timezone.utc)
    results: list[dict[str, Any]] = []
    hard_failure = False
    for name, command, required in command_steps(dry_run):
        result = run_step(name, command, required)
        results.append(result)
        if required and result["returnCode"]:
            hard_failure = True
    finished = dt.datetime.now(dt.timezone.utc)
    payload = {
        "startedAt": started.isoformat(),
        "finishedAt": finished.isoformat(),
        "status": "failed" if hard_failure else (
            "degraded" if any(item["returnCode"] for item in results) else "ok"
        ),
        "dryRun": dry_run,
        "steps": results,
    }
    if not dry_run:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        publish_command = [sys.executable, str(ROOT / "publish_online.py")]
        if request_id:
            publish_command.extend(["--request-id", request_id])
        publish_result = run_step("online_publish", publish_command, False)
        results.append(publish_result)
        if publish_result["returnCode"] and payload["status"] == "ok":
            payload["status"] = "degraded"
        payload["steps"] = results
        STATUS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return payload, 2 if hard_failure else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--request-id")
    args = parser.parse_args()
    payload, exit_code = run_refresh(args.dry_run, args.request_id)
    if not args.dry_run:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
