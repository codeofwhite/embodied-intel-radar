#!/usr/bin/env python3
"""Low-rate public-page job market scanner for career decisions.

The collector stores normalized facts and source URLs. It does not bypass login,
CAPTCHA, robots.txt, or other access controls. Competition is reported as either
observed market evidence or a clearly labelled entry-pressure proxy.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sqlite3
import statistics
import sys
import time
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

import requests


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "jobs.sqlite"
CAREER_LINKS_PATH = ROOT / "data" / "career_links.json"
JOB_HINTS = ("招聘", "校招", "实习", "工程师", "研究员", "职位", "job", "career")


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.jsonld: list[str] = []
        self.in_jsonld = False
        self.jsonld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            if tag == "script" and "ld+json" in values.get("type", "").lower():
                self.in_jsonld = True
                self.jsonld_parts = []
            else:
                self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key and values.get("content"):
                self.meta[key.lower()] = values["content"]

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_jsonld:
            self.jsonld.append("".join(self.jsonld_parts))
            self.in_jsonld = False
            self.jsonld_parts = []
        elif tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_jsonld:
            self.jsonld_parts.append(data)
        elif not self.skip:
            cleaned = " ".join(data.split())
            if cleaned:
                self.parts.append(cleaned)
                if self.in_title:
                    self.title_parts.append(cleaned)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_company_registry(config_path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    registry = Path(config.get("company_registry", "company_registry.json"))
    if not registry.is_absolute():
        registry = config_path.parent / registry
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload.get("companies", []) if isinstance(payload, dict) else []


def canonical_url(url: str) -> str:
    split = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(split.query) if k.lower() not in {
        "utm_source", "utm_medium", "utm_campaign", "from", "source", "ref"
    }]
    path = re.sub(r"/{2,}", "/", split.path).rstrip("/") or "/"
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, urlencode(kept), ""))


def domain_allowed(url: str, allowed: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == item or host.endswith("." + item) for item in allowed)


def flatten_jsonld(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        out: list[dict[str, Any]] = []
        for item in value:
            out.extend(flatten_jsonld(item))
        return out
    if not isinstance(value, dict):
        return []
    out = [value]
    if "@graph" in value:
        out.extend(flatten_jsonld(value["@graph"]))
    return out


def first_jobposting(parser: VisibleTextParser) -> dict[str, Any] | None:
    for block in parser.jsonld:
        try:
            parsed = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in flatten_jsonld(parsed):
            kind = item.get("@type", "")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(str(x).lower() == "jobposting" for x in kinds):
                return item
    return None


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return " ".join(html.unescape(text).split())


def nested_name(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("name", ""))
    return clean_text(value)


def parse_location(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(filter(None, (parse_location(x) for x in value)))
    if not isinstance(value, dict):
        return clean_text(value)
    addr = value.get("address", value)
    if isinstance(addr, dict):
        fields = [addr.get("addressRegion"), addr.get("addressLocality"), addr.get("streetAddress")]
        return " ".join(clean_text(x) for x in fields if x)
    return clean_text(addr)


def normalize_salary(text: str, base_salary: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "salary_min_monthly": None,
        "salary_max_monthly": None,
        "salary_months": None,
        "salary_daily": None,
        "salary_raw": "",
    }
    if isinstance(base_salary, dict):
        value = base_salary.get("value", base_salary)
        if isinstance(value, dict):
            low = value.get("minValue") or value.get("value")
            high = value.get("maxValue") or value.get("value")
            unit = clean_text(value.get("unitText") or base_salary.get("unitText")).upper()
            try:
                low_f, high_f = float(low), float(high)
                if unit in {"MONTH", "MONTHLY"}:
                    result.update(salary_min_monthly=low_f, salary_max_monthly=high_f,
                                  salary_raw=f"{low_f:g}-{high_f:g}/月")
                    return result
                if unit in {"YEAR", "YEARLY"}:
                    result.update(salary_min_monthly=low_f / 12, salary_max_monthly=high_f / 12,
                                  salary_raw=f"{low_f:g}-{high_f:g}/年")
                    return result
                if unit in {"DAY", "DAILY"}:
                    result.update(salary_daily=low_f if low_f == high_f else (low_f + high_f) / 2,
                                  salary_raw=f"{low_f:g}-{high_f:g}/天")
                    return result
            except (TypeError, ValueError):
                pass

    patterns = [
        (r"(\d+(?:\.\d+)?)\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*[kK]\s*(?:[·x×*]\s*(\d{2})\s*薪)?", 1000),
        (r"(\d+(?:\.\d+)?)\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*千\s*(?:元)?(?:/月|每月|月薪)?\s*(?:[·x×*]\s*(\d{2})\s*薪)?", 1000),
        (r"(\d+(?:\.\d+)?)\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*万\s*(?:元)?(?:/月|每月|月薪)", 10000),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            low, high = float(match.group(1)) * multiplier, float(match.group(2)) * multiplier
            months = int(match.group(3)) if match.lastindex and match.lastindex >= 3 and match.group(3) else None
            result.update(salary_min_monthly=low, salary_max_monthly=high,
                          salary_months=months, salary_raw=match.group(0))
            return result
    annual = re.search(r"(\d+(?:\.\d+)?)\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*万\s*(?:元)?(?:/年|每年|年薪)", text)
    if annual:
        result.update(salary_min_monthly=float(annual.group(1)) * 10000 / 12,
                      salary_max_monthly=float(annual.group(2)) * 10000 / 12,
                      salary_months=12, salary_raw=annual.group(0))
        return result
    daily = re.search(r"(\d+(?:\.\d+)?)\s*[-~—–至]\s*(\d+(?:\.\d+)?)\s*元\s*(?:/天|每天|日薪)", text)
    if daily:
        result.update(salary_daily=(float(daily.group(1)) + float(daily.group(2))) / 2,
                      salary_raw=daily.group(0))
    return result


def find_date(text: str) -> str:
    match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", text)
    if not match:
        return ""
    try:
        return dt.date(*(int(x) for x in match.groups())).isoformat()
    except ValueError:
        return ""


def infer_employment(text: str) -> str:
    lowered = text.lower()
    if "实习" in lowered or "intern" in lowered:
        return "实习"
    if any(x in lowered for x in ("校招", "应届", "届", "graduate", "campus")):
        return "校招"
    if any(x in lowered for x in (
        "社招", "社会招聘", "年以上", "全职", "full_time", "full-time", "full time"
    )):
        return "全职/社招"
    return "未注明"


def infer_education(text: str) -> str:
    for item in ("博士", "硕士", "本科", "大专"):
        if item in text:
            return item
    return "未注明"


def infer_experience(text: str) -> str:
    for pattern in (r"经验不限", r"应届", r"(\d+)\s*[-~—–至]\s*(\d+)\s*年", r"(\d+)\s*年以上", r"(\d+)\s*年经验"):
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return "未注明"


def infer_location(text: str, locations: list[str]) -> str:
    explicit = re.search(
        r"(?:工作地点|工作城市|职位地点|地点|location)\s*[：:]\s*([^。；;|]{1,40})",
        text,
        re.I,
    )
    if explicit:
        explicit_hits = [loc for loc in locations if loc != "全国" and loc in explicit.group(1)]
        if explicit_hits:
            return " / ".join(explicit_hits[:3])
    hits = [loc for loc in locations if loc != "全国" and loc in text]
    return " / ".join(hits[:3]) if hits else "未注明"


def extract_skills(text: str, skills: list[str]) -> list[str]:
    lowered = text.lower()
    return [skill for skill in skills if skill.lower() in lowered]


def split_clauses(text: str) -> list[str]:
    """Return compact, de-duplicated clauses suitable for job-detail summaries."""
    normalized = re.sub(r"\s+(?=(?:\d+|[一二三四五六七八九十])[.、）)])", "。", clean_text(text))
    pieces = re.split(r"[。；;\n]+", normalized)
    clauses: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        value = re.sub(r"^(?:\d+|[一二三四五六七八九十])[.、）)]\s*", "", piece).strip(" ，,:：-")
        if 6 <= len(value) <= 220 and value not in seen:
            seen.add(value)
            clauses.append(value)
    return clauses


def extract_capability_groups(text: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    lowered = text.lower()
    groups: list[dict[str, Any]] = []
    for name, keywords in config.get("capability_groups", {}).items():
        signals = [word for word in keywords if word.lower() in lowered]
        if signals:
            groups.append({"name": name, "signals": signals[:6]})
    return groups


def extract_job_sections(text: str) -> tuple[list[str], list[str]]:
    clauses = split_clauses(text)
    responsibility_hints = ("负责", "参与", "设计", "构建", "开发", "优化", "实现", "维护", "调试", "研究")
    requirement_hints = ("要求", "熟悉", "掌握", "具备", "本科", "硕士", "博士", "经验", "优先", "能力")
    responsibilities = [item for item in clauses if any(hint in item for hint in responsibility_hints)][:5]
    requirements = [item for item in clauses if any(hint in item for hint in requirement_hints)][:5]
    if not responsibilities:
        responsibilities = clauses[:2]
    return responsibilities, requirements


def build_interview_prep(capabilities: list[dict[str, Any]], skills: list[str],
                         category: str) -> list[dict[str, str]]:
    templates = {
        "编程与系统": "请结合项目说明一次性能瓶颈定位：如何测量、归因并验证优化有效？",
        "感知与多模态": "如果 RGB-D 或多模态观测存在噪声与时延，你会怎样设计鲁棒表征和评测？",
        "规划控制与学习": "请设计一个从示范或强化学习到真机闭环验证的最小实验，并说明失败恢复。",
        "仿真与数据闭环": "如何验证仿真数据真的提升目标机器人，而不只是在离线指标上变好？",
        "部署与训练基础设施": "如何把训练、评测、部署做成可复现流水线，并定位线上退化？",
        "硬件与产品化": "面对执行器、传感器或真机安全约束，你会设置哪些验收门槛？",
    }
    questions: list[dict[str, str]] = []
    for group in capabilities[:4]:
        name = group["name"]
        questions.append({
            "question": templates.get(name, f"请说明你在{name}方面最能证明能力的项目。"),
            "basis": f"岗位信号：{name} / {'、'.join(group['signals'][:4])}",
        })
    if not questions:
        basis = "、".join(skills[:4]) or category
        questions.append({
            "question": f"请用一个可验证的项目说明你为何适合“{category}”方向。",
            "basis": f"岗位信号：{basis}",
        })
    return questions


def job_insights(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    text = clean_text(job.get("description_excerpt", ""))
    responsibilities, requirements = extract_job_sections(text)
    capabilities = extract_capability_groups(
        " ".join((job.get("title", ""), text, " ".join(job.get("skills", [])))), config
    )
    clauses = split_clauses(text)
    if responsibilities:
        summary = responsibilities[0]
    elif clauses:
        summary = clauses[0]
    else:
        summary = "当前只解析到岗位标题，请打开原始招聘页查看完整职责。"
    completeness = "详细" if len(responsibilities) >= 2 and len(requirements) >= 2 else (
        "有限" if text else "仅标题线索"
    )
    return {
        "workSummary": summary[:240],
        "responsibilities": responsibilities,
        "requirements": requirements,
        "capabilityGroups": capabilities,
        "interviewPrep": build_interview_prep(capabilities, job.get("skills", []), job.get("category", "其他")),
        "contentCompleteness": completeness,
        "evidenceSnippet": text[:360],
    }


def classify(text: str, categories: dict[str, list[str]]) -> tuple[str, dict[str, int]]:
    lowered = text.lower()
    scores = {name: sum(1 for keyword in words if keyword.lower() in lowered)
              for name, words in categories.items()}
    best = max(scores, key=scores.get) if scores else "其他"
    # "算法工程师/深度学习" occurs in almost every technical posting. Prefer
    # a more specific role family when at least two specific signals exist.
    generic = "通用算法/多模态/CV"
    specific = {name: score for name, score in scores.items() if name != generic}
    if best == generic and specific and max(specific.values()) >= 2:
        best = max(specific, key=specific.get)
    return (best if scores.get(best, 0) else "其他"), scores


def parse_job_page(url: str, body: str, config: dict[str, Any], discovery: dict[str, str] | None = None) -> dict[str, Any]:
    parser = VisibleTextParser()
    parser.feed(body)
    visible = " ".join(parser.parts)
    job = first_jobposting(parser)
    discovery = discovery or {}
    if job:
        title = clean_text(job.get("title"))
        company = nested_name(job.get("hiringOrganization"))
        description = clean_text(job.get("description"))
        location = parse_location(job.get("jobLocation"))
        date_posted = clean_text(job.get("datePosted"))[:10]
        employment = infer_employment(
            clean_text(job.get("employmentType")) + " " + title + " " + description
        )
        salary = normalize_salary(title + " " + description, job.get("baseSalary"))
    else:
        title = (parser.meta.get("og:title") or " ".join(parser.title_parts) or discovery.get("title", ""))[:300]
        description = (parser.meta.get("description") or parser.meta.get("og:description") or
                       discovery.get("description", "") or visible)[:12000]
        company = ""
        nowcoder_company = re.search(r"_([^_]+?)(?:校招|实习|社招)_牛客网", title)
        if nowcoder_company:
            company = nowcoder_company.group(1).strip()
        for sep in (" - ", " | ", "_招聘", "招聘_"):
            if not company and sep in title:
                pieces = [x.strip() for x in title.split(sep) if x.strip()]
                if len(pieces) >= 2:
                    company = pieces[-1]
                    break
        # Prefer the description: company names in titles often contain a city
        # that is unrelated to the job's actual workplace.
        location = infer_location(description, config["locations"])
        if location == "未注明":
            location = infer_location(title, config["locations"])
        date_posted = find_date(visible)
        employment = infer_employment(title + " " + description)
        salary = normalize_salary(title + " " + visible[:20000])
    combined = " ".join((title, description, visible[:20000]))
    category, category_scores = classify(combined, config["categories"])
    if not location:
        location = infer_location(combined, config["locations"])
    skill_list = extract_skills(combined, config["skills"])
    canonical = canonical_url(url)
    fingerprint_base = "|".join((title.lower(), company.lower(), location.lower()))
    fingerprint = hashlib.sha256(fingerprint_base.encode("utf-8")).hexdigest()[:24]
    return {
        "id": fingerprint,
        "url": canonical,
        "source_domain": urlsplit(canonical).netloc,
        "title": clean_text(title),
        "company": clean_text(company),
        "location": clean_text(location) or "未注明",
        "date_posted": date_posted,
        "employment_type": employment,
        "education": infer_education(combined),
        "experience": infer_experience(combined),
        "category": category,
        "category_scores": category_scores,
        "skills": skill_list,
        "description_excerpt": clean_text(description)[:4000],
        **salary,
    }




class DjiHotJobsParser(HTMLParser):
    """Extract individual server-rendered cards from DJI's official hot-jobs page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.field = ""
        self.current: dict[str, Any] = {}
        self.jobs: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        classes = values.get("class", "")
        if tag == "div" and "pc_card__" in classes and not self.depth:
            self.depth = 1
            self.current = {"title": [], "locations": [], "description": [], "url": ""}
            return
        if not self.depth:
            return
        if tag == "div":
            self.depth += 1
        if tag == "a" and values.get("href"):
            self.current["url"] = values["href"]
        if tag == "h4":
            self.field = "title"
        elif tag == "span" and "pc_tag__" in classes:
            self.field = "locations"
        elif tag == "p" and "pc_intro__" in classes:
            self.field = "description"

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        if tag in {"h4", "span", "p"}:
            self.field = ""
        if tag == "div":
            self.depth -= 1
            if not self.depth:
                if self.current.get("url") and self.current.get("title"):
                    self.jobs.append(self.current)
                self.current = {}

    def handle_data(self, data: str) -> None:
        if self.depth and self.field:
            cleaned = " ".join(data.split())
            if cleaned:
                self.current[self.field].append(cleaned)


def parse_dji_hot_jobs(body: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    parser = DjiHotJobsParser()
    parser.feed(body)
    jobs: list[dict[str, Any]] = []
    for item in parser.jobs:
        title = clean_text(" ".join(item["title"]))
        description = clean_text(" ".join(item["description"]))
        location = " / ".join(dict.fromkeys(item["locations"])) or "未注明"
        combined = f"{title} {description}"
        category, category_scores = classify(combined, config["categories"])
        if category == "其他":
            continue
        salary = normalize_salary(combined)
        jobs.append({
            "id": hashlib.sha256(f"dji-hot-jobs:{title}".encode("utf-8")).hexdigest()[:24],
            "url": item["url"],
            "source_domain": "careers.dji.com",
            "title": title,
            "company": "大疆创新",
            "location": location,
            "date_posted": "",
            "employment_type": "校招",
            "education": infer_education(combined),
            "experience": infer_experience(combined),
            "category": category,
            "category_scores": category_scores,
            "skills": extract_skills(combined, config["skills"]),
            "description_excerpt": description[:4000],
            **salary,
        })
    return jobs


class UnitreePositionsParser(HTMLParser):
    """Extract the server-rendered cards on Unitree's official positions page."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.field = ""
        self.duty_depth = 0
        self.current: dict[str, Any] = {}
        self.jobs: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        classes = values.get("class", "").split()
        if not self.depth and tag == "a" and "link" in classes and values.get("href", "").startswith("/position/"):
            self.depth = 1
            self.current = {"title": [], "base": [], "duties": [], "url": values["href"]}
            return
        if not self.depth:
            return
        if tag not in self.VOID_TAGS:
            self.depth += 1
        if tag == "p" and "title" in classes:
            self.field = "title"
        elif tag == "p" and "base-info" in classes:
            self.field = "base"
        elif tag == "div" and "duty" in classes:
            self.duty_depth = self.depth
            self.field = "duties"

    def handle_endtag(self, tag: str) -> None:
        if not self.depth:
            return
        if tag == "p":
            self.field = "duties" if self.duty_depth else ""
        if tag == "div" and self.duty_depth == self.depth:
            self.duty_depth = 0
            self.field = ""
        self.depth -= 1
        if not self.depth:
            if self.current.get("url") and self.current.get("title"):
                self.jobs.append(self.current)
            self.current = {}
            self.field = ""
            self.duty_depth = 0

    def handle_data(self, data: str) -> None:
        if self.depth and self.field:
            cleaned = " ".join(data.split())
            if cleaned and cleaned not in {"HOT", "热招", "急聘"}:
                self.current[self.field].append(cleaned)


def parse_unitree_positions(body: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    parser = UnitreePositionsParser()
    parser.feed(body)
    jobs: list[dict[str, Any]] = []
    for item in parser.jobs:
        title = clean_text(" ".join(item["title"]))
        base = clean_text(" ".join(item["base"]))
        description = "。".join(clean_text(value) for value in item["duties"] if clean_text(value))
        combined = f"{title} {base} {description}"
        category, category_scores = classify(combined, config["categories"])
        if category == "其他":
            continue
        salary = normalize_salary(combined)
        url = canonical_url(urljoin("https://www.unitree.com/", item["url"]))
        jobs.append({
            "id": hashlib.sha256(f"unitree:{url}".encode("utf-8")).hexdigest()[:24],
            "url": url,
            "source_domain": "www.unitree.com",
            "title": title,
            "company": "宇树科技",
            "location": infer_location(base, config["locations"]),
            "date_posted": "",
            "employment_type": infer_employment(combined),
            "education": infer_education(combined),
            "experience": infer_experience(combined),
            "category": category,
            "category_scores": category_scores,
            "skills": extract_skills(combined, config["skills"]),
            "description_excerpt": description[:4000],
            **salary,
        })
    return jobs


class Fetcher:
    def __init__(self, config: dict[str, Any]) -> None:
        request_cfg = config["request"]
        self.timeout = request_cfg["timeout_seconds"]
        self.delay = request_cfg["delay_seconds"]
        self.respect_robots = request_cfg.get("respect_robots_txt", True)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = request_cfg["user_agent"]
        self.robot_cache: dict[str, RobotFileParser | None] = {}
        self.response_cache: dict[str, requests.Response] = {}
        self.last_request = 0.0

    def allowed(self, url: str) -> tuple[bool, str]:
        if not self.respect_robots:
            return True, "robots_check_disabled"
        split = urlsplit(url)
        root = f"{split.scheme}://{split.netloc}"
        if root not in self.robot_cache:
            robots_url = urljoin(root, "/robots.txt")
            try:
                response = self.session.get(
                    robots_url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                response.raise_for_status()
                parser = RobotFileParser(robots_url)
                parser.parse(response.text.splitlines())
                self.robot_cache[root] = parser
            except Exception:
                self.robot_cache[root] = None
        parser = self.robot_cache[root]
        if parser is None:
            return True, "robots_unavailable"
        return parser.can_fetch(self.session.headers["User-Agent"], url), "robots_txt"

    def get(self, url: str, check_robots: bool = True) -> requests.Response:
        cached = self.response_cache.get(canonical_url(url))
        if cached is not None:
            return cached
        if check_robots:
            allowed, reason = self.allowed(url)
            if not allowed:
                raise PermissionError(f"robots.txt disallows URL ({reason})")
        remaining = self.delay - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)
        response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        self.last_request = time.monotonic()
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if ("html" in content_type or "text" in content_type) and "charset=" not in content_type:
            try:
                response.content.decode("utf-8")
                response.encoding = "utf-8"
            except UnicodeDecodeError:
                response.encoding = response.apparent_encoding
        self.response_cache[canonical_url(url)] = response
        return response


def discover_bing_rss(fetcher: Fetcher, query: str, max_results: int) -> list[dict[str, str]]:
    # Bing exposes an RSS representation of public web search results. No API key is used.
    url = "https://www.bing.com/search?format=rss&q=" + quote_plus(query)
    response = fetcher.get(url, check_robots=False)
    root = ET.fromstring(response.content)
    results: list[dict[str, str]] = []
    for item in root.findall(".//item")[:max_results]:
        link = clean_text(item.findtext("link"))
        title = clean_text(item.findtext("title"))
        description = clean_text(item.findtext("description"))
        if link:
            results.append({"url": link, "title": title, "description": description, "query": query})
    return results


def looks_like_job(item: dict[str, str]) -> bool:
    haystack = (item.get("title", "") + " " + item.get("description", "") + " " + item.get("url", "")).lower()
    return any(hint.lower() in haystack for hint in JOB_HINTS)


def discovery_matches_query_scope(item: dict[str, str]) -> bool:
    """Keep search-engine results inside an explicit site: query boundary."""
    match = re.search(r"(?:^|\s)site:([^\s]+)", item.get("query", ""), re.I)
    if not match:
        return True
    requested = match.group(1).strip().strip("/.").lower()
    return domain_allowed(item.get("url", ""), [requested])


def discovery_fallback_relevant(item: dict[str, str], config: dict[str, Any]) -> bool:
    """A manual lead needs job intent and a configured career direction in result text."""
    if not discovery_matches_query_scope(item) or not looks_like_job(item):
        return False
    result_text = " ".join((item.get("title", ""), item.get("description", ""), item.get("url", "")))
    _, scores = classify(result_text, config["categories"])
    if max(scores.values(), default=0) < 1:
        return False
    parsed = urlsplit(item.get("url", ""))
    generic_title = any(word in item.get("title", "").lower() for word in ("招聘网", "人才网", "招聘官网", "招聘首页"))
    if generic_title and parsed.path in {"", "/"}:
        return False
    return True


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, url TEXT NOT NULL, source_domain TEXT, title TEXT,
        company TEXT, location TEXT, date_posted TEXT, employment_type TEXT,
        education TEXT, experience TEXT, category TEXT, skills_json TEXT,
        description_excerpt TEXT, salary_min_monthly REAL, salary_max_monthly REAL,
        salary_months INTEGER, salary_daily REAL, salary_raw TEXT,
        first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS observations (
        run_date TEXT NOT NULL, job_id TEXT NOT NULL, category TEXT, location TEXT,
        salary_min_monthly REAL, salary_max_monthly REAL,
        PRIMARY KEY (run_date, job_id)
    );
    CREATE TABLE IF NOT EXISTS runs (
        run_date TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT,
        discovered INTEGER, fetched INTEGER, parsed INTEGER, failures INTEGER,
        notes TEXT
    );
    """)


def store_job(connection: sqlite3.Connection, job: dict[str, Any], run_date: str) -> None:
    existing = connection.execute("SELECT first_seen FROM jobs WHERE id = ?", (job["id"],)).fetchone()
    first_seen = existing[0] if existing else run_date
    connection.execute("""
    INSERT OR REPLACE INTO jobs VALUES (
        :id, :url, :source_domain, :title, :company, :location, :date_posted,
        :employment_type, :education, :experience, :category, :skills_json,
        :description_excerpt, :salary_min_monthly, :salary_max_monthly,
        :salary_months, :salary_daily, :salary_raw, :first_seen, :last_seen
    )
    """, {**job, "skills_json": json.dumps(job["skills"], ensure_ascii=False),
           "first_seen": first_seen, "last_seen": run_date})
    connection.execute("""
    INSERT OR REPLACE INTO observations
    (run_date, job_id, category, location, salary_min_monthly, salary_max_monthly)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (run_date, job["id"], job["category"], job["location"],
          job["salary_min_monthly"], job["salary_max_monthly"]))


def configured_career_links(companies: list[dict[str, Any]], checked_at: str,
                            listing_status: dict[str, str] | None = None) -> list[dict[str, Any]]:
    listing_status = listing_status or {}
    links: list[dict[str, Any]] = []
    for company in companies:
        url = company.get("careerUrl", "")
        if not url:
            continue
        status = listing_status.get(canonical_url(url), "官方固定入口")
        links.append({
            "id": f"career-{company['id']}",
            "company": company["name"],
            "title": f"{company['name']} · {company.get('careerKind', '招聘入口')}",
            "url": url,
            "sourceTier": "公司官方入口",
            "status": status,
            "verification": (
                "本次已成功访问职位列表" if status == "本次可访问" else
                "本次职位列表请求失败，仍保留官方入口" if status == "本次访问失败" else
                "来自公司注册表；动态页面可能需要手动搜索岗位"
            ),
            "discoveredAt": checked_at,
            "careerKind": company.get("careerKind", "招聘入口"),
            "matchedSignals": [],
        })
    return links


def discovery_fallback_link(item: dict[str, str], checked_at: str,
                            config: dict[str, Any]) -> dict[str, Any]:
    combined = " ".join((item.get("title", ""), item.get("description", ""), item.get("query", "")))
    category, _ = classify(combined, config["categories"])
    return {
        "id": "lead-" + hashlib.sha256(canonical_url(item["url"]).encode("utf-8")).hexdigest()[:20],
        "company": "待从原页确认",
        "title": item.get("title") or "招聘搜索线索",
        "url": item["url"],
        "sourceTier": source_tier(urlsplit(item["url"]).netloc, config),
        "status": "需手动打开",
        "verification": "搜索结果与方向匹配，但本次未能稳定解析详情；直接打开原页确认。",
        "discoveredAt": checked_at,
        "careerKind": "最新搜索线索",
        "query": item.get("query", ""),
        "category": category,
        "matchedSignals": extract_skills(combined, config["skills"])[:8],
        "excerpt": clean_text(item.get("description", ""))[:280],
    }


def deduplicate_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for job in jobs:
        key = canonical_url(job["url"])
        previous = unique.get(key)
        if previous is None or len(job.get("description_excerpt", "")) > len(previous.get("description_excerpt", "")):
            unique[key] = job
    return list(unique.values())


def collect(config_path: Path, db_path: Path, dry_run: bool = False) -> int:
    config = load_config(config_path)
    companies = load_company_registry(config_path, config)
    if dry_run:
        print(json.dumps({"queries": len(config["discovery_queries"]),
                          "seeds": len(config["seed_urls"]),
                          "categories": list(config["categories"])}, ensure_ascii=False, indent=2))
        return 0
    run_date = dt.date.today().isoformat()
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    fetcher = Fetcher(config)
    discoveries: dict[str, dict[str, str]] = {
        canonical_url(url): {"url": url, "title": "", "description": "", "query": "seed"}
        for url in config["seed_urls"]
    }
    discovery_failures: list[str] = []
    for query in config["discovery_queries"]:
        try:
            for item in discover_bing_rss(fetcher, query, config["request"]["max_results_per_query"]):
                if (domain_allowed(item["url"], config["allowed_domains"])
                        and discovery_matches_query_scope(item) and looks_like_job(item)):
                    discoveries.setdefault(canonical_url(item["url"]), item)
        except Exception as exc:
            discovery_failures.append(f"discovery {query}: {type(exc).__name__}: {exc}")

    jobs: list[dict[str, Any]] = []
    fallback_links: list[dict[str, Any]] = []
    listing_status: dict[str, str] = {}
    failures = list(discovery_failures)
    fetched = 0
    for listing in config.get("listing_sources", []):
        try:
            response = fetcher.get(listing["url"])
            fetched += 1
            listing_status[canonical_url(listing["url"])] = "本次可访问"
            if listing["type"] == "dji_hot_jobs":
                jobs.extend(parse_dji_hot_jobs(response.text, config))
            elif listing["type"] == "unitree_positions":
                jobs.extend(parse_unitree_positions(response.text, config))
            else:
                raise ValueError(f"unsupported listing source {listing['type']}")
        except Exception as exc:
            listing_status[canonical_url(listing.get("url", ""))] = "本次访问失败"
            failures.append(
                f"listing {listing.get('url', '')}: {type(exc).__name__}: {exc}"
            )
    for canonical, item in discoveries.items():
        try:
            response = fetcher.get(item["url"])
            fetched += 1
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower() and "text" not in content_type.lower():
                raise ValueError(f"unsupported content-type {content_type}")
            job = parse_job_page(response.url, response.text, config, item)
            relevant_score = max(job["category_scores"].values(), default=0)
            if relevant_score == 0 or not any(hint.lower() in (job["title"] + " " + job["description_excerpt"]).lower()
                                              for hint in JOB_HINTS):
                raise ValueError("page does not look like a relevant job")
            jobs.append(job)
        except Exception as exc:
            failures.append(f"fetch {canonical}: {type(exc).__name__}: {exc}")
            if item.get("query") != "seed" and discovery_fallback_relevant(item, config):
                fallback_links.append(discovery_fallback_link(item, started, config))

    jobs = deduplicate_jobs(jobs)
    all_links = configured_career_links(companies, started, listing_status) + fallback_links
    unique_links = {canonical_url(item["url"]): item for item in all_links}
    CAREER_LINKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CAREER_LINKS_PATH.write_text(json.dumps({
        "meta": {
            "generatedAt": started,
            "count": len(unique_links),
            "manualLeadCount": len(fallback_links),
            "notice": "无法稳定解析的动态招聘页仍保留直达链接；是否开放以原页面为准。",
        },
        "items": list(unique_links.values()),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{run_date}.jsonl"
    with raw_path.open("w", encoding="utf-8") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        init_db(connection)
        # A same-day rerun replaces that day's incomplete snapshot instead of
        # mixing records from failed verification attempts.
        connection.execute("DELETE FROM observations WHERE run_date = ?", (run_date,))
        for job in jobs:
            store_job(connection, job, run_date)
        connection.execute("""
            DELETE FROM jobs
            WHERE first_seen = ? AND last_seen = ?
              AND id NOT IN (SELECT job_id FROM observations)
        """, (run_date, run_date))
        connection.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (run_date, started, dt.datetime.now(dt.timezone.utc).isoformat(),
                            len(discoveries), fetched, len(jobs), len(failures),
                            "\n".join(failures[:100])))
        connection.commit()

    print(f"run_date={run_date} discovered={len(discoveries)} fetched={fetched} parsed={len(jobs)} failures={len(failures)}")
    print(f"raw={raw_path} db={db_path}")
    if failures:
        print("Failure sample:")
        for failure in failures[:10]:
            print("-", failure)
    return 0 if jobs else 2


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def pct(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def is_entry(job: dict[str, Any]) -> bool:
    text = job["employment_type"] + " " + job["experience"]
    return any(x in text for x in ("实习", "校招", "应届", "经验不限", "1年"))


def experience_year_bounds(text: str) -> tuple[int | None, int | None]:
    normalized = text.lower()
    ranges = re.findall(r"(\d+)\s*[-~—–至]\s*(\d+)\s*年", normalized)
    if ranges:
        lower, upper = max((int(left), int(right)) for left, right in ranges)
        return min(lower, upper), max(lower, upper)
    minimums = re.findall(r"(\d+)\s*年以上", normalized)
    if minimums:
        lower = max(int(value) for value in minimums)
        return lower, None
    exact = re.findall(r"(\d+)\s*年(?:工作)?经验", normalized)
    if exact:
        value = max(int(item) for item in exact)
        return value, value
    return None, None


def entry_barrier(
    job: dict[str, Any], config: dict[str, Any]
) -> tuple[str, int, list[str]]:
    """Estimate application barriers from explicit JD evidence, never admission odds."""
    priority_config = config.get("job_priority", {})
    title = str(job.get("title", "")).lower()
    text = " ".join(str(job.get(key, "")) for key in (
        "title", "description_excerpt"
    )).lower()
    high_signals = [
        str(signal) for signal in priority_config.get("high_barrier_signals", [])
        if str(signal).lower() in text
    ]
    if "博士" in title:
        high_signals.append("职位标题明确博士方向")
    lower_years, upper_years = experience_year_bounds(text)
    if lower_years is not None and lower_years >= int(priority_config.get("junior_max_years", 3)):
        high_signals.append(f"明确要求至少 {lower_years} 年经验")
    if high_signals:
        return "高", 20, list(dict.fromkeys(high_signals))[:4]

    friendly_signals = [
        str(signal) for signal in priority_config.get("entry_friendly_signals", [])
        if str(signal).lower() in text
    ]
    employment = str(job.get("employment_type", ""))
    education = next((value for value in ("博士", "硕士", "本科", "大专") if value in text), "未注明")
    has_explicit_easy_experience = any(
        value in text for value in ("经验不限", "应届", "无经验")
    )
    at_most_one_year = upper_years is not None and upper_years <= 1

    if (
        employment in {"实习", "校招"}
        and education == "本科"
        and (friendly_signals or has_explicit_easy_experience)
    ) or (
        employment in {"全职/社招", "全职", "社招"}
        and education in {"本科", "未注明"}
        and (has_explicit_easy_experience or at_most_one_year)
    ):
        basis = friendly_signals + (["本科可投"] if education == "本科" else [])
        if at_most_one_year:
            basis.append("经验要求不超过 1 年")
        return "低", 80, list(dict.fromkeys(basis))[:4]

    if employment in {"实习", "校招"}:
        has_experience_evidence = has_explicit_easy_experience or lower_years is not None
        if education == "未注明" and not has_experience_evidence:
            return "不可判断", 40, [
                f"岗位类型为{employment}",
                "学历与经验要求未完整披露",
            ]
        basis = friendly_signals or [f"岗位类型为{employment}"]
        if education == "硕士":
            basis.append("要求硕士")
        elif education == "博士":
            basis.append("页面提到博士，是否为硬性要求需核实")
        return "中", 55, list(dict.fromkeys(basis))[:4]

    junior_limit = int(priority_config.get("junior_max_years", 3))
    if lower_years is not None and lower_years < junior_limit:
        basis = [
            f"经验范围 {lower_years}-{upper_years} 年" if upper_years is not None
            else f"至少 {lower_years} 年经验"
        ]
        if education == "硕士":
            basis.append("要求硕士")
        return "中", 55, basis

    return "不可判断", 40, ["岗位页未提供足够的学历或经验门槛证据"]


def job_priority(
    job: dict[str, Any],
    config: dict[str, Any],
    match: int,
    source: str,
) -> dict[str, Any]:
    priority_config = config.get("job_priority", {})
    barrier, friendliness, barrier_basis = entry_barrier(job, config)
    company = str(job.get("company", ""))
    category = str(job.get("category", ""))
    employment = str(job.get("employment_type", ""))
    role_text = " ".join(str(job.get(key, "")) for key in (
        "title", "description_excerpt"
    )).lower()
    big_tech = any(
        str(name).lower() in company.lower()
        for name in priority_config.get("big_tech_companies", [])
    )
    direct = (
        category in set(priority_config.get("direct_categories", []))
        and any(
            str(signal).lower() in role_text
            for signal in priority_config.get("direct_signals", [])
        )
    )
    adjacent = category in set(priority_config.get("adjacent_categories", []))
    acceptable_barrier = barrier in {"低", "中", "不可判断"}

    if direct and employment in {"实习", "校招"} and acceptable_barrier:
        tier, label, bonus = "P0", "具身实习/校招", 18
    elif direct and employment in {"全职/社招", "全职", "社招"} and barrier in {"低", "中"}:
        tier, label, bonus = "P1", "具身初级全职", 14
    elif big_tech and adjacent and barrier in {"低", "中"}:
        tier, label, bonus = "P2", "大厂入门友好岗位", 10
    else:
        tier, label, bonus = "P3", "其他匹配岗位", 0

    barrier_adjustment = {"低": 12, "中": 5, "不可判断": -3, "高": -25}[barrier]
    official_bonus = 6 if source == "公司官方" else 0
    score = max(0, min(100, match + bonus + barrier_adjustment + official_bonus))
    return {
        "entryBarrier": barrier,
        "entryFriendliness": friendliness,
        "entryBasis": barrier_basis,
        "priorityTier": tier,
        "priorityLabel": label,
        "priorityScore": score,
        "isBigTech": big_tech,
    }


def pressure_proxy(jobs: list[dict[str, Any]]) -> tuple[str, float]:
    """Low-confidence entry pressure proxy; it is not an applicant/job ratio."""
    if not jobs:
        return "无样本", 0.0
    entry_share = sum(is_entry(job) for job in jobs) / len(jobs)
    graduate_gate = sum(job["education"] in {"硕士", "博士"} for job in jobs) / len(jobs)
    companies = len({job["company"] for job in jobs if job["company"]})
    concentration = 1 - min(companies / max(len(jobs), 1), 1)
    score = 100 * (0.55 * (1 - entry_share) + 0.25 * graduate_gate + 0.20 * concentration)
    if len(jobs) < 10 or entry_share >= 0.85:
        return "不可估计", round(score, 1)
    label = "高" if score >= 65 else "中" if score >= 40 else "低"
    return label, round(score, 1)


def load_jobs(connection: sqlite3.Connection, run_date: str | None) -> tuple[str, list[dict[str, Any]]]:
    if not run_date:
        row = connection.execute("SELECT MAX(run_date) FROM observations").fetchone()
        run_date = row[0] if row else None
    if not run_date:
        return "", []
    columns = [row[1] for row in connection.execute("PRAGMA table_info(jobs)")]
    rows = connection.execute("""
        SELECT j.* FROM jobs j JOIN observations o ON o.job_id=j.id
        WHERE o.run_date=? ORDER BY j.category, j.title
    """, (run_date,)).fetchall()
    jobs = [dict(zip(columns, row)) for row in rows]
    for job in jobs:
        job["skills"] = json.loads(job.pop("skills_json") or "[]")
    return run_date, jobs


def summarize(jobs: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        groups.setdefault(job["category"], []).append(job)
    rows = []
    profile = {x.lower() for x in config["profile_signals"]}
    for category in list(config["categories"]) + (["其他"] if "其他" in groups else []):
        group = groups.get(category, [])
        monthly = [(job["salary_min_monthly"] + job["salary_max_monthly"]) / 2
                   for job in group if job["salary_min_monthly"] is not None and job["salary_max_monthly"] is not None]
        group_skills = [skill for job in group for skill in job["skills"]]
        skill_counts = {skill: group_skills.count(skill) for skill in sorted(set(group_skills))}
        common = sorted(skill_counts, key=lambda x: (-skill_counts[x], x))[:8]
        observed = {skill.lower() for skill in group_skills}
        match = pct(len(profile & observed), len(profile))
        pressure, pressure_score = pressure_proxy(group)
        rows.append({
            "category": category,
            "jobs": len(group),
            "companies": len({job["company"] for job in group if job["company"]}),
            "shenzhen_pct": pct(sum("深圳" in job["location"] for job in group), len(group)),
            "entry_pct": pct(sum(is_entry(job) for job in group), len(group)),
            "salary_n": len(monthly),
            "salary_median": median(monthly),
            "profile_coverage_pct": match,
            "pressure": pressure,
            "pressure_score": pressure_score,
            "common_skills": common,
        })
    return rows


def read_evidence(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def money(value: float | None) -> str:
    return "未披露" if value is None else f"{value / 1000:.1f}K/月"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def write_reports(config_path: Path, db_path: Path, run_date: str | None = None) -> int:
    config = load_config(config_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2
    with sqlite3.connect(db_path) as connection:
        selected_date, jobs = load_jobs(connection, run_date)
        run = connection.execute("SELECT * FROM runs WHERE run_date=?", (selected_date,)).fetchone()
        dates = [row[0] for row in connection.execute("SELECT DISTINCT run_date FROM observations ORDER BY run_date")]
    if not jobs:
        print("No jobs available for report", file=sys.stderr)
        return 2
    rows = summarize(jobs, config)
    evidence = read_evidence(ROOT / "market_evidence.csv")
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    csv_path = reports / f"{selected_date}-jobs.csv"
    csv_fields = ["title", "company", "location", "category", "employment_type", "education",
                  "experience", "salary_min_monthly", "salary_max_monthly", "salary_months",
                  "salary_daily", "date_posted", "skills", "source_domain", "url"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for job in jobs:
            writer.writerow({key: (";".join(job[key]) if key == "skills" else job.get(key, "")) for key in csv_fields})

    run_note = ""
    if run:
        run_note = f"发现链接 {run[3]}，成功请求 {run[4]}，纳入岗位 {run[5]}，失败 {run[6]}。"
    md: list[str] = [
        f"# 就业市场扫描报告：{selected_date}", "",
        f"样本岗位数：**{len(jobs)}**。{run_note}", "",
        "> 这是以公开搜索发现的2027届校招/实习页面为主的样本，不代表全市场。薪资只统计明确披露的全职月薪；竞争代理不是投递人数或真实供需比。", "",
        "## 方向比较", "",
        "|方向|岗位|公司|深圳占比|实习/校招友好|薪资样本|披露薪资中位数|经历关键词覆盖|入门竞争代理|", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    ]
    for row in rows:
        md.append(f"|{row['category']}|{row['jobs']}|{row['companies']}|{row['shenzhen_pct']}%|{row['entry_pct']}%|{row['salary_n']}|{money(row['salary_median'])}|{row['profile_coverage_pct']}%|{row['pressure']} ({row['pressure_score']})|")
    md += ["", "竞争代理计算：55%×非入门岗位占比 + 25%×硕博门槛占比 + 20%×岗位集中度。它只衡量应届进入难度，可信度低，不能替代投递/候选人数。", "",
           "## 高频技能", ""]
    for row in rows:
        md.append(f"- **{row['category']}**：{', '.join(row['common_skills']) or '样本不足'}")
    md += ["", "## 行业供需证据（与本次岗位样本分开）", "",
           "|时期|市场|岗位增速|求职增速|说明|", "|---|---|---:|---:|---|"]
    for item in evidence:
        md.append(f"|{item['period']}|{item['market']}|{item['job_growth_pct'] or '—'}%|{item['candidate_growth_pct'] or '—'}%|[{item['note']}]({item['source_url']})|")
    md += ["", "## 当前样本岗位", ""]
    for job in jobs:
        md.append(f"- [{job['title'] or '标题缺失'}]({job['url']}) — {job['company'] or '公司未解析'}；{job['location']}；{job['employment_type']}；{job['salary_raw'] or '薪资未披露'}")
    if len(dates) < 2:
        md += ["", "## 趋势限制", "", "当前只有一次快照，不能建立真实新增/消失趋势。至少间隔一周再次运行后才开始报告纵向趋势。"]
    md_path = reports / f"{selected_date}-report.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    max_jobs = max(max(row["jobs"] for row in rows), 1)
    cards = "".join(
        f'<article><h3>{esc(row["category"])}</h3><div class="bar"><i style="width:{100*row["jobs"]/max_jobs:.1f}%"></i></div>'
        f'<p><b>{row["jobs"]}</b> 岗位 · {row["companies"]} 公司 · 深圳 {row["shenzhen_pct"]}%</p>'
        f'<p>入门友好 {row["entry_pct"]}% · 薪资中位 {esc(money(row["salary_median"]))}</p>'
        f'<p>经历覆盖 {row["profile_coverage_pct"]}% · 竞争代理 {esc(row["pressure"])} {row["pressure_score"]}</p>'
        f'<small>{esc(", ".join(row["common_skills"]) or "样本不足")}</small></article>' for row in rows
    )
    job_rows = "".join(
        f'<tr><td><a href="{esc(job["url"])}">{esc(job["title"] or "标题缺失")}</a></td>'
        f'<td>{esc(job["company"] or "未解析")}</td><td>{esc(job["category"])}</td>'
        f'<td>{esc(job["location"])}</td><td>{esc(job["employment_type"])}</td><td>{esc(job["salary_raw"] or "未披露")}</td></tr>'
        for job in jobs
    )
    html_doc = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>就业市场扫描 {esc(selected_date)}</title><style>
body{{font:15px/1.55 system-ui,sans-serif;margin:0;background:#f5f7fb;color:#172033}}main{{max-width:1180px;margin:auto;padding:32px 20px}}
.note{{background:#fff4d8;border-left:4px solid #d69000;padding:12px 16px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px}}
article{{background:white;border:1px solid #dde3ee;border-radius:12px;padding:16px}}h1,h2,h3{{line-height:1.2}}.bar{{height:8px;background:#e8edf5;border-radius:8px}}.bar i{{display:block;height:100%;background:#2f6fed;border-radius:8px}}
table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:9px;border-bottom:1px solid #e5e9f0;text-align:left;vertical-align:top}}a{{color:#175dcc}}small{{color:#566176}}
</style><main><h1>就业市场扫描：{esc(selected_date)}</h1><p>{esc(run_note)}</p><p class="note">公开网页样本，不代表全市场。竞争代理只衡量入门门槛，不是投递人数或真实供需比。首次快照不能判断纵向趋势。</p>
<h2>方向比较</h2><section class="grid">{cards}</section><h2>岗位明细</h2><table><thead><tr><th>职位</th><th>公司</th><th>方向</th><th>地点</th><th>类型</th><th>薪资</th></tr></thead><tbody>{job_rows}</tbody></table>
<p>完整方法、行业证据和限制见同名 Markdown 报告。</p></main></html>"""
    html_path = reports / f"{selected_date}-report.html"
    html_path.write_text(html_doc, encoding="utf-8")
    print(f"markdown={md_path}\nhtml={html_path}\ncsv={csv_path}")
    return 0


def source_tier(domain: str, config: dict[str, Any]) -> str:
    official = set(config.get("official_domains", []))
    if any(domain == item or domain.endswith("." + item) for item in official):
        return "公司官方"
    if domain.endswith(".edu.cn"):
        return "高校转发"
    return "招聘平台"


def display_job_title(title: str) -> str:
    if "牛客网" in title and "_" in title:
        return title.split("_", 1)[0].strip()
    return re.sub(r"\s*[-_|]\s*(?:招聘|职位).*$", "", title).strip() or title


def explicit_location(text: str, locations: list[str]) -> str:
    match = re.search(
        r"(?:工作地点|工作城市|职位地点|地点|location)\s*[：:]\s*([^。；;|]{1,40})",
        text,
        re.I,
    )
    if not match:
        return ""
    hits = [loc for loc in locations if loc != "全国" and loc in match.group(1)]
    return " / ".join(hits[:3])


def match_score(job: dict[str, Any], config: dict[str, Any], flags: list[str]) -> tuple[int, list[str]]:
    profile = {item.lower() for item in config["profile_signals"]}
    matches = [skill for skill in job["skills"] if skill.lower() in profile]
    score = 38 + min(40, 8 * len(matches))
    if job["category"] in {"机器人仿真/合成数据", "3D视觉/点云/重建", "机器人控制/VLA",
                           "数据工程/数据闭环", "柔性物体/布料"}:
        score += 8
    if "深圳" in job["location"]:
        score += 6
    if is_entry(job):
        score += 4
    if "发布日期较旧" in flags:
        score -= 12
    if "地点信息冲突" in flags:
        score -= 8
    if "发布日期异常" in flags:
        score -= 20
    if job["company"] in {"", "公司未解析"}:
        score -= 18
    return max(0, min(100, score)), matches


def company_registry_match(job_company: str, companies: list[dict[str, Any]]) -> str:
    lowered = job_company.lower()
    for company in companies:
        names = [company.get("name", ""), *company.get("aliases", [])]
        if any(name and name.lower() in lowered for name in names):
            return company["id"]
    return ""


def export_site_data(config_path: Path, db_path: Path, output_path: Path,
                     run_date: str | None = None) -> int:
    config = load_config(config_path)
    companies = load_company_registry(config_path, config)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2
    with sqlite3.connect(db_path) as connection:
        selected_date, jobs = load_jobs(connection, run_date)
        snapshot_dates = [
            row[0] for row in connection.execute(
                "SELECT DISTINCT run_date FROM observations ORDER BY run_date"
            )
        ]
    if not jobs:
        print("No jobs available for export", file=sys.stderr)
        return 2

    selected = dt.date.fromisoformat(selected_date)
    records: list[dict[str, Any]] = []
    official_count = 0
    flagged_count = 0
    for job in jobs:
        flags: list[str] = []
        location = job["location"] or "未注明"
        explicit = explicit_location(job["description_excerpt"], config["locations"])
        if explicit and explicit != location:
            flags.append("地点信息冲突")
            location = explicit

        age_days: int | None = None
        if job["date_posted"]:
            try:
                age_days = (selected - dt.date.fromisoformat(job["date_posted"])).days
                if age_days > 180:
                    flags.append("发布日期较旧")
                elif age_days < 0:
                    flags.append("发布日期异常")
            except ValueError:
                flags.append("发布日期无法解析")
        else:
            flags.append("发布日期缺失")

        tier = source_tier(job["source_domain"], config)
        if tier == "公司官方":
            official_count += 1
        else:
            flags.append("非公司官方来源")
        score_job = dict(job)
        score_job["location"] = location
        score, matched = match_score(score_job, config, flags)
        priority = job_priority(score_job, config, score, tier)
        insights = job_insights(job, config)
        listing_status = "可能过期" if "发布日期较旧" in flags else (
            "官网本次可见" if tier == "公司官方" else "页面本次可访问"
        )
        if flags:
            flagged_count += 1
        records.append({
            "id": job["id"],
            "company": job["company"] or "公司未解析",
            "title": display_job_title(job["title"] or "标题缺失"),
            "rawTitle": job["title"] or "标题缺失",
            "location": location,
            "category": job["category"],
            "employmentType": job["employment_type"],
            "education": job["education"],
            "experience": job["experience"],
            "datePosted": job["date_posted"],
            "ageDays": age_days,
            "match": score,
            "matchBasis": matched,
            **priority,
            "skills": job["skills"],
            **insights,
            "salary": {
                "raw": job["salary_raw"],
                "minMonthly": job["salary_min_monthly"],
                "maxMonthly": job["salary_max_monthly"],
                "months": job["salary_months"],
                "daily": job["salary_daily"],
            },
            "url": job["url"],
            "sourceDomain": job["source_domain"],
            "sourceTier": tier,
            "verification": "本次成功获取并解析",
            "listingStatus": listing_status,
            "lastSeen": job["last_seen"],
            "qualityFlags": flags,
            "companyId": company_registry_match(job["company"], companies),
        })

    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    records.sort(key=lambda item: (
        priority_order.get(item["priorityTier"], 9),
        -item["priorityScore"],
        -item["match"],
        item["company"],
        item["title"],
    ))
    try:
        career_payload = json.loads(CAREER_LINKS_PATH.read_text(encoding="utf-8"))
        career_links = career_payload.get("items", [])
    except (OSError, json.JSONDecodeError):
        career_links = configured_career_links(companies, dt.datetime.now(dt.timezone.utc).isoformat())
    company_counts: dict[str, dict[str, int]] = {}
    for record in records:
        if not record["companyId"]:
            continue
        count = company_counts.setdefault(record["companyId"], {"jobCount": 0, "officialJobCount": 0})
        count["jobCount"] += 1
        if record["sourceTier"] == "公司官方":
            count["officialJobCount"] += 1
    company_records = [
        {**company, **company_counts.get(company["id"], {"jobCount": 0, "officialJobCount": 0})}
        for company in companies
    ]
    manual_count = sum(item.get("status") == "需手动打开" for item in career_links)
    fresh_count = sum(item["listingStatus"] != "可能过期" for item in records)
    priority_counts = {
        tier: sum(item["priorityTier"] == tier for item in records)
        for tier in priority_order
    }
    entry_friendly_count = sum(item["entryBarrier"] == "低" for item in records)
    payload = {
        "meta": {
            "snapshotDate": selected_date,
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "jobCount": len(records),
            "officialSourceCount": official_count,
            "flaggedCount": flagged_count,
            "freshJobCount": fresh_count,
            "entryFriendlyJobCount": entry_friendly_count,
            "priorityCounts": priority_counts,
            "manualLinkCount": manual_count,
            "companyCount": len(company_records),
            "snapshotCount": len(snapshot_dates),
            "trendReady": len(snapshot_dates) >= 2,
            "notice": "公开网页样本，不代表全市场。非官方来源、旧发布日期和字段冲突均已显式标注。",
            "matchMethod": "匹配分衡量技能与方向贴合；岗位优先分另行结合岗位类型、明确门槛和官方来源排序，均不是录用概率。",
            "entryBarrierMethod": "只依据岗位页明确披露的学历、经验和职级信号；信息不足标为不可判断。",
        },
        "jobs": records,
        "careerLinks": career_links,
        "companies": company_records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"site_json={output_path} jobs={len(records)} official={official_count} flagged={flagged_count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    collect_parser = sub.add_parser("collect", help="discover and collect public job pages")
    collect_parser.add_argument("--dry-run", action="store_true")
    report_parser = sub.add_parser("report", help="generate Markdown, HTML and CSV reports")
    report_parser.add_argument("--date", help="snapshot date, defaults to latest")
    export_parser = sub.add_parser("export-site", help="export quality-labelled JSON for the radar website")
    export_parser.add_argument("--date", help="snapshot date, defaults to latest")
    export_parser.add_argument("--output", type=Path, default=ROOT / "data" / "jobs.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "collect":
        return collect(args.config, args.db, args.dry_run)
    if args.command == "export-site":
        return export_site_data(args.config, args.db, args.output, args.date)
    return write_reports(args.config, args.db, args.date)


if __name__ == "__main__":
    raise SystemExit(main())
