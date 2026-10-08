#!/usr/bin/env python3
"""Collect traceable end-of-day quotes for the embodied-intelligence watchlist."""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data" / "quotes.json"
SECRET_PATH = ROOT / "secrets" / "market.json"
API_URL = "https://www.alphavantage.co/query"
DAILY_LIMIT = 25
WATCHLIST = [
    {"name": "宇树科技", "symbol": "688836.SH", "providerSymbol": "688836.SHH", "tier": "核心业务", "currency": "CNY"},
    {"name": "埃斯顿", "symbol": "002747.SZ", "providerSymbol": "002747.SHZ", "tier": "核心业务", "currency": "CNY"},
    {"name": "机器人", "symbol": "300024.SZ", "providerSymbol": "300024.SHZ", "tier": "核心业务", "currency": "CNY"},
    {"name": "绿的谐波", "symbol": "688017.SH", "providerSymbol": "688017.SHH", "tier": "产业链", "currency": "CNY"},
    {"name": "拓普集团", "symbol": "601689.SH", "providerSymbol": "601689.SHH", "tier": "产业链", "currency": "CNY"},
    {"name": "鸣志电器", "symbol": "603728.SH", "providerSymbol": "603728.SHH", "tier": "产业链", "currency": "CNY"},
    {"name": "汇川技术", "symbol": "300124.SZ", "providerSymbol": "300124.SHZ", "tier": "产业链", "currency": "CNY"},
    {"name": "奥比中光", "symbol": "688322.SH", "providerSymbol": "688322.SHH", "tier": "产业链", "currency": "CNY"},
    {"name": "三花智控", "symbol": "002050.SZ", "providerSymbol": "002050.SHZ", "tier": "产业链", "currency": "CNY"},
    {"name": "双环传动", "symbol": "002472.SZ", "providerSymbol": "002472.SHZ", "tier": "产业链", "currency": "CNY"},
    {"name": "兆威机电", "symbol": "003021.SZ", "providerSymbol": "003021.SHZ", "tier": "产业链", "currency": "CNY"},
    {"name": "雷赛智能", "symbol": "002979.SZ", "providerSymbol": "002979.SHZ", "tier": "产业链", "currency": "CNY"},
    {"name": "柯力传感", "symbol": "603662.SH", "providerSymbol": "603662.SHH", "tier": "产业链", "currency": "CNY"},
    {"name": "NVIDIA", "symbol": "NVDA", "providerSymbol": "NVDA", "tier": "大厂敞口", "currency": "USD"},
    {"name": "Tesla", "symbol": "TSLA", "providerSymbol": "TSLA", "tier": "大厂敞口", "currency": "USD"},
    {"name": "Alphabet", "symbol": "GOOGL", "providerSymbol": "GOOGL", "tier": "大厂敞口", "currency": "USD"},
]


def has_dated_history(item: dict[str, Any]) -> bool:
    series = item.get("series")
    return (
        isinstance(series, list)
        and len(series) >= 2
        and all(
            isinstance(point, dict)
            and isinstance(point.get("date"), str)
            and isinstance(point.get("close"), (int, float))
            for point in series
        )
    )



def safe_error(exc: Exception, api_key: str) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return message[:260]

def load_api_key() -> str:
    if os.environ.get("ALPHA_VANTAGE_API_KEY"):
        return os.environ["ALPHA_VANTAGE_API_KEY"].strip()
    try:
        return str(json.loads(SECRET_PATH.read_text(encoding="utf-8"))["api_key"]).strip()
    except (OSError, KeyError, ValueError, TypeError):
        return ""


def cached_today(path: Path, today: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    items = payload.get("items", [])
    symbols = {item.get("symbol") for item in items}
    expected = {item["symbol"] for item in WATCHLIST}
    history_ready = {
        item.get("symbol") for item in items if has_dated_history(item)
    }
    if (
        payload.get("meta", {}).get("generatedDate") == today
        and expected <= symbols
        and expected <= history_ready
    ):
        return payload
    return None


def load_previous(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def parse_series(entry: dict[str, str], payload: dict[str, Any], observed_at: str) -> dict[str, Any]:
    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict) or not series:
        detail = payload.get("Information") or payload.get("Note") or payload.get("Error Message") or "daily series missing"
        raise ValueError(str(detail))
    ordered = sorted(series.items(), reverse=True)
    latest_date, latest = ordered[0]
    history = [
        {"date": date, "close": round(float(values["4. close"]), 4)}
        for date, values in reversed(ordered[:100])
    ]
    closes = [point["close"] for point in history[-10:]]
    price = closes[-1]
    previous = closes[-2] if len(closes) > 1 else price
    change = ((price - previous) / previous * 100) if previous else 0.0
    return {
        **entry,
        "price": round(price, 4),
        "previousClose": round(previous, 4),
        "changePercent": round(change, 4),
        "marketDate": latest_date,
        "observedAt": observed_at,
        "seriesInterval": "1d",
        "series": history,
        "points": closes,
        "status": "ok",
        "sourceUrl": "https://www.alphavantage.co/documentation/",
    }


def collect(api_key: str, output: Path, delay_seconds: float = 13.0, force: bool = False) -> tuple[dict[str, Any], int]:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    if not force:
        cached = cached_today(output, today)
        if cached:
            return cached, 0
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if not api_key:
        payload = {
            "meta": {
                "provider": "Alpha Vantage",
                "status": "unconfigured",
                "schemaVersion": 3,
                "generatedAt": now,
                "generatedDate": today,
                "notice": "行情 API Key 未配置；没有使用演示价格。",
            },
            "items": [],
            "errors": [],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload, 1
    session = requests.Session()
    session.headers["User-Agent"] = "EmbodiedIntelRadar/0.3 (personal research)"
    previous_payload = load_previous(output)
    previous_meta = previous_payload.get("meta", {})
    previous_items = {
        item.get("symbol"): item for item in previous_payload.get("items", []) if item.get("symbol")
    }
    same_day = previous_meta.get("generatedDate") == today
    previous_requests = int(previous_meta.get("requestsToday", previous_meta.get("requestedCount", 0))) if same_day else 0
    requests_today = min(previous_requests, DAILY_LIMIT)
    requests_this_run = 0
    cached_count = 0
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for entry in WATCHLIST:
        previous = previous_items.get(entry["symbol"])
        if same_day and previous and previous.get("status") == "ok" and has_dated_history(previous):
            items.append({**previous, **entry})
            cached_count += 1
            continue
        if requests_today >= DAILY_LIMIT:
            if previous:
                items.append({**previous, **entry, "status": "stale"})
            errors.append({"symbol": entry["symbol"], "error": "当日 API 请求配额保护：未发起新请求"})
            continue
        if requests_this_run:
            time.sleep(delay_seconds)
        requests_today += 1
        requests_this_run += 1
        try:
            response = session.get(API_URL, params={
                "function": "TIME_SERIES_DAILY",
                "symbol": entry["providerSymbol"],
                "outputsize": "compact",
                "apikey": api_key,
            }, timeout=25)
            response.raise_for_status()
            items.append(parse_series(entry, response.json(), now))
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            if previous:
                items.append({**previous, **entry, "status": "stale"})
            errors.append({"symbol": entry["symbol"], "error": safe_error(exc, api_key)})
    status = "ok" if len(items) == len(WATCHLIST) and all(item.get("status") == "ok" for item in items) else ("degraded" if items else "failed")
    payload = {
        "meta": {
            "provider": "Alpha Vantage",
            "status": status,
            "schemaVersion": 3,
            "generatedAt": now,
            "generatedDate": today,
            "itemCount": len(items),
            "requestedCount": len(WATCHLIST),
            "watchlistVersion": 2,
            "apiRequestsThisRun": requests_this_run,
            "requestsToday": requests_today,
            "dailyLimit": DAILY_LIMIT,
            "cachedCount": cached_count,
            "historyReadyCount": sum(has_dated_history(item) for item in items),
            "notice": "Alpha Vantage 真实日线收盘数据；按标的每日缓存，不是盘中实时交易报价。",
        },
        "items": items,
        "errors": errors,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload, 0 if items else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=13.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--configure-key", action="store_true")
    args = parser.parse_args()
    if args.configure_key:
        value = getpass.getpass("Alpha Vantage API Key: ").strip()
        if not value:
            print("empty key rejected", file=sys.stderr)
            return 2
        SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
        SECRET_PATH.write_text(json.dumps({"api_key": value}) + "\n", encoding="utf-8")
        SECRET_PATH.chmod(0o600)
        print(f"configured={SECRET_PATH}")
        return 0
    if args.dry_run:
        print(json.dumps({"provider": "Alpha Vantage", "symbols": len(WATCHLIST), "keyConfigured": bool(load_api_key())}))
        return 0
    payload, code = collect(load_api_key(), args.output, args.delay_seconds, args.force)
    print(f"provider=AlphaVantage status={payload['meta']['status']} items={len(payload['items'])} errors={len(payload['errors'])}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
