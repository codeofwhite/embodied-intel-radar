#!/usr/bin/env python3
"""Rank public social clues and build auditable short-horizon forecasts."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


DEFAULT_TOPICS = (
    ("招聘与团队", ("招聘", "招人", "内推", "hiring", "referral", "headcount", "扩招")),
    ("VLA与策略学习", ("vla", "robot learning", "模仿学习", "强化学习", "policy", "post-training")),
    ("仿真与机器人数据", ("仿真", "simulation", "sim2real", "real2sim", "机器人数据", "dataset", "合成数据")),
    ("人形与运动控制", ("人形", "humanoid", "运动控制", "locomotion", "whole-body", "全身控制")),
    ("灵巧操作", ("灵巧", "dexterous", "manipulation", "抓取", "grasp")),
    ("开源、论文与产品", ("开源", "open source", "release", "发布", "论文", "paper", "benchmark", "demo")),
)


def _text(item: dict[str, Any]) -> str:
    return " ".join(str(item.get(key, "")) for key in ("title", "excerpt", "url")).lower()


def _matches(text: str, keywords: list[str] | tuple[str, ...]) -> list[str]:
    return [str(keyword) for keyword in keywords if str(keyword).lower() in text]


def account_for_url(url: str) -> str:
    split = urlsplit(url)
    if (split.hostname or "").lower().removeprefix("www.") not in {"x.com", "twitter.com"}:
        return ""
    parts = [part for part in split.path.split("/") if part]
    if not parts or parts[0].lower() in {"i", "search", "intent", "share"}:
        return ""
    return parts[0].lstrip("@").lower()


def classify_topic(item: dict[str, Any], section: dict[str, Any]) -> str:
    text = _text(item)
    configured = section.get("topics", [])
    rules = [
        (str(rule.get("label", "")), tuple(str(word) for word in rule.get("keywords", [])))
        for rule in configured
        if rule.get("label") and rule.get("keywords")
    ] or list(DEFAULT_TOPICS)
    best_label = "具身智能综合"
    best_count = 0
    for label, keywords in rules:
        count = len(_matches(text, keywords))
        if count > best_count:
            best_label = label
            best_count = count
    return best_label


def score_items(
    items: list[dict[str, Any]],
    previous_items: list[dict[str, Any]],
    section: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach a transparent relevance score; do not invent engagement metrics."""
    previous_ids = {
        str(item.get("id") or item.get("url")) for item in previous_items
        if item.get("id") or item.get("url")
    }
    relevance = section.get("relevance", {})
    embodied_keywords = [str(value) for value in relevance.get("embodied_keywords", [])]
    career_keywords = [str(value) for value in relevance.get("employment_keywords", [])]
    trend_keywords = [str(value) for value in relevance.get("trend_keywords", [])]
    watched = {str(value).lower().lstrip("@") for value in section.get("watched_accounts", [])}

    enriched: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        text = _text(item)
        embodied = _matches(text, embodied_keywords)
        career = _matches(text, career_keywords)
        trend = _matches(text, trend_keywords)
        account = account_for_url(str(item.get("url", "")))
        is_watched = bool(account and account in watched)
        is_new = str(item.get("id") or item.get("url")) not in previous_ids

        score = 35
        reasons = ["包含具身智能方向关键词"]
        score += min(25, len(embodied) * 5)
        if career:
            score += min(12, len(career) * 4)
            reasons.append("包含招聘或职业信号")
        if trend:
            score += min(12, len(trend) * 3)
            reasons.append("包含发布、论文或趋势信号")
        if is_watched:
            score += 12
            reasons.append("来自精选观察账号")
        if is_new:
            score += 8
            reasons.append("相对历史记录为新线索")
        if item.get("verification") == "target_page_fetched":
            score += 8
            reasons.append("已读取公开原始页面")
        elif item.get("verification") == "search_index_only":
            reasons.append("目前仅有公开搜索摘要，原文待核实")

        item.update({
            "account": account,
            "topic": classify_topic(item, section),
            "score": max(0, min(100, score)),
            "priority": "高" if score >= 80 else "中" if score >= 60 else "低",
            "scoreReasons": reasons,
            "forecastStatus": "规则评分·待后续证据验证",
        })
        enriched.append(item)

    topic_accounts: dict[str, set[str]] = {}
    for item in enriched:
        identity = item.get("account") or item.get("domain") or item.get("url")
        topic_accounts.setdefault(str(item["topic"]), set()).add(str(identity))
    for item in enriched:
        item["supportCount"] = len(topic_accounts[str(item["topic"])])
    return sorted(enriched, key=lambda item: (-int(item["score"]), str(item.get("title", ""))))


def build_predictions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("topic") or "具身智能综合"), []).append(item)
    predictions: list[dict[str, Any]] = []
    for topic, evidence in grouped.items():
        identities = {
            str(item.get("account") or item.get("domain") or item.get("url"))
            for item in evidence
        }
        source_count = len(identities)
        confidence = "高" if source_count >= 3 else "中" if source_count >= 2 else "低"
        predictions.append({
            "topic": topic,
            "horizonDays": 14,
            "direction": f"{topic}在未来 14 天可能继续出现值得跟踪的新信号",
            "confidence": confidence,
            "evidenceCount": len(evidence),
            "sourceCount": source_count,
            "topEvidenceIds": [str(item.get("id", "")) for item in evidence[:3]],
            "invalidation": "未来 14 天没有第二个独立来源或官方原始证据时，应降低或撤销该判断",
            "status": "启发式趋势判断，不是已发生事实或精确概率",
            "score": round(sum(int(item.get("score", 0)) for item in evidence) / len(evidence), 1),
        })
    confidence_rank = {"高": 0, "中": 1, "低": 2}
    return sorted(
        predictions,
        key=lambda row: (confidence_rank[row["confidence"]], -row["sourceCount"], -row["score"], row["topic"]),
    )


def load_history(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"updatedAt": "", "items": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return {"updatedAt": "", "items": []}
    return payload


def merge_history(
    previous_items: list[dict[str, Any]],
    current_items: list[dict[str, Any]],
    now: str,
    max_items: int = 2000,
) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in previous_items:
        key = str(raw.get("id") or raw.get("url") or "")
        if key:
            merged[key] = dict(raw)
    for raw in current_items:
        key = str(raw.get("id") or raw.get("url") or "")
        if not key:
            continue
        old = merged.get(key, {})
        merged[key] = {
            "id": raw.get("id", old.get("id", "")),
            "url": raw.get("url", old.get("url", "")),
            "title": raw.get("title", old.get("title", "")),
            "platform": raw.get("platform", old.get("platform", "")),
            "account": raw.get("account", old.get("account", "")),
            "topic": raw.get("topic", old.get("topic", "")),
            "score": raw.get("score", old.get("score", 0)),
            "firstSeenAt": old.get("firstSeenAt") or now,
            "lastSeenAt": now,
            "seenCount": int(old.get("seenCount", 0)) + 1,
        }
    ordered = sorted(
        merged.values(), key=lambda item: str(item.get("lastSeenAt", "")), reverse=True
    )[:max_items]
    return {"updatedAt": now, "items": ordered}


def write_history(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
