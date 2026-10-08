#!/usr/bin/env python3
"""Send a quality-labelled recruitment digest to a Feishu custom bot."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

import jobscan


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "jobs.sqlite"
DEFAULT_CONFIG = ROOT / "config.json"
DEFAULT_SECRET = ROOT / "secrets" / "feishu.json"
DEFAULT_STATE = ROOT / "data" / "feishu_notify_state.json"
DEFAULT_SOCIAL = ROOT / "data" / "social.json"
DEFAULT_SOCIAL_CONFIG = ROOT / "intel_sources.json"
REQUIRED_KEYWORD = "具身雷达"


def validate_webhook(url: str) -> str:
    value = url.strip()
    parsed = urlsplit(value)
    prefix = "/open-apis/bot/v2/hook/"
    if parsed.scheme != "https" or parsed.hostname != "open.feishu.cn":
        raise ValueError("Webhook 必须是 https://open.feishu.cn 地址")
    if not parsed.path.startswith(prefix) or parsed.path == prefix:
        raise ValueError("Webhook 路径不是飞书自定义机器人格式")
    if parsed.query or parsed.fragment:
        raise ValueError("Webhook 不应包含查询参数或片段")
    return value


def load_webhook(path: Path) -> str:
    value = os.environ.get("FEISHU_RADAR_WEBHOOK_URL", "").strip()
    if not value:
        if not path.exists():
            raise FileNotFoundError(f"未找到私密配置：{path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("webhook_url", "") if isinstance(payload, dict) else ""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("私密配置缺少非空 webhook_url")
    return validate_webhook(value)


def load_digest_jobs(
    db_path: Path, run_date: str | None
) -> tuple[str, list[dict[str, Any]], int, bool]:
    if not db_path.exists():
        raise FileNotFoundError(f"数据库不存在：{db_path}")
    with sqlite3.connect(db_path) as connection:
        selected_date, jobs = jobscan.load_jobs(connection, run_date)
        total_jobs = len(jobs)
        dates = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT run_date FROM observations ORDER BY run_date"
            )
        ]
        index = dates.index(selected_date)
        has_previous = index > 0
        if has_previous:
            query = "SELECT job_id FROM observations WHERE run_date=?"
            current = {row[0] for row in connection.execute(query, (selected_date,))}
            previous = {row[0] for row in connection.execute(query, (dates[index - 1],))}
            jobs = [job for job in jobs if job["id"] in current - previous]
    return selected_date, jobs, total_jobs, has_previous


def rank_jobs(jobs: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for job in jobs:
        match, _ = jobscan.match_score(job, config, [])
        tier = jobscan.source_tier(job.get("source_domain", ""), config)
        priority = jobscan.job_priority(job, config, match, tier)
        ranked.append({**job, "matchScore": match, **priority})

    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return sorted(ranked, key=lambda job: (
        priority_order.get(job["priorityTier"], 9),
        -job["priorityScore"],
        -job["matchScore"],
        job.get("title", ""),
    ))


def load_social_payload(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not isinstance(payload, dict):
        return [], []
    items = [item for item in payload.get("items", []) if isinstance(item, dict) and item.get("url")]
    predictions = [item for item in payload.get("predictions", []) if isinstance(item, dict)]
    items.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("title", ""))))
    return items, predictions


def load_high_value_social(path: Path, limit: int = 3) -> list[dict[str, Any]]:
    items, _ = load_social_payload(path)
    allowed = {"招人/内推", "面试经验", "岗位能力画像", "薪酬与工作强度", "团队方向变化"}
    return [
        item for item in items
        if item.get("signalType") in allowed or int(item.get("score", 0)) >= 60
    ][:limit]


def load_notification_settings(path: Path) -> dict[str, Any]:
    defaults = {
        "timezone": "Asia/Shanghai",
        "digest_hour": 20,
        "min_digest_score": 60,
        "urgent_score": 85,
        "urgent_min_support": 2,
        "max_items": 5,
        "max_predictions": 3,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        configured = payload.get("social", {}).get("notifications", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        configured = {}
    if isinstance(configured, dict):
        defaults.update(configured)
    return defaults


def load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def select_social_notification(
    items: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    state: dict[str, Any],
    settings: dict[str, Any],
    now: dt.datetime | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], str]:
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        local_now = now.astimezone(ZoneInfo(str(settings["timezone"])))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{settings['timezone']}") from exc
    local_day = local_now.date().isoformat()
    alerted = {str(value) for value in state.get("alerted_social_ids", [])}
    urgent = [
        item for item in items
        if int(item.get("score", 0)) >= int(settings["urgent_score"])
        and int(item.get("supportCount", 0)) >= int(settings["urgent_min_support"])
        and str(item.get("id") or item.get("url")) not in alerted
    ]
    max_items = int(settings["max_items"])
    max_predictions = int(settings["max_predictions"])
    if urgent:
        topics = {str(item.get("topic", "")) for item in urgent}
        matching = [row for row in predictions if str(row.get("topic", "")) in topics]
        return "urgent", urgent[:max_items], matching[:max_predictions], local_day

    digest_due = (
        local_now.hour >= int(settings["digest_hour"])
        and state.get("last_social_digest_date") != local_day
    )
    digest_items = [
        item for item in items
        if int(item.get("score", 0)) >= int(settings["min_digest_score"])
    ][:max_items]
    if digest_due and (digest_items or predictions):
        return "digest", digest_items, predictions[:max_predictions], local_day
    return "", [], [], local_day


def build_card(
    selected_date: str,
    jobs: list[dict[str, Any]],
    total_jobs: int,
    has_previous: bool,
    config: dict[str, Any],
    limit: int = 8,
    social_items: list[dict[str, Any]] | None = None,
    predictions: list[dict[str, Any]] | None = None,
    notification_mode: str = "jobs",
) -> dict[str, Any]:
    title_by_mode = {
        "urgent": f"{REQUIRED_KEYWORD} · 重要社媒信号",
        "digest": f"{REQUIRED_KEYWORD} · 每日趋势摘要",
        "combined": f"{REQUIRED_KEYWORD} · 招聘与趋势更新",
        "test": f"{REQUIRED_KEYWORD} · 推送测试",
        "jobs": f"{REQUIRED_KEYWORD} · 招聘更新",
    }
    elements: list[dict[str, Any]] = []
    include_jobs = notification_mode in {"jobs", "combined"}
    if notification_mode == "test":
        elements.append({
            "tag": "markdown",
            "content": (
                f"**{REQUIRED_KEYWORD} · 测试消息**\n"
                "用于验证社媒评分、趋势字段和飞书链路，不代表真实行业事件。"
            ),
        })
    elif include_jobs:
        label = "新增岗位" if has_previous else "本次收录"
        elements.append({
            "tag": "markdown",
            "content": (
                f"**{REQUIRED_KEYWORD} · {selected_date}**\n"
                f"当前样本 **{total_jobs}** 个，{label} **{len(jobs)}** 个。"
            ),
        })
        ranked = rank_jobs(jobs, config)[:limit]
        if ranked:
            elements.append({"tag": "hr"})
            for job in ranked:
                title = jobscan.display_job_title(job.get("title") or "标题缺失")
                tier = jobscan.source_tier(job.get("source_domain", ""), config)
                elements.append({
                    "tag": "markdown",
                    "content": (
                        f"**[{title}]({job['url']})**\n"
                        f"{job.get('company') or '公司未解析'} · "
                        f"{job.get('location') or '地点未注明'} · "
                        f"{job.get('employment_type') or '类型未注明'} · {tier}\n"
                        f"**{job['priorityLabel']}** · 入门门槛 **{job['entryBarrier']}** · "
                        f"岗位优先分 **{job['priorityScore']}** · 匹配分 {job['matchScore']}"
                    ),
                })
        else:
            elements.append({
                "tag": "markdown",
                "content": "本次快照没有发现新增岗位，保持观察。",
            })
    else:
        label = "高优先级即时提醒" if notification_mode == "urgent" else "每日汇总"
        elements.append({
            "tag": "markdown",
            "content": f"**{REQUIRED_KEYWORD} · {label} · {selected_date}**",
        })
    social_items = social_items or []
    if social_items:
        elements.extend([
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": "**X / 小红书高价值就业线索与行业信号（待核实）**",
            },
        ])
        for item in social_items:
            platform = item.get("platform") or "社媒"
            signal_type = item.get("signalType") or "行业动态"
            title = item.get("title") or "标题缺失"
            topic = item.get("topic") or "具身智能综合"
            priority = item.get("priority") or "待评分"
            score = item.get("score", "-")
            account = (
                f"@{item['account']}" if item.get("account")
                else item.get("company") or "来源待确认"
            )
            reasons = "；".join(str(value) for value in item.get("scoreReasons", [])[:2])
            elements.append({
                "tag": "markdown",
                "content": (
                    f"**[{title}]({item['url']})**\n"
                    f"{platform} · {account} · {topic} · {signal_type}\n"
                    f"优先级 **{priority}** · 评分 **{score}/100**"
                    + (f"\n依据：{reasons}" if reasons else "")
                ),
            })
    predictions = predictions or []
    if predictions:
        elements.extend([
            {"tag": "hr"},
            {"tag": "markdown", "content": "**未来 14 天趋势观察（启发式）**"},
        ])
        for row in predictions:
            elements.append({
                "tag": "markdown",
                "content": (
                    f"**{row.get('topic') or '具身智能综合'} · "
                    f"置信度{row.get('confidence') or '低'}**\n"
                    f"{row.get('direction') or '继续观察后续信号'}\n"
                    f"证据 {row.get('evidenceCount', 0)} 条 / "
                    f"独立来源 {row.get('sourceCount', 0)} 个\n"
                    f"失效条件：{row.get('invalidation') or '缺少后续独立来源或官方证据'}"
                ),
            })
    elements.append({
        "tag": "note",
        "elements": [{
            "tag": "plain_text",
            "content": "公开网页样本，不代表全市场；社媒线索不是已核验岗位，请回到原文与公司招聘页确认。",
        }],
    })
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": title_by_mode.get(notification_mode, title_by_mode["jobs"]),
                },
            },
            "elements": elements,
        },
    }


def card_digest(card: dict[str, Any]) -> str:
    encoded = json.dumps(card, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def social_content_digest(
    items: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> str:
    stable_items = [{
        key: item.get(key)
        for key in ("id", "url", "title", "topic", "score", "priority", "supportCount")
    } for item in items]
    stable_predictions = [{
        key: row.get(key)
        for key in ("topic", "confidence", "evidenceCount", "sourceCount", "score")
    } for row in predictions]
    return card_digest({"items": stable_items, "predictions": stable_predictions})


def read_last_digest(path: Path) -> str:
    return str(load_state(path).get("last_digest", ""))


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_notification_state(
    path: Path,
    state: dict[str, Any],
    selected_date: str,
    digest: str,
    social_mode: str,
    local_day: str,
    social_items: list[dict[str, Any]],
    job_digest: str,
    social_digest: str,
    included_jobs: bool,
) -> None:
    payload = dict(state)
    payload.update({
        "last_snapshot": selected_date,
        "last_digest": digest,
        "sent_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    if included_jobs:
        payload["last_job_digest"] = job_digest
    if social_mode == "digest":
        payload["last_social_digest_date"] = local_day
        payload["last_social_digest"] = social_digest
    if social_mode == "urgent":
        alerted = [str(value) for value in payload.get("alerted_social_ids", [])]
        alerted.extend(str(item.get("id") or item.get("url")) for item in social_items)
        payload["alerted_social_ids"] = list(dict.fromkeys(alerted))[-500:]
    write_state(path, payload)


def send_card(webhook: str, card: dict[str, Any], timeout: float) -> None:
    response = requests.post(webhook, json=card, timeout=timeout)
    response.raise_for_status()
    try:
        result = response.json()
    except requests.JSONDecodeError as exc:
        raise RuntimeError("飞书返回了非 JSON 响应") from exc
    code = result.get("code", result.get("StatusCode", 0))
    if code not in (0, "0", None):
        message = result.get("msg", result.get("StatusMessage", "未知错误"))
        raise RuntimeError(f"飞书拒绝消息：code={code}, message={message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--secret", type=Path, default=DEFAULT_SECRET)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--social", type=Path, default=DEFAULT_SOCIAL)
    parser.add_argument("--social-config", type=Path, default=DEFAULT_SOCIAL_CONFIG)
    parser.add_argument("--date")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--test-card", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.limit < 1 or args.limit > 20:
        print("--limit 必须在 1 到 20 之间", file=sys.stderr)
        return 2
    try:
        config = jobscan.load_config(args.config)
        if args.test_card:
            card = build_card(
                dt.datetime.now(dt.timezone.utc).date().isoformat(),
                [],
                0,
                True,
                config,
                args.limit,
                social_items=[{
                    "id": "feishu-test",
                    "platform": "X",
                    "account": "test_only",
                    "signalType": "行业动态",
                    "topic": "VLA与策略学习",
                    "title": "【测试】具身智能 Twitter/X 推送链路",
                    "url": "https://x.com/search?q=embodied%20AI&src=typed_query&f=live",
                    "priority": "高",
                    "score": 88,
                    "scoreReasons": ["测试社媒评分字段", "测试原帖链接与待核实边界"],
                }],
                predictions=[{
                    "topic": "VLA与策略学习",
                    "confidence": "低",
                    "direction": "这是一条格式测试，不构成真实趋势判断",
                    "evidenceCount": 1,
                    "sourceCount": 1,
                    "invalidation": "测试完成后立即失效",
                }],
                notification_mode="test",
            )
            if args.dry_run:
                print(json.dumps(card, ensure_ascii=False, indent=2))
                return 0
            send_card(load_webhook(args.secret), card, args.timeout)
            print("test_card sent=true")
            return 0
        date, jobs, total, has_previous = load_digest_jobs(args.db, args.date)
        all_social, all_predictions = load_social_payload(args.social)
        settings = load_notification_settings(args.social_config)
        state = load_state(args.state)
        if args.dry_run or args.force:
            social_mode = "digest" if all_social or all_predictions else ""
            social_items = all_social[:int(settings["max_items"])]
            predictions = all_predictions[:int(settings["max_predictions"])]
            try:
                local_day = dt.datetime.now(dt.timezone.utc).astimezone(
                    ZoneInfo(str(settings["timezone"]))
                ).date().isoformat()
            except ZoneInfoNotFoundError as exc:
                raise ValueError(f"未知时区：{settings['timezone']}") from exc
        else:
            social_mode, social_items, predictions, local_day = select_social_notification(
                all_social, all_predictions, state, settings
            )
        social_digest = social_content_digest(social_items, predictions)
        if (
            not args.dry_run
            and not args.force
            and social_mode == "digest"
            and state.get("last_social_digest") == social_digest
        ):
            state["last_social_digest_date"] = local_day
            write_state(args.state, state)
            social_mode = ""
            social_items = []
            predictions = []
        job_card = build_card(date, jobs, total, has_previous, config, args.limit)
        job_digest = card_digest(job_card)
        has_job_content = not has_previous or bool(jobs)
        has_job_update = has_job_content and (
            args.dry_run or args.force or state.get("last_job_digest") != job_digest
        )
        if not args.dry_run and not args.force and not has_job_update and not social_mode:
            print(f"snapshot={date} no_actionable_updates=true")
            return 0
        notification_mode = (
            "combined" if has_job_update and social_mode
            else "jobs" if has_job_update
            else social_mode or "digest"
        )
        card = build_card(
            date,
            jobs,
            total,
            has_previous,
            config,
            args.limit,
            social_items,
            predictions,
            notification_mode,
        )
        digest = card_digest(card)
        if args.dry_run:
            print(json.dumps(card, ensure_ascii=False, indent=2))
            return 0
        if not args.force and read_last_digest(args.state) == digest:
            print(f"snapshot={date} already_sent=true")
            return 0
        send_card(load_webhook(args.secret), card, args.timeout)
        write_notification_state(
            args.state,
            state,
            date,
            digest,
            social_mode,
            local_day,
            social_items,
            job_digest,
            social_digest,
            has_job_update,
        )
        print(
            f"snapshot={date} sent=true highlighted={len(jobs)} "
            f"social={len(social_items)} predictions={len(predictions)} "
            f"mode={notification_mode}"
        )
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, requests.RequestException) as exc:
        print(f"Feishu notification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
