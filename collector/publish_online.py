#!/usr/bin/env python3
"""Publish local radar artifacts to the private Sites backend."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "secrets" / "online.json"


def load_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = ("site_url", "ingest_secret")
    for key in required:
        if not payload.get(key):
            raise ValueError(f"missing {key}")
    return {str(key): str(value) for key, value in payload.items()}


def create_config(site_url: str, sites_authorization: str = "", path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "site_url": site_url.rstrip("/"),
        "ingest_secret": secrets.token_urlsafe(48),
        "sites_authorization": sites_authorization,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def headers(config: dict[str, str]) -> dict[str, str]:
    result = {"Authorization": f"Bearer {config['ingest_secret']}"}
    if config.get("sites_authorization"):
        result["OAI-Sites-Authorization"] = f"Bearer {config['sites_authorization']}"
    return result


def claim(config: dict[str, str]) -> dict[str, Any] | None:
    response = requests.post(
        config["site_url"] + "/api/collector/claim",
        headers=headers(config),
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("request")


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def build_payload(request_id: str | None = None) -> dict[str, Any]:
    jobs = read_json(ROOT / "data" / "jobs.json", {"meta": {}, "jobs": []})
    events = read_json(ROOT / "data" / "events.json", {"meta": {}, "items": []})
    social = read_json(ROOT / "data" / "social.json", {"meta": {}, "items": []})
    quotes = read_json(ROOT / "data" / "quotes.json", {
        "meta": {"status": "unconfigured", "notice": "尚无真实行情快照。"}, "items": [],
    })
    refresh = read_json(ROOT / "data" / "refresh_status.json", {"status": "unknown"})
    generated = refresh.get("finishedAt") or jobs.get("meta", {}).get("generatedAt")
    return {
        "generatedAt": generated or dt.datetime.now(dt.timezone.utc).isoformat(),
        "jobs": jobs,
        "events": events,
        "social": social,
        "quotes": quotes,
        "refresh": refresh,
        "requestId": request_id,
    }


def publish(config: dict[str, str], request_id: str | None = None) -> dict[str, Any]:
    response = requests.post(
        config["site_url"] + "/api/ingest",
        headers={**headers(config), "Content-Type": "application/json"},
        json=build_payload(request_id),
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--site-url", default=os.environ.get("RADAR_SITE_URL", ""))
    parser.add_argument("--sites-authorization", default=os.environ.get("RADAR_SITES_AUTHORIZATION", ""))
    parser.add_argument("--claim", action="store_true")
    parser.add_argument("--request-id")
    parser.add_argument("--update-sites-authorization", action="store_true")
    parser.add_argument("--print-ingest-secret", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.init:
            if not args.site_url:
                raise ValueError("--site-url is required")
            sites_authorization = args.sites_authorization or getpass.getpass(
                "Sites authorization token: "
            ).strip()
            create_config(args.site_url, sites_authorization)
            print(f"configured={CONFIG_PATH}")
            return 0
        config = load_config()
        if args.update_sites_authorization:
            config["sites_authorization"] = getpass.getpass(
                "Sites authorization token: "
            ).strip()
            CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            CONFIG_PATH.chmod(0o600)
            print(f"updated={CONFIG_PATH}")
            return 0
        if args.print_ingest_secret:
            print(config["ingest_secret"])
            return 0
        if args.claim:
            request = claim(config)
            print(json.dumps(request, ensure_ascii=False))
            return 0
        result = publish(config, args.request_id)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, requests.RequestException) as exc:
        print(f"online publish failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
