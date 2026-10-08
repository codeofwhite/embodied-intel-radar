#!/usr/bin/env python3
"""Collect public company-event links and social search clues."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote_plus, urlencode, urlsplit
import xml.etree.ElementTree as ET

import jobscan
import social_rank


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCES = ROOT / "intel_sources.json"
DEFAULT_EMPLOYMENT_KEYWORDS = (
    "招聘", "招人", "内推", "求职", "岗位", "职位", "校招", "实习", "面试",
    "面经", "offer", "薪资", "薪酬", "加班", "工作强度", "hiring", "referral",
    "opening", "interview", "headcount",
)
DEFAULT_EMBODIED_KEYWORDS = (
    "具身智能", "人形机器人", "机器人", "robotics", "humanoid", "robot learning",
    "vla", "模仿学习", "强化学习", "仿真", "sim2real", "real2sim", "灵巧操作",
    "运动控制", "机器人数据", "数据闭环", "3d视觉", "点云",
)
SIGNAL_TYPE_KEYWORDS = (
    ("招人/内推", ("招人", "招聘", "内推", "招募", "hiring", "referral", "opening", "校招", "实习", "hc", "headcount")),
    ("面试经验", ("面试", "面经", "interview", "offer流程", "一面", "二面")),
    ("岗位能力画像", ("岗位要求", "任职要求", "能力要求", "技能栈", "jd", "岗位画像")),
    ("薪酬与工作强度", ("薪资", "薪酬", "工资", "总包", "package", "加班", "996", "工作强度")),
    ("团队方向变化", ("团队", "组里", "方向调整", "扩招", "缩招", "裁员", "headcount")),
)

EVENT_AREA_KEYWORDS = (
    ("兼容性", ("breaking", "deprecat", "migration", "compatib")),
    ("数据与采集", ("dataset", "record", "camera", "teleop", "data collection")),
    ("训练与策略", ("train", "policy", "finetun", "optimizer", "reinforcement")),
    ("模型与检查点", ("checkpoint", "model", "weight", "vla", "groot")),
    ("ROS2 与硬件", ("ros2", "unitree", "g1", "h1", "go2")),
    ("安装与依赖", ("install", "dependency", "dependencies", "package", "python")),
    ("文档与示例", ("document", "docs", "example", "tutorial")),
)
PROJECT_NAMES = {
    "Isaac-GR00T": "Isaac GR00T",
    "lerobot": "LeRobot",
    "openpi": "OpenPI",
    "unitree_ros2": "Unitree ROS2",
}


def friendly_project(repo: str) -> str:
    slug = repo.rsplit("/", 1)[-1]
    return PROJECT_NAMES.get(slug, slug)


def clean_release_line(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", value)
    value = value.replace("`", "")
    value = value.replace("**", "").replace("__", "").replace("~~", "")
    return jobscan.clean_text(value).strip()


def release_key_changes(body: str, limit: int = 3) -> list[str]:
    changes: list[str] = []
    ignored = ("what's changed", "what is changed", "full changelog", "new contributors", "contributors")
    for raw_line in body.splitlines():
        if not re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", raw_line):
            continue
        cleaned = clean_release_line(raw_line)
        lowered = cleaned.lower()
        if not cleaned or lowered.startswith(ignored) or cleaned.startswith("@"):
            continue
        cleaned = cleaned[:157].rstrip() + "…" if len(cleaned) > 160 else cleaned
        if cleaned not in changes:
            changes.append(cleaned)
        if len(changes) >= limit:
            break
    return changes


def first_sentence(value: str, limit: int = 180) -> str:
    cleaned = clean_release_line(value)
    if not cleaned:
        return ""
    sentence = re.split(r"(?<=[.!?。！？])\s+", cleaned, maxsplit=1)[0]
    return sentence[: limit - 1].rstrip() + "…" if len(sentence) > limit else sentence


def event_details(item: dict[str, Any]) -> dict[str, Any]:
    domain = str(item.get("domain", ""))
    company = str(item.get("company") or "来源机构")
    project = str(item.get("project") or (item.get("title") if domain == "github.com" else "研究论文" if domain == "arxiv.org" else company))
    version = str(item.get("version") or "")
    text = " ".join((str(item.get("title", "")), str(item.get("excerpt", "")), project)).lower()
    if domain == "github.com" and version:
        event_type = "开源版本"
        what_happened = f"{company} 发布 {project} {version}。"
    elif domain == "github.com":
        event_type = "开源项目"
        owner = "" if company == "来源机构" else f"{company} "
        what_happened = f"发现 {owner}{project} 的公开项目页面。"
    elif domain == "arxiv.org":
        event_type = "研究论文"
        what_happened = f"发布研究论文《{item.get('title', '标题待确认')}》。"
    elif any(keyword in text for keyword in ("融资", "funding", "investment")):
        event_type = "融资动态"
        what_happened = first_sentence(str(item.get("excerpt") or item.get("title")))
    else:
        event_type = "公司动态"
        what_happened = first_sentence(str(item.get("excerpt") or item.get("title")))

    affected_areas = [
        label for label, keywords in EVENT_AREA_KEYWORDS
        if any(keyword in text for keyword in keywords)
    ][:4]
    if not affected_areas:
        affected_areas = ["论文方法"] if domain == "arxiv.org" else ["综合动态"]

    project_key = project.lower()
    if "lerobot" in project_key:
        why_it_matters = "与你的机器人数据采集、策略训练和开源基线复现链路直接相关。"
    elif "groot" in project_key:
        why_it_matters = "与 VLA 模型、检查点以及推理和微调链路相关。"
    elif "openpi" in project_key:
        why_it_matters = "与 OpenPI 的训练、推理、评测和依赖兼容性相关。"
    elif "unitree" in project_key:
        why_it_matters = "与宇树机器人 ROS2 接口、真机通信和示例工程相关。"
    elif domain == "arxiv.org":
        why_it_matters = "可作为方法和相关工作线索，但论文发布本身不代表代码可复现或真机有效。"
    else:
        why_it_matters = "这是具身智能生态动态；是否与你当前方向相关仍需结合原文判断。"

    if "兼容性" in affected_areas:
        suggested_action = "升级前先核对破坏性变更、依赖版本，以及已有数据和模型是否兼容。"
    elif domain == "github.com":
        suggested_action = "正在使用该项目时，先打开 Release 核对相关模块；未使用则收藏观察即可。"
    elif domain == "arxiv.org":
        suggested_action = "先核对任务、数据和真机评测是否匹配你的方向，再决定是否精读。"

    else:
        suggested_action = "打开原始来源核对具体事实，再决定是否跟进。"

    key_changes = item.get("keyChanges")
    if not isinstance(key_changes, list) or not key_changes:
        excerpt_point = first_sentence(str(item.get("excerpt", "")))
        key_changes = [excerpt_point] if excerpt_point else ["原文摘要不足，请打开来源核对。"]
    return {
        **item,
        "eventType": event_type,
        "project": project,
        "version": version,
        "whatHappened": what_happened,
        "keyChanges": key_changes[:3],
        "affectedAreas": affected_areas,
        "whyItMatters": why_it_matters,
        "suggestedAction": suggested_action,
        "interpretation": "来源事实与规则提炼分开展示；具体变更仍以原文为准。",
    }



def source_tier(kind: str, domain: str) -> str:
    if kind == "social":
        return "社媒搜索线索"
    if domain == "arxiv.org":
        return "研究发布"
    if domain == "github.com":
        return "开源发布"
    return "公司官方"


def platform_for_url(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host == "x.com" or host.endswith(".x.com") or host == "twitter.com" or host.endswith(".twitter.com"):
        return "X"
    if host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com") or host == "xhslink.com" or host.endswith(".xhslink.com"):
        return "小红书"
    return "其他"


def signal_type(text: str) -> str:
    lowered = text.lower()
    for label, keywords in SIGNAL_TYPE_KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return label
    return "普通观点/传闻"


def social_relevant(item: dict[str, str], section: dict[str, Any]) -> bool:
    """Require embodied context plus a career, trend, or watched-account signal."""
    relevance = section.get("relevance", {})
    employment = relevance.get("employment_keywords", DEFAULT_EMPLOYMENT_KEYWORDS)
    embodied = relevance.get("embodied_keywords", DEFAULT_EMBODIED_KEYWORDS)
    trend = relevance.get("trend_keywords", ())
    text = " ".join((item.get("title", ""), item.get("description", ""), item.get("url", ""))).lower()
    account = social_rank.account_for_url(item.get("url", ""))
    watched = {str(value).lower().lstrip("@") for value in section.get("watched_accounts", [])}
    return (
        any(str(keyword).lower() in text for keyword in employment)
        or any(str(keyword).lower() in text for keyword in trend)
        or bool(account and account in watched)
    ) and (
        any(str(keyword).lower() in text for keyword in embodied)
    )


def company_from_text(text: str, companies: list[dict[str, Any]]) -> str:
    lowered = text.lower()
    for company in companies:
        names = [company.get("name", ""), *company.get("aliases", [])]
        if any(name and str(name).lower() in lowered for name in names):
            return str(company.get("name", ""))
    return ""


def build_search_shortcuts(section: dict[str, Any]) -> list[dict[str, str]]:
    shortcuts: list[dict[str, str]] = []
    for index, item in enumerate(section.get("search_shortcuts", [])):
        platform = str(item.get("platform", ""))
        query = str(item.get("query", "")).strip()
        if not query or platform not in {"X", "小红书"}:
            continue
        if platform == "X":
            url = f"https://x.com/search?q={quote_plus(query)}&src=typed_query&f=live"
        else:
            url = f"https://www.xiaohongshu.com/search_result?keyword={quote_plus(query)}"
        shortcuts.append({
            "id": f"{platform.lower()}-{index}",
            "platform": platform,
            "label": str(item.get("label") or query),
            "query": query,
            "url": url,
        })
    return shortcuts


def indexed_candidates(
    kind: str,
    config: dict[str, Any],
    discover: Any = jobscan.discover_bing_rss,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    section = config[kind]
    fetcher = jobscan.Fetcher(config)
    allowed = section["allowed_domains"]
    candidates: dict[str, dict[str, str]] = {}
    health: list[dict[str, Any]] = []
    queries = list(section["queries"])
    if kind == "social":
        account_terms = section.get("account_query_terms", "robotics OR humanoid OR VLA")
        queries.extend(
            f"site:x.com/{str(account).lstrip('@')} {account_terms}"
            for account in section.get("watched_accounts", [])
        )
    for query in dict.fromkeys(queries):
        try:
            found = discover(
                fetcher, query, config["request"]["max_results_per_query"]
            )
            accepted = [item for item in found if jobscan.domain_allowed(item["url"], allowed)]
            if kind == "social":
                accepted = [item for item in accepted if social_relevant(item, section)]
            for item in accepted:
                candidates.setdefault(jobscan.canonical_url(item["url"]), item)
            health.append({
                "query": query,
                "status": "ok",
                "discovered": len(found),
                "accepted": len(accepted),
            })
        except Exception as exc:
            health.append({
                "query": query,
                "status": "error",
                "discovered": 0,
                "accepted": 0,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return list(candidates.values())[: section["max_items"]], health


def verify_event(
    item: dict[str, str], fetcher: jobscan.Fetcher
) -> tuple[str, str, str]:
    response = fetcher.get(item["url"])
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type and "text" not in content_type:
        raise ValueError(f"unsupported content-type {content_type}")
    parser = jobscan.VisibleTextParser()
    parser.feed(response.text)
    title = (
        parser.meta.get("og:title")
        or " ".join(parser.title_parts)
        or item["title"]
    )
    excerpt = (
        parser.meta.get("description")
        or parser.meta.get("og:description")
        or item["description"]
    )
    return response.url, jobscan.clean_text(title)[:240], jobscan.clean_text(excerpt)[:500]


def structured_events(
    config: dict[str, Any], fetcher: jobscan.Fetcher, now: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    section = config.get("events", {}).get("structured_sources", {})
    items: list[dict[str, Any]] = []
    health: list[dict[str, Any]] = []
    for source in section.get("github_releases", []):
        repo = source["repo"]
        try:
            response = fetcher.get(
                f"https://api.github.com/repos/{repo}/releases?per_page={source.get('limit', 4)}",
                check_robots=False,
            )
            releases = response.json()
            if not isinstance(releases, list):
                raise ValueError("GitHub releases response is not a list")
            for release in releases[: source.get("limit", 4)]:
                url = release.get("html_url")
                if not url:
                    continue
                canonical = jobscan.canonical_url(url)
                raw_body = str(release.get("body") or "")
                project = friendly_project(repo)
                version = jobscan.clean_text(release.get("tag_name") or "")
                release_title = jobscan.clean_text(release.get("name") or version or repo)[:240]
                items.append({
                    "id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
                    "title": f"{project}{f' {version}' if version else ''}",
                    "releaseTitle": release_title,
                    "excerpt": jobscan.clean_text(raw_body or f"{repo} 发布新版本")[:500],
                    "keyChanges": release_key_changes(raw_body),
                    "repo": repo,
                    "project": project,
                    "version": version,
                    "url": canonical,
                    "domain": "github.com",
                    "company": source.get("company", repo.split("/")[0]),
                    "sourceTier": "开源发布",
                    "verification": "structured_api",
                    "publishedAt": release.get("published_at") or release.get("created_at"),
                    "discoveredAt": now,
                })
            health.append({"source": f"github:{repo}", "status": "ok", "accepted": len(releases[: source.get("limit", 4)])})
        except Exception as exc:
            health.append({"source": f"github:{repo}", "status": "error", "accepted": 0, "error": f"{type(exc).__name__}: {exc}"})

    for source in section.get("arxiv", []):
        try:
            params = urlencode({
                "search_query": source["query"],
                "start": 0,
                "max_results": source.get("limit", 8),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            })
            response = fetcher.get(f"https://export.arxiv.org/api/query?{params}", check_robots=False)
            root = ET.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            for entry in entries:
                url = jobscan.clean_text(entry.findtext("atom:id", default="", namespaces=ns))
                if not url:
                    continue
                canonical = jobscan.canonical_url(url)
                items.append({
                    "id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
                    "title": jobscan.clean_text(entry.findtext("atom:title", default="", namespaces=ns))[:240],
                    "excerpt": jobscan.clean_text(entry.findtext("atom:summary", default="", namespaces=ns))[:500],
                    "url": canonical,
                    "domain": "arxiv.org",
                    "company": "学术研究",
                    "sourceTier": "研究发布",
                    "verification": "structured_api",
                    "publishedAt": entry.findtext("atom:published", default="", namespaces=ns),
                    "discoveredAt": now,
                })
            health.append({"source": "arxiv", "status": "ok", "accepted": len(entries)})
        except Exception as exc:
            health.append({"source": "arxiv", "status": "error", "accepted": 0, "error": f"{type(exc).__name__}: {exc}"})
    return items, health


def scan(
    kind: str,
    sources_path: Path,
    output_path: Path,
    history_path: Path | None = None,
) -> dict[str, Any]:
    config = jobscan.load_config(sources_path)
    section = config[kind]
    candidates, health = indexed_candidates(kind, config)
    fetcher = jobscan.Fetcher(config)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    companies = jobscan.load_company_registry(sources_path, config) if kind == "social" else []
    items: list[dict[str, Any]] = []
    verify_failures = 0
    for candidate in candidates:
        url = candidate["url"]
        title = candidate["title"]
        excerpt = candidate["description"]
        verification = "search_index_only"
        if section.get("verify_target_pages"):
            try:
                url, title, excerpt = verify_event(candidate, fetcher)
                verification = "target_page_fetched"
            except Exception:
                verify_failures += 1
                continue
        domain = (urlsplit(url).hostname or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        canonical = jobscan.canonical_url(url)
        item: dict[str, Any] = {
            "id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24],
            "title": title or "标题缺失",
            "excerpt": excerpt,
            "url": canonical,
            "domain": domain,
            "sourceTier": source_tier(kind, domain),
            "verification": verification,
            "discoveredAt": now,
        }
        if kind == "social":
            combined = " ".join((title, excerpt))
            item.update({
                "platform": platform_for_url(canonical),
                "signalType": signal_type(combined),
                "company": company_from_text(combined, companies),
                "role": "",
                "confidence": "搜索索引线索·待核实",
                "freshness": "发布时间待原文确认",
            })
        items.append(item)
    if kind == "events":
        structured, structured_health = structured_events(config, fetcher, now)
        health.extend(structured_health)
        merged = {item["id"]: item for item in items}
        for item in structured:
            merged[item["id"]] = item
        items = sorted(
            merged.values(),
            key=lambda item: item.get("publishedAt") or item.get("discoveredAt") or "",
            reverse=True,
        )[: section["max_items"]]
        items = [event_details(item) for item in items]
    predictions: list[dict[str, Any]] = []
    history: dict[str, Any] = {"items": []}
    if kind == "social":
        if history_path is not None:
            history = social_rank.load_history(history_path)
        items = social_rank.score_items(items, history.get("items", []), section)
        predictions = social_rank.build_predictions(items)

    payload: dict[str, Any] = {
        "meta": {
            "kind": kind,
            "generatedAt": now,
            "itemCount": len(items),
            "candidateCount": len(candidates),
            "verificationFailures": verify_failures,
            "notice": section.get(
                "notice",
                "公开搜索发现并成功访问的来源页面；仍需打开原文核对具体事实。",
            ),
            "sourceHealth": health,
        },
        "items": items,
    }
    if kind == "social":
        payload["searchShortcuts"] = build_search_shortcuts(section)
        payload["predictions"] = predictions
        payload["meta"].update({
            "highPriorityCount": sum(item.get("priority") == "高" for item in items),
            "predictionCount": len(predictions),
            "predictionNotice": "启发式趋势判断；保留证据数、置信度与失效条件，不是精确概率。",
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if kind == "social" and history_path is not None:
        social_rank.write_history(
            history_path,
            social_rank.merge_history(history.get("items", []), items, now),
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("events", "social"))
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--history", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    default_output = ROOT / "data" / f"{args.kind}.json"
    if args.dry_run:
        config = jobscan.load_config(args.sources)
        section = config[args.kind]
        print(json.dumps({
            "kind": args.kind,
            "queries": len(section["queries"]),
            "allowed_domains": section["allowed_domains"],
            "target_fetch": section.get("verify_target_pages", False),
            "search_shortcuts": len(section.get("search_shortcuts", [])),
        }, ensure_ascii=False, indent=2))
        return 0
    try:
        history_path = args.history
        if args.kind == "social" and history_path is None:
            history_path = ROOT / "data" / "raw" / "social_history.json"
        payload = scan(args.kind, args.sources, args.output or default_output, history_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"{args.kind} scan failed: {exc}", file=sys.stderr)
        return 2
    meta = payload["meta"]
    print(
        f"kind={args.kind} candidates={meta['candidateCount']} "
        f"items={meta['itemCount']} verify_failures={meta['verificationFailures']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
