#!/usr/bin/env python3
"""Claim at most one online refresh request and execute it locally."""

from __future__ import annotations

import subprocess
import sys

import publish_online


def main() -> int:
    try:
        request = publish_online.claim(publish_online.load_config())
    except Exception as exc:
        print(f"online poll unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not request:
        print("online refresh queue empty")
        return 0
    request_id = str(request["id"])
    return subprocess.run([
        sys.executable,
        str(publish_online.ROOT / "radar_refresh.py"),
        "--request-id",
        request_id,
    ], cwd=publish_online.ROOT.parent, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
