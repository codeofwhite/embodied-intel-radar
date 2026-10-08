"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, BriefcaseBusiness, Building2, CircleAlert, ExternalLink,
  GraduationCap, Link2, MapPin, MessageSquareText, Plus, RefreshCw, Search, Star, Trash2,
  TrendingDown, TrendingUp,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

type Capability = { name: string; signals: string[] };
type InterviewPrep = { question: string; basis: string };
type Job = {
  id: string; company: string; companyId?: string; title: string; location: string;
  category: string; employmentType?: string; education?: string; experience?: string;
  match: number; matchBasis: string[]; skills: string[]; url: string; sourceTier: string;
  entryBarrier?: string; entryFriendliness?: number; entryBasis?: string[];
  priorityTier?: string; priorityLabel?: string; priorityScore?: number; isBigTech?: boolean;
  verification: string; listingStatus?: string; qualityFlags: string[];
  datePosted?: string | null; lastSeen?: string; contentCompleteness?: string;
  workSummary?: string; responsibilities?: string[]; requirements?: string[];
  capabilityGroups?: Capability[]; interviewPrep?: InterviewPrep[]; evidenceSnippet?: string;
  salary?: { raw?: string };
};
type CareerLink = {
  id: string; company: string; title: string; url: string; sourceTier: string;
  status: string; verification: string; discoveredAt: string; careerKind?: string;
  category?: string; query?: string; matchedSignals?: string[]; excerpt?: string;
};
type Company = {
  id: string; name: string; city: string; companyType: string; listedStatus: string;
  ticker?: string; marketTier: string; focus: string; careerUrl: string; careerKind: string;
  officialUrl: string; evidenceUrl: string; jobCount: number; officialJobCount: number;
};
type IntelItem = {
  id: string; title: string; excerpt?: string; url: string; domain: string;
  sourceTier: string; verification: string; publishedAt?: string; discoveredAt: string;
  company?: string; role?: string; platform?: "X" | "小红书";
  signalType?: string; confidence?: string; freshness?: string;
  eventType?: string; project?: string; version?: string; repo?: string;
  releaseTitle?: string; whatHappened?: string; keyChanges?: string[];
  affectedAreas?: string[]; whyItMatters?: string; suggestedAction?: string;
  interpretation?: string;
};
type SearchShortcut = { id: string; platform: "X" | "小红书"; label: string; query: string; url: string };
type SavedSocialSignal = {
  id: string; platform: "X" | "小红书"; url: string; title: string; note: string;
  signalType: string; company: string; role: string; tags: string[];
  publishedAt?: string | null; createdAt: string; confidence: string;
};
type QuotePoint = { date: string; close: number };
type Quote = {
  name: string; symbol: string; providerSymbol: string; tier: string; currency: string;
  price: number; previousClose: number; changePercent: number; marketDate: string;
  observedAt: string; points: number[]; status: string; seriesInterval?: string;
  series?: QuotePoint[];
};
type ItemEnvelope<T> = { meta: Record<string, unknown>; items?: T[] };
type SocialEnvelope = ItemEnvelope<IntelItem> & { searchShortcuts?: SearchShortcut[] };
type JobEnvelope = {
  meta: Record<string, unknown>; jobs?: Job[]; careerLinks?: CareerLink[]; companies?: Company[];
};
type Snapshot = {
  generatedAt: string; jobs: JobEnvelope; events: ItemEnvelope<IntelItem>;
  social: SocialEnvelope; quotes: ItemEnvelope<Quote>;
  refresh: { status?: string; finishedAt?: string };
};

const SIGNAL_TYPES = ["招人/内推", "面试经验", "岗位能力画像", "薪酬与工作强度", "团队方向变化", "普通观点/传闻"];
const EMPTY_SIGNAL_DRAFT = { url: "", title: "", note: "", signalType: "招人/内推", company: "", role: "", tags: "" };
type RefreshRequest = {
  id: string; status: string; requestedAt?: string; claimedAt?: string;
  finishedAt?: string; message?: string;
};

const statusText: Record<string, string> = {
  queued: "排队中", running: "采集中", succeeded: "已完成",
  ok: "已完成", degraded: "部分来源失败", failed: "失败",
};

function formatTime(value?: string | null) {
  if (!value) return "尚未更新";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

type MarketRange = "1M" | "3M" | "ALL";
const MARKET_RANGES: { value: MarketRange; label: string }[] = [
  { value: "1M", label: "1 个月" },
  { value: "3M", label: "3 个月" },
  { value: "ALL", label: "全部可用" },
];

function formatMarketDate(value?: string) {
  if (!value) return "日期待补全";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function formatQuotePrice(value: number, currency: string) {
  const prefix = currency === "CNY" ? "¥" : currency === "USD" ? "$" : "";
  const sign = value < 0 ? "-" : "";
  return `${sign}${prefix}${Math.abs(value).toFixed(2)}`;
}

function quoteSeriesForRange(quote: Quote, range: MarketRange): QuotePoint[] {
  const dated = Array.isArray(quote.series) && quote.series.length >= 2;
  const source = dated
    ? quote.series!
    : (quote.points ?? []).map((close, index, points) => ({
        date: index === points.length - 1 ? "最新" : `T-${points.length - index - 1}`,
        close,
      }));
  if (!dated || range === "ALL" || source.length < 2) return source;
  const latest = new Date(`${source[source.length - 1].date}T00:00:00Z`);
  const cutoff = new Date(latest);
  cutoff.setUTCDate(cutoff.getUTCDate() - (range === "1M" ? 31 : 93));
  const filtered = source.filter(point => new Date(`${point.date}T00:00:00Z`) >= cutoff);
  return filtered.length >= 2 ? filtered : source;
}

function marketStats(series: QuotePoint[]) {
  if (!series.length) return { high: 0, low: 0, absolute: 0, percent: 0 };
  const prices = series.map(point => point.close);
  const first = prices[0];
  const last = prices[prices.length - 1];
  return {
    high: Math.max(...prices),
    low: Math.min(...prices),
    absolute: last - first,
    percent: first ? ((last - first) / first) * 100 : 0,
  };
}

export default function Home() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [refresh, setRefresh] = useState<RefreshRequest | null>(null);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("全部来源");
  const [freshnessFilter, setFreshnessFilter] = useState("本次可访问");
  const [categoryFilter, setCategoryFilter] = useState("全部方向");
  const [employmentFilter, setEmploymentFilter] = useState("全部类型");
  const [priorityFilter, setPriorityFilter] = useState("全部重点");
  const [barrierFilter, setBarrierFilter] = useState("全部门槛");
  const [marketTier, setMarketTier] = useState("核心业务");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [marketRange, setMarketRange] = useState<MarketRange>("1M");
  const [eventTypeFilter, setEventTypeFilter] = useState("全部类型");
  const [eventMode, setEventMode] = useState<"latest" | "all">("latest");
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [savedSocial, setSavedSocial] = useState<SavedSocialSignal[]>([]);
  const [socialLoadState, setSocialLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [socialStatus, setSocialStatus] = useState("");
  const [signalPlatformFilter, setSignalPlatformFilter] = useState("全部平台");
  const [signalTypeFilter, setSignalTypeFilter] = useState("全部类型");
  const [signalDraft, setSignalDraft] = useState(EMPTY_SIGNAL_DRAFT);
  const [saved, setSaved] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set();
    try { return new Set(JSON.parse(localStorage.getItem("eir-saved-jobs") ?? "[]")); }
    catch { return new Set(); }
  });

  const loadSnapshot = useCallback(async () => {
    try {
      const response = await fetch("/api/snapshot", { cache: "no-store" });
      if (response.status === 404) { setLoadState("empty"); return; }
      if (!response.ok) throw new Error(String(response.status));
      setSnapshot(await response.json());
      setLoadState("ready");
    } catch { setLoadState("error"); }
  }, []);

  const loadSavedSocial = useCallback(async () => {
    try {
      const response = await fetch("/api/social-signals", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      const payload = await response.json() as { items?: SavedSocialSignal[] };
      setSavedSocial(payload.items ?? []);
      setSocialLoadState("ready");
    } catch {
      setSocialLoadState("error");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadSnapshot(); void loadSavedSocial(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadSnapshot, loadSavedSocial]);
  useEffect(() => {
    if (!refresh || !["queued", "running"].includes(refresh.status)) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(`/api/refresh/${refresh.id}`, { cache: "no-store" });
      if (!response.ok) return;
      const next = await response.json() as RefreshRequest;
      setRefresh(next);
      if (!["queued", "running"].includes(next.status)) void loadSnapshot();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh, loadSnapshot]);

  async function requestRefresh() {
    const response = await fetch("/api/refresh", { method: "POST" });
    if (!response.ok) {
      setRefresh({ id: "error", status: "failed", message: "刷新请求提交失败" });
      return;
    }
    setRefresh(await response.json());
  }

  function toggleSaved(id: string) {
    const next = new Set(saved);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSaved(next);
    localStorage.setItem("eir-saved-jobs", JSON.stringify([...next]));
  }

  async function submitSocialSignal(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSocialStatus("正在保存…");
    try {
      const response = await fetch("/api/social-signals", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ...signalDraft,
          tags: signalDraft.tags.split(/[,，]/).map(tag => tag.trim()).filter(Boolean),
        }),
      });
      const payload = await response.json() as { signal?: SavedSocialSignal; error?: string };
      if (!response.ok || !payload.signal) {
        const messages: Record<string, string> = {
          only_x_or_xiaohongshu_https_urls: "目前只接受 X、Twitter、小红书或 xhslink 的 HTTPS 链接。",
          url_already_saved: "这个链接已经保存过了。",
          invalid_payload: "输入过长或格式不正确，请检查后重试。",
        };
        throw new Error(messages[payload.error ?? ""] ?? "保存失败，输入内容已保留。 ");
      }
      setSavedSocial(items => [payload.signal!, ...items]);
      setSignalDraft(EMPTY_SIGNAL_DRAFT);
      setSocialLoadState("ready");
      setSocialStatus("已保存到私有链接收件箱。");
    } catch (error) {
      setSocialStatus(error instanceof Error ? error.message : "保存失败，输入内容已保留。");
    }
  }

  async function removeSocialSignal(id: string) {
    setSocialStatus("正在删除…");
    try {
      const response = await fetch("/api/social-signals", {
        method: "DELETE",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id }),
      });
      if (!response.ok) throw new Error();
      setSavedSocial(items => items.filter(item => item.id !== id));
      setSocialStatus("已从私有收件箱删除。");
    } catch {
      setSocialStatus("删除失败，页面内容未改变。");
    }
  }

  const jobs = useMemo(() => snapshot?.jobs.jobs ?? [], [snapshot]);
  const careerLinks = useMemo(() => snapshot?.jobs.careerLinks ?? [], [snapshot]);
  const companies = useMemo(() => snapshot?.jobs.companies ?? [], [snapshot]);
  const events = useMemo(() => snapshot?.events.items ?? [], [snapshot]);
  const social = useMemo(() => snapshot?.social.items ?? [], [snapshot]);
  const socialShortcuts = useMemo(() => snapshot?.social.searchShortcuts ?? [], [snapshot]);
  const quotes = useMemo(() => snapshot?.quotes.items ?? [], [snapshot]);
  const categories = useMemo(() => [...new Set(jobs.map(job => job.category))], [jobs]);
  const filteredJobs = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return jobs.filter(job => {
      const searchMatch = !needle || `${job.company} ${job.title} ${job.location} ${job.category} ${job.skills.join(" ")} ${job.workSummary ?? ""} ${job.priorityLabel ?? ""} ${(job.entryBasis ?? []).join(" ")}`.toLowerCase().includes(needle);
      const sourceMatch = sourceFilter === "全部来源" || job.sourceTier === "公司官方";
      const freshnessMatch = freshnessFilter === "全部岗位" || job.listingStatus !== "可能过期";
      const categoryMatch = categoryFilter === "全部方向" || job.category === categoryFilter;
      const employmentMatch = employmentFilter === "全部类型" || job.employmentType === employmentFilter;
      const priorityMatch = priorityFilter === "全部重点" || job.priorityLabel === priorityFilter;
      const barrierMatch = barrierFilter === "全部门槛" || job.entryBarrier === barrierFilter;
      return searchMatch && sourceMatch && freshnessMatch && categoryMatch && employmentMatch && priorityMatch && barrierMatch;
    });
  }, [jobs, query, sourceFilter, freshnessFilter, categoryFilter, employmentFilter, priorityFilter, barrierFilter]);
  const visibleLinks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return careerLinks.filter(link => !needle || `${link.company} ${link.title} ${link.category ?? ""} ${(link.matchedSignals ?? []).join(" ")}`.toLowerCase().includes(needle));
  }, [careerLinks, query]);
  const officialJobs = jobs.filter(job => job.sourceTier === "公司官方").length;
  const manualLinks = careerLinks.filter(link => link.status === "需手动打开").length;
  const filteredIndexedSocial = social.filter(item =>
    (signalPlatformFilter === "全部平台" || item.platform === signalPlatformFilter)
    && (signalTypeFilter === "全部类型" || item.signalType === signalTypeFilter)
  );
  const filteredSavedSocial = savedSocial.filter(item =>
    (signalPlatformFilter === "全部平台" || item.platform === signalPlatformFilter)
    && (signalTypeFilter === "全部类型" || item.signalType === signalTypeFilter)
  );
  const activeRefresh = refresh && ["queued", "running"].includes(refresh.status);
  const quoteStatus = String(snapshot?.quotes.meta.status ?? "unconfigured");
  const tierQuotes = useMemo(() => quotes.filter(quote => quote.tier === marketTier), [quotes, marketTier]);
  const selectedQuote = tierQuotes.find(quote => quote.symbol === selectedSymbol) ?? tierQuotes[0];
  const selectedMarketSeries = useMemo(
    () => selectedQuote ? quoteSeriesForRange(selectedQuote, marketRange) : [],
    [selectedQuote, marketRange],
  );
  const selectedMarketStats = useMemo(() => marketStats(selectedMarketSeries), [selectedMarketSeries]);
  const selectedHasDatedHistory = Boolean(selectedQuote?.series && selectedQuote.series.length >= 2);
  const eventTypes = useMemo(
    () => [...new Set(events.map(item => item.eventType ?? item.sourceTier))],
    [events],
  );
  const visibleEvents = useMemo(() => {
    const filtered = events.filter(item =>
      eventTypeFilter === "全部类型" || (item.eventType ?? item.sourceTier) === eventTypeFilter
    );
    if (eventMode === "all") return filtered;
    const seen = new Set<string>();
    return filtered.filter(item => {
      const key = item.repo ?? `${item.company ?? ""}:${item.project ?? item.company ?? item.title}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [events, eventTypeFilter, eventMode]);

  function chooseMarketTier(tier: string) {
    setMarketTier(tier);
    setSelectedSymbol(quotes.find(quote => quote.tier === tier)?.symbol ?? "");
  }

  return (
    <main className="radar-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">E</span><div><strong>具身智能雷达</strong><small>就业优先 · 公司 · 市场</small></div></div>
        <div className="sync-line"><span className={loadState === "ready" ? "status-dot ready" : "status-dot"} />
          {loadState === "ready" ? `线上快照 ${formatTime(snapshot?.generatedAt)}` : loadState === "loading" ? "正在读取线上数据" : loadState === "empty" ? "等待首个线上快照" : "线上数据暂不可用"}
        </div>
        <Button onClick={requestRefresh} disabled={Boolean(activeRefresh)} className="refresh-button"><RefreshCw className={activeRefresh ? "spin" : ""} />{activeRefresh ? statusText[refresh!.status] : "立即刷新"}</Button>
      </header>

      {refresh && <div className={`refresh-strip ${refresh.status}`} role="status"><Activity /><strong>{statusText[refresh.status] ?? refresh.status}</strong><span>{refresh.message ?? (refresh.status === "queued" ? "本机采集器会在约 2 分钟内接单" : "刷新状态已更新")}</span></div>}

      <div className="dashboard">
        <section className="intro jobs-intro">
          <div><p className="eyebrow">EMBODIED AI CAREER RADAR</p><h1>先看最新匹配岗位</h1></div>
          <div className="intro-stats"><span><strong>{jobs.length}</strong> 已解析岗位</span><span><strong>{officialJobs}</strong> 公司官网来源</span><span><strong>{manualLinks}</strong> 条手动线索</span></div>
        </section>

        <Tabs defaultValue="jobs" className="radar-tabs">
          <TabsList className="nav-tabs">
            <TabsTrigger value="jobs">招聘 <span>{jobs.length || "—"}</span></TabsTrigger>
            <TabsTrigger value="signals">就业情报 <span>{social.length + savedSocial.length || "—"}</span></TabsTrigger>
            <TabsTrigger value="companies">公司 <span>{companies.length || "—"}</span></TabsTrigger>
            <TabsTrigger value="markets">行情 <span>{quotes.length || "—"}</span></TabsTrigger>
            <TabsTrigger value="events">事件 <span>{events.length || "—"}</span></TabsTrigger>
            <TabsTrigger value="overview">总览</TabsTrigger>
          </TabsList>

          <TabsContent value="jobs">
            <div className="section-head jobs-head">
              <div><h2>岗位与面试准备</h2><p>职责和问题由页面文本提炼；模拟题不是公司真实面试原题。</p></div>
              <label className="search-box"><Search /><Input value={query} onChange={event => setQuery(event.target.value)} placeholder="公司、岗位、城市或技能" /></label>
            </div>
            <div className="filter-bar">
              <FilterGroup label="新鲜度" values={["本次可访问", "全部岗位"]} active={freshnessFilter} onChange={setFreshnessFilter} />
              <FilterGroup label="来源" values={["全部来源", "公司官方"]} active={sourceFilter} onChange={setSourceFilter} />
              <label className="select-filter"><span>方向</span><select value={categoryFilter} onChange={event => setCategoryFilter(event.target.value)}><option>全部方向</option>{categories.map(category => <option key={category}>{category}</option>)}</select></label>
              <label className="select-filter"><span>类型</span><select value={employmentFilter} onChange={event => setEmploymentFilter(event.target.value)}><option>全部类型</option><option>实习</option><option>校招</option><option>全职/社招</option><option>社招</option></select></label>
              <label className="select-filter"><span>重点</span><select value={priorityFilter} onChange={event => setPriorityFilter(event.target.value)}><option>全部重点</option><option>具身实习/校招</option><option>具身初级全职</option><option>大厂入门友好岗位</option></select></label>
              <label className="select-filter"><span>入门门槛</span><select value={barrierFilter} onChange={event => setBarrierFilter(event.target.value)}><option>全部门槛</option><option>低</option><option>中</option><option>不可判断</option><option>高</option></select></label>
              <span className="result-count">{filteredJobs.length} 个结果</span>
            </div>
            <div className="job-list">
              {filteredJobs.map(job => (
                <article className="job-card" key={job.id}>
                  <div className="job-main">
                    <p>{job.company}</p><h3>{job.title}</h3>
                    <div className="tag-row"><Badge variant={job.priorityTier === "P0" || job.priorityTier === "P1" ? "default" : "secondary"}>{job.priorityLabel ?? "其他匹配岗位"}</Badge><Badge variant="outline">入门门槛：{job.entryBarrier ?? "不可判断"}</Badge><Badge variant="outline">{job.employmentType || "类型未注明"}</Badge><Badge variant="outline"><MapPin />{job.location || "地点未披露"}</Badge><Badge variant={job.sourceTier === "公司官方" ? "default" : "secondary"}>{job.sourceTier}</Badge><Badge variant="outline">{job.listingStatus ?? "状态待确认"}</Badge><Badge variant="outline">{job.category}</Badge></div>
                    <p className="work-summary">{job.workSummary || "当前只解析到标题，建议打开原页查看完整职责。"}</p>
                    <div className="skill-row">{job.skills.slice(0, 8).map(skill => <span key={skill}>{skill}</span>)}</div>
                    {job.qualityFlags?.length > 0 && <p className="quality">需注意：{job.qualityFlags.join("、")}</p>}
                  </div>
                  <div className="job-side">
                    <button className={saved.has(job.id) ? "star saved" : "star"} onClick={() => toggleSaved(job.id)} aria-label="收藏岗位"><Star /></button>
                    <strong>{job.priorityScore ?? job.match}<small>岗位优先分</small></strong>
                    <Button variant="outline" size="sm" onClick={() => setSelectedJob(job)}>能力与面试</Button>
                    <a href={job.url} target="_blank" rel="noreferrer">招聘原页 <ExternalLink /></a>
                  </div>
                </article>
              ))}
              {!filteredJobs.length && <Empty text={loadState === "ready" ? "没有符合当前条件的岗位，可切换到全部岗位或查看下方招聘入口。" : "等待线上数据。"} />}
            </div>

            <div className="section-head link-head"><div><h2>招聘入口与未解析线索</h2><p>动态页面抓不下来也保留直达地址；“需手动打开”是最新搜索线索，不代表已经核验岗位开放。</p></div></div>
            <div className="career-grid">
              {visibleLinks.map(link => (
                <a className={`career-card ${link.status === "需手动打开" ? "manual" : ""}`} href={link.url} target="_blank" rel="noreferrer" key={link.id}>
                  <div><Badge variant="outline">{link.status}</Badge><span>{link.company}</span></div>
                  <h3>{link.title}</h3><p>{link.excerpt || link.verification}</p>
                  {(link.matchedSignals ?? []).length > 0 && <small>匹配：{link.matchedSignals!.join("、")}</small>}
                  <strong>打开招聘页面 <ExternalLink /></strong>
                </a>
              ))}
              {!visibleLinks.length && <Empty text="当前没有匹配的招聘入口。" />}
            </div>
          </TabsContent>

          <TabsContent value="signals">
            <div className="section-head signals-head">
              <div><p className="eyebrow">X + 小红书</p><h2>就业情报与链接收件箱</h2><p>社媒内容帮助发现岗位、面试和团队信号，但不计入真实招聘岗位；重要信息请回到公司招聘页交叉确认。</p></div>
              <div className="signal-filter-row">
                <label className="select-filter"><span>平台</span><select value={signalPlatformFilter} onChange={event => setSignalPlatformFilter(event.target.value)}><option>全部平台</option><option>X</option><option>小红书</option></select></label>
                <label className="select-filter"><span>类型</span><select value={signalTypeFilter} onChange={event => setSignalTypeFilter(event.target.value)}><option>全部类型</option>{SIGNAL_TYPES.map(type => <option key={type}>{type}</option>)}</select></label>
              </div>
            </div>

            <section className="shortcut-panel">
              <div><h3>直接搜最新内容</h3><p>搜索按钮只是入口，不会被统计成情报；结果按平台实时展示，时间与真实性需在原文确认。</p></div>
              <div className="shortcut-grid">
                {socialShortcuts.map(shortcut => <a href={shortcut.url} target="_blank" rel="noreferrer" key={shortcut.id}><Badge variant="outline">{shortcut.platform}</Badge><span>{shortcut.label}</span><ExternalLink /></a>)}
                {!socialShortcuts.length && <small>完成下一次采集刷新后会出现预设搜索入口。</small>}
              </div>
            </section>

            <div className="signal-layout">
              <form className="signal-form" onSubmit={submitSocialSignal}>
                <div className="form-title"><Plus /><div><h3>保存一条链接</h3><p>抓不到正文也可以只贴链接；标题可留空，备注会原样保留。</p></div></div>
                <label className="wide"><span>链接 *</span><Input required type="url" value={signalDraft.url} onChange={event => setSignalDraft(draft => ({ ...draft, url: event.target.value }))} placeholder="https://x.com/... 或 https://www.xiaohongshu.com/..." /></label>
                <label><span>信号类型</span><select value={signalDraft.signalType} onChange={event => setSignalDraft(draft => ({ ...draft, signalType: event.target.value }))}>{SIGNAL_TYPES.map(type => <option key={type}>{type}</option>)}</select></label>
                <label><span>标题</span><Input value={signalDraft.title} onChange={event => setSignalDraft(draft => ({ ...draft, title: event.target.value }))} placeholder="例如：某机器人团队内推" maxLength={160} /></label>
                <label><span>关联公司</span><Input value={signalDraft.company} onChange={event => setSignalDraft(draft => ({ ...draft, company: event.target.value }))} placeholder="宇树科技（可选）" maxLength={80} /></label>
                <label><span>关联岗位</span><Input value={signalDraft.role} onChange={event => setSignalDraft(draft => ({ ...draft, role: event.target.value }))} placeholder="VLA / 仿真 / 数据（可选）" maxLength={100} /></label>
                <label className="wide"><span>标签</span><Input value={signalDraft.tags} onChange={event => setSignalDraft(draft => ({ ...draft, tags: event.target.value }))} placeholder="深圳，校招，VLA（逗号分隔）" /></label>
                <label className="wide"><span>我的备注</span><Textarea value={signalDraft.note} onChange={event => setSignalDraft(draft => ({ ...draft, note: event.target.value }))} placeholder="记录能力要求、面试问题、联系人线索或需要后续核验的点。" maxLength={1000} /></label>
                <div className="form-actions"><Button type="submit"><MessageSquareText />保存到私有收件箱</Button><span role="status">{socialStatus}</span></div>
              </form>

              <div className="signal-explainer">
                <h3>怎么判断价值</h3>
                <ol><li><strong>招人/内推</strong><span>先核对公司、岗位名和官方投递入口。</span></li><li><strong>面试与能力</strong><span>提炼重复出现的技能，不把个人经历当公司统一标准。</span></li><li><strong>薪酬与强度</strong><span>记录城市、职级和时间，避免跨岗位直接比较。</span></li><li><strong>团队变化</strong><span>作为方向信号观察，不据此断言招聘扩张或收缩。</span></li></ol>
              </div>
            </div>

            <div className="section-head"><div><h2>我保存的链接</h2><p>持久保存在这个私有站点中；“待核实”不等于无用，而是提醒你回原文确认。</p></div><span className="result-count">{filteredSavedSocial.length} 条</span></div>
            <div className="signal-grid">
              {filteredSavedSocial.map(item => <SavedSignalCard item={item} onDelete={removeSocialSignal} key={item.id} />)}
              {!filteredSavedSocial.length && <Empty text={socialLoadState === "error" ? "私有收件箱暂不可用；你填写的表单内容不会自动清空。" : socialLoadState === "loading" ? "正在读取私有收件箱…" : "还没有保存符合当前筛选条件的链接。"} />}
            </div>

            <div className="section-head"><div><h2>自动发现的公开线索</h2><p>{String(snapshot?.social.meta.notice ?? "只使用公开搜索索引，不请求登录后正文。")}</p></div><span className="result-count">{filteredIndexedSocial.length} 条</span></div>
            <div className="signal-grid">
              {filteredIndexedSocial.map(item => <IndexedSignalCard item={item} key={item.id} />)}
              {!filteredIndexedSocial.length && <Empty text="本轮没有通过严格相关性过滤的公开线索。可使用上方实时搜索入口，找到有价值的内容后直接粘贴保存。" />}
            </div>
          </TabsContent>

          <TabsContent value="companies">
            <div className="section-head"><div><h2>具身公司与招聘入口</h2><p>整机、具身模型、机器人部件和科技大厂统一查看；上市状态不等于投资建议。</p></div></div>
            <div className="company-grid">
              {companies.map(company => (
                <Card className="radar-card company-card" key={company.id}>
                  <CardHeader><div><Badge variant="outline">{company.companyType}</Badge><Badge variant="secondary">{company.listedStatus}{company.ticker ? ` · ${company.ticker}` : ""}</Badge></div><CardTitle>{company.name}</CardTitle></CardHeader>
                  <CardContent><p>{company.focus}</p><small><MapPin />{company.city}</small><div className="company-count"><strong>{company.jobCount}</strong><span>个当前样本岗位 · 官网 {company.officialJobCount}</span></div><a href={company.careerUrl} target="_blank" rel="noreferrer">{company.careerKind} <ExternalLink /></a></CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="markets">
            <div className="section-head market-heading">
              <div><h2>具身机器人与科技股观察池</h2><p>{String(snapshot?.quotes.meta.notice ?? "真实日线收盘数据，不是盘中实时交易报价。")}</p></div>
              <div className="tier-switch">{["核心业务", "产业链", "大厂敞口"].map(tier => <button className={marketTier === tier ? "active" : ""} onClick={() => chooseMarketTier(tier)} key={tier}>{tier}</button>)}</div>
            </div>
            {quoteStatus !== "ok" && <div className="market-warning"><CircleAlert />行情状态：{String(snapshot?.quotes.meta.notice ?? "行情源尚未配置或本次抓取失败。")}</div>}
            {selectedQuote ? <div className="market-layout">
              <section className="market-chart-panel">
                <header className="market-chart-head">
                  <div className="quote-identity"><span>{selectedQuote.tier}</span><h3>{selectedQuote.name}<small>{selectedQuote.symbol}</small></h3></div>
                  <div className="market-range" aria-label="选择行情时间范围">
                    {MARKET_RANGES.map(option => <button
                      className={(selectedHasDatedHistory ? marketRange : "ALL") === option.value ? "active" : ""}
                      disabled={!selectedHasDatedHistory && option.value !== "ALL"}
                      onClick={() => setMarketRange(option.value)}
                      title={!selectedHasDatedHistory && option.value !== "ALL" ? "日期历史待行情刷新补齐" : undefined}
                      key={option.value}
                    >{option.label}</button>)}
                  </div>
                </header>
                {!selectedHasDatedHistory && <div className="history-warning"><CircleAlert />当前旧缓存只有最近 10 个收盘点；真实日期将在行情刷新后补齐。</div>}
                <div className="market-price-line">
                  <div><strong>{formatQuotePrice(selectedQuote.price, selectedQuote.currency)}</strong><span>{selectedQuote.currency} · 日线收盘</span></div>
                  <span className={selectedQuote.changePercent < 0 ? "negative" : "positive"}>{selectedQuote.changePercent < 0 ? <TrendingDown /> : <TrendingUp />}当日 {selectedQuote.changePercent > 0 ? "+" : ""}{selectedQuote.changePercent.toFixed(2)}%</span>
                </div>
                <div className="market-stat-grid">
                  <div><span>区间涨跌</span><strong className={selectedMarketStats.percent < 0 ? "negative" : "positive"}>{selectedMarketStats.percent > 0 ? "+" : ""}{selectedMarketStats.percent.toFixed(2)}%</strong><small>{selectedMarketStats.absolute > 0 ? "+" : ""}{formatQuotePrice(selectedMarketStats.absolute, selectedQuote.currency)}</small></div>
                  <div><span>区间最高</span><strong>{formatQuotePrice(selectedMarketStats.high, selectedQuote.currency)}</strong></div>
                  <div><span>区间最低</span><strong>{formatQuotePrice(selectedMarketStats.low, selectedQuote.currency)}</strong></div>
                  <div><span>数据点</span><strong>{selectedMarketSeries.length}</strong><small>日线交易点</small></div>
                </div>
                <div className="market-chart" role="img" aria-label={`${selectedQuote.name}日线收盘价走势`}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={selectedMarketSeries} margin={{ top: 12, right: 12, bottom: 8, left: 4 }} accessibilityLayer>
                      <CartesianGrid stroke="#203026" strokeDasharray="3 5" vertical={false} />
                      <XAxis dataKey="date" minTickGap={38} tickLine={false} axisLine={{ stroke: "#304236" }} tick={{ fill: "#819383", fontSize: 11 }} tickFormatter={value => selectedHasDatedHistory ? String(value).slice(5) : String(value)} />
                      <YAxis width={66} domain={["auto", "auto"]} tickLine={false} axisLine={false} tick={{ fill: "#819383", fontSize: 11 }} tickFormatter={value => formatQuotePrice(Number(value), selectedQuote.currency)} />
                      <Tooltip contentStyle={{ background: "#071009", border: "1px solid #365342", borderRadius: 3 }} labelStyle={{ color: "#a8b9aa" }} formatter={value => [formatQuotePrice(Number(value), selectedQuote.currency), "收盘价"]} labelFormatter={label => selectedHasDatedHistory ? `交易日 ${formatMarketDate(String(label))}` : `历史点 ${String(label)}`} />
                      <Line type="monotone" dataKey="close" stroke={selectedMarketStats.percent < 0 ? "#ff7d7d" : "#64e9c6"} strokeWidth={2.5} dot={false} activeDot={{ r: 4, fill: "#ccff52", stroke: "#071009" }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <footer className="market-source"><span>交易日 {formatMarketDate(selectedQuote.marketDate)}</span><span>采集于 {formatTime(selectedQuote.observedAt)}</span><span>{selectedQuote.status === "stale" ? "缓存行情" : "Alpha Vantage EOD"}</span></footer>
              </section>
              <aside className="market-watchlist">
                <header><div><h3>{marketTier}</h3><p>选择标的查看时间区间与价格统计</p></div><span>{tierQuotes.length} 个</span></header>
                <div>{tierQuotes.map(quote => <button className={selectedQuote.symbol === quote.symbol ? "active" : ""} onClick={() => setSelectedSymbol(quote.symbol)} key={quote.symbol}>
                  <span><strong>{quote.name}</strong><small>{quote.symbol} · {formatMarketDate(quote.marketDate)}</small></span>
                  <span><strong>{formatQuotePrice(quote.price, quote.currency)}</strong><small className={quote.changePercent < 0 ? "negative" : "positive"}>{quote.changePercent > 0 ? "+" : ""}{quote.changePercent.toFixed(2)}%</small></span>
                </button>)}</div>
              </aside>
            </div> : <Empty text="这个分组尚未拿到真实行情；公司信息仍可在公司页查看。" />}
          </TabsContent>

          <TabsContent value="events">
            <div className="section-head events-heading">
              <div><h2>公司、研究与开源事件</h2><p>先看发生了什么和是否需要行动；来源事实与规则判断分开呈现。</p></div>
              <div className="event-controls">
                <label className="select-filter"><span>类型</span><select value={eventTypeFilter} onChange={event => setEventTypeFilter(event.target.value)}><option>全部类型</option>{eventTypes.map(type => <option key={type}>{type}</option>)}</select></label>
                <div className="tier-switch"><button className={eventMode === "latest" ? "active" : ""} onClick={() => setEventMode("latest")}>每个项目最新</button><button className={eventMode === "all" ? "active" : ""} onClick={() => setEventMode("all")}>全部历史</button></div>
              </div>
            </div>
            <div className="event-legend"><span><i className="fact-dot" />来源事实：发布与原文要点</span><span><i className="guide-dot" />规则判断：相关性与建议动作</span><strong>{visibleEvents.length} 条</strong></div>
            <div className="event-grid">{visibleEvents.map(item => <EventCard key={item.id} item={item} />)}{!visibleEvents.length && <Empty text="当前筛选下没有通过目标页验证的事件。" />}</div>
          </TabsContent>

          <TabsContent value="overview">
            <div className="metric-grid"><Metric icon={<BriefcaseBusiness />} label="本次岗位" value={jobs.length} detail={`官网来源 ${officialJobs}`} /><Metric icon={<Building2 />} label="公司库" value={companies.length} detail="含上市与未上市" /><Metric icon={<Link2 />} label="招聘入口" value={careerLinks.length} detail={`手动线索 ${manualLinks}`} /><Metric icon={<Activity />} label="行情覆盖" value={quotes.length} detail={quoteStatus === "ok" ? "真实 EOD 行情" : "部分行情待更新"} /></div>
            <div className="overview-grid"><Card className="radar-card"><CardHeader><CardTitle>最新事件</CardTitle></CardHeader><CardContent className="event-list compact">{events.slice(0, 5).map(item => <EventRow key={item.id} item={item} />)}{!events.length && <Empty text="尚无通过验证的公司、研究或开源事件。" />}</CardContent></Card><Card className="radar-card"><CardHeader><CardTitle>优先岗位</CardTitle></CardHeader><CardContent className="rank-list">{jobs.slice(0, 6).map(job => <button onClick={() => setSelectedJob(job)} key={job.id}><span>{job.company}<small>{job.title}</small></span><strong>{job.priorityScore ?? job.match}</strong></button>)}{!jobs.length && <Empty text="等待真实招聘快照。" />}</CardContent></Card></div>
          </TabsContent>
        </Tabs>
      </div>

      <JobSheet job={selectedJob} onClose={() => setSelectedJob(null)} />
    </main>
  );
}

function FilterGroup({ label, values, active, onChange }: { label: string; values: string[]; active: string; onChange: (value: string) => void }) {
  return <div className="filter-group"><span>{label}</span>{values.map(value => <button className={active === value ? "active" : ""} onClick={() => onChange(value)} key={value}>{value}</button>)}</div>;
}

function JobSheet({ job, onClose }: { job: Job | null; onClose: () => void }) {
  return <Sheet open={Boolean(job)} onOpenChange={open => { if (!open) onClose(); }}><SheetContent className="job-sheet sm:max-w-2xl"><SheetHeader><Badge variant={job?.sourceTier === "公司官方" ? "default" : "secondary"}>{job?.sourceTier ?? "来源"}</Badge><SheetTitle>{job?.title ?? "岗位详情"}</SheetTitle><SheetDescription>{job?.company} · {job?.location} · {job?.category}</SheetDescription></SheetHeader>{job && <div className="job-sheet-body"><div className="detail-meta"><span><GraduationCap />{job.education || "学历未注明"}</span><span>{job.experience || "经验未注明"}</span><span>{job.employmentType || "类型未注明"}</span><span>{job.priorityLabel || "其他匹配岗位"}</span><span>入门门槛：{job.entryBarrier || "不可判断"}</span><span>内容完整度：{job.contentCompleteness || "未知"}</span></div><DetailSection title="入门门槛依据" items={job.entryBasis?.length ? job.entryBasis : ["岗位页没有足够证据，不能据此判断录用难度。"]} /><DetailSection title="这个岗位做什么" items={job.responsibilities?.length ? job.responsibilities : [job.workSummary || "请打开原页查看完整职责。"]} /><DetailSection title="任职要求" items={job.requirements?.length ? job.requirements : ["页面未稳定解析出完整要求，请以招聘原页为准。"]} /><section className="detail-section"><h3>能力图谱</h3><div className="capability-list">{(job.capabilityGroups ?? []).map(group => <div key={group.name}><strong>{group.name}</strong><span>{group.signals.join("、")}</span></div>)}{!job.capabilityGroups?.length && <p>只有标题级信号，暂不做更强推断。</p>}</div></section><section className="detail-section"><h3>针对这个岗位的模拟面试准备</h3><p className="generated-note">以下问题由岗位文本生成，不是公司真实面试题。</p><ol className="interview-list">{(job.interviewPrep ?? []).map((item, index) => <li key={`${item.question}-${index}`}><strong>{item.question}</strong><span>{item.basis}</span></li>)}</ol></section><section className="detail-section"><h3>依据与边界</h3><p>匹配分 {job.match}；岗位优先分 {job.priorityScore ?? job.match}。这些是可解释排序，不是录用概率。</p><p>{job.evidenceSnippet || job.verification}</p>{job.qualityFlags?.length > 0 && <p className="quality">需注意：{job.qualityFlags.join("、")}</p>}</section><a className="primary-link" href={job.url} target="_blank" rel="noreferrer">打开招聘原页确认并投递 <ExternalLink /></a></div>}</SheetContent></Sheet>;
}

function DetailSection({ title, items }: { title: string; items: string[] }) {
  return <section className="detail-section"><h3>{title}</h3><ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></section>;
}

function Metric({ icon, label, value, detail }: { icon: React.ReactNode; label: string; value: number; detail: string }) {
  return <Card className="radar-card metric"><CardContent><div>{icon}<span>{label}</span></div><strong>{value}</strong><small>{detail}</small></CardContent></Card>;
}

function EventCard({ item }: { item: IntelItem }) {
  const changes = item.keyChanges?.length ? item.keyChanges : [item.excerpt || "原文摘要不足，请打开来源核对。"];
  return <article className="event-card">
    <header><div><Badge>{item.eventType ?? item.sourceTier}</Badge><Badge variant="outline">{item.company ?? item.domain}</Badge></div><time>{formatTime(item.publishedAt || item.discoveredAt)}</time></header>
    <div className="event-title"><span>{item.sourceTier}</span><h3>{item.project ?? item.title}{item.version && <small>{item.version}</small>}</h3>{item.releaseTitle && item.releaseTitle !== item.title && <p>{item.releaseTitle}</p>}</div>
    <section className="event-facts"><span>来源事实</span><h4>发生了什么</h4><p>{item.whatHappened ?? item.title}</p><h4>原文列出的主要变化</h4><ul>{changes.slice(0, 3).map((change, index) => <li key={`${item.id}-change-${index}`}>{change}</li>)}</ul></section>
    {(item.affectedAreas ?? []).length > 0 && <div className="event-areas">{item.affectedAreas!.map(area => <span key={area}>{area}</span>)}</div>}
    <section className="event-guidance"><span>规则判断</span><div><h4>与你的关系</h4><p>{item.whyItMatters ?? "需要结合你的研究和求职方向判断。"}</p></div><div><h4>建议动作</h4><p>{item.suggestedAction ?? "打开原始来源核对后再决定是否跟进。"}</p></div></section>
    <footer><small>{item.interpretation ?? "当前是旧事件格式；完成刷新后会补齐结构化解释。"}</small><a href={item.url} target="_blank" rel="noreferrer">查看原文 <ExternalLink /></a></footer>
  </article>;
}

function EventRow({ item }: { item: IntelItem }) {
  return <a className="event-row" href={item.url} target="_blank" rel="noreferrer"><div><div className="event-row-badges"><Badge variant="outline">{item.eventType ?? item.sourceTier}</Badge><span>{item.company ?? item.domain}</span></div><h3>{item.project ?? item.title}{item.version ? ` · ${item.version}` : ""}</h3><p>{item.whatHappened ?? item.excerpt ?? "打开原始来源查看详情。"}</p>{item.suggestedAction && <small>建议：{item.suggestedAction}</small>}</div><aside><time>{formatTime(item.publishedAt || item.discoveredAt)}</time><span>{item.domain} <ExternalLink /></span></aside></a>;
}

function IndexedSignalCard({ item }: { item: IntelItem }) {
  return <article className="signal-card"><div className="signal-card-head"><div><Badge>{item.platform ?? "社媒"}</Badge><Badge variant="outline">{item.signalType ?? "普通观点/传闻"}</Badge></div><span>{item.freshness ?? "时间待确认"}</span></div><h3>{item.title}</h3><p>{item.excerpt || "公开索引没有提供摘要，请打开原文查看。"}</p>{(item.company || item.role) && <div className="signal-linkage"><strong>{item.company || "公司待确认"}</strong><span>{item.role || "岗位待确认"}</span></div>}<div className="signal-card-foot"><small>{item.confidence ?? item.verification}</small><a href={item.url} target="_blank" rel="noreferrer">打开原文 <ExternalLink /></a></div></article>;
}

function SavedSignalCard({ item, onDelete }: { item: SavedSocialSignal; onDelete: (id: string) => void }) {
  return <article className="signal-card saved-signal"><div className="signal-card-head"><div><Badge>{item.platform}</Badge><Badge variant="outline">{item.signalType}</Badge></div><button type="button" onClick={() => onDelete(item.id)} aria-label="删除这条链接"><Trash2 /></button></div><h3>{item.title}</h3><p>{item.note || "没有填写备注；打开原文查看内容。"}</p>{(item.company || item.role) && <div className="signal-linkage"><strong>{item.company || "公司待确认"}</strong><span>{item.role || "岗位待确认"}</span></div>}{item.tags.length > 0 && <div className="skill-row">{item.tags.map(tag => <span key={tag}>{tag}</span>)}</div>}<div className="signal-card-foot"><small>{item.confidence} · 保存于 {formatTime(item.createdAt)}</small><a href={item.url} target="_blank" rel="noreferrer">打开原文 <ExternalLink /></a></div></article>;
}

function Empty({ text }: { text: string }) { return <div className="empty">{text}</div>; }
