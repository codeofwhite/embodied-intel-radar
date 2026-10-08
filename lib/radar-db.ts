import { env } from "cloudflare:workers";

export interface SnapshotPayload {
  generatedAt: string;
  jobs: Record<string, unknown>;
  events: Record<string, unknown>;
  social: Record<string, unknown>;
  quotes: Record<string, unknown>;
  refresh: Record<string, unknown>;
  requestId?: string | null;
}

export interface SocialSignalInput {
  platform: "X" | "小红书";
  url: string;
  title: string;
  note: string;
  signalType: string;
  company: string;
  role: string;
  tags: string[];
  publishedAt?: string | null;
}

export interface SocialSignalRecord extends SocialSignalInput {
  id: string;
  createdAt: string;
  confidence: "个人保存·待核实";
}

type SocialSignalRow = {
  id: string;
  platform: "X" | "小红书";
  url: string;
  title: string;
  note: string;
  signal_type: string;
  company: string;
  role: string;
  tags_json: string;
  published_at: string | null;
  created_at: string;
};

function database(): D1Database {
  if (!env.DB) throw new Error("D1 binding DB is unavailable");
  return env.DB;
}

export function isCollectorAuthorized(request: Request): boolean {
  const configured = env.RADAR_INGEST_SECRET;
  if (!configured) return false;
  return (request.headers.get("authorization") ?? "") === `Bearer ${configured}`;
}

export async function latestSnapshot(): Promise<SnapshotPayload | null> {
  const row = await database().prepare(
    `SELECT generated_at, jobs_json, events_json, social_json, quotes_json, refresh_json
     FROM radar_snapshots ORDER BY id DESC LIMIT 1`,
  ).first<Record<string, string>>();
  if (!row) return null;
  return {
    generatedAt: row.generated_at,
    jobs: JSON.parse(row.jobs_json),
    events: JSON.parse(row.events_json),
    social: JSON.parse(row.social_json),
    quotes: JSON.parse(row.quotes_json),
    refresh: JSON.parse(row.refresh_json),
  };
}

export async function saveSnapshot(payload: SnapshotPayload): Promise<void> {
  const db = database();
  const receivedAt = new Date().toISOString();
  const insert = db.prepare(
    `INSERT INTO radar_snapshots
      (generated_at, received_at, jobs_json, events_json, social_json, quotes_json, refresh_json)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    payload.generatedAt,
    receivedAt,
    JSON.stringify(payload.jobs),
    JSON.stringify(payload.events),
    JSON.stringify(payload.social),
    JSON.stringify(payload.quotes),
    JSON.stringify(payload.refresh),
  );
  if (payload.requestId) {
    const status = String((payload.refresh as { status?: string }).status ?? "succeeded");
    const finish = db.prepare(
      `UPDATE refresh_requests SET status = ?, finished_at = ?, message = ? WHERE id = ?`,
    ).bind(status, receivedAt, "线上数据已更新", payload.requestId);
    await db.batch([insert, finish]);
  } else {
    await insert.run();
  }
}

export async function queueRefresh(): Promise<Record<string, unknown>> {
  const db = database();
  const active = await db.prepare(
    `SELECT id, status, requested_at, claimed_at, finished_at, message
     FROM refresh_requests WHERE status IN ('queued', 'running')
     ORDER BY requested_at DESC LIMIT 1`,
  ).first<Record<string, string | null>>();
  if (active) return normalizeRefresh(active);
  const id = crypto.randomUUID();
  const requestedAt = new Date().toISOString();
  await db.prepare(
    `INSERT INTO refresh_requests (id, status, requested_at) VALUES (?, 'queued', ?)`,
  ).bind(id, requestedAt).run();
  return { id, status: "queued", requestedAt };
}

export async function getRefresh(id: string): Promise<Record<string, unknown> | null> {
  const row = await database().prepare(
    `SELECT id, status, requested_at, claimed_at, finished_at, message
     FROM refresh_requests WHERE id = ?`,
  ).bind(id).first<Record<string, string | null>>();
  return row ? normalizeRefresh(row) : null;
}

export async function claimRefresh(): Promise<Record<string, unknown> | null> {
  const db = database();
  const row = await db.prepare(
    `SELECT id, status, requested_at, claimed_at, finished_at, message
     FROM refresh_requests WHERE status = 'queued' ORDER BY requested_at LIMIT 1`,
  ).first<Record<string, string | null>>();
  if (!row) return null;
  const claimedAt = new Date().toISOString();
  const result = await db.prepare(
    `UPDATE refresh_requests SET status = 'running', claimed_at = ?, message = ?
     WHERE id = ? AND status = 'queued'`,
  ).bind(claimedAt, "本地采集器正在刷新", row.id).run();
  if (!result.meta.changes) return null;
  return { ...normalizeRefresh(row), status: "running", claimedAt, message: "本地采集器正在刷新" };
}

export async function listSocialSignals(limit = 100): Promise<SocialSignalRecord[]> {
  const result = await database().prepare(
    `SELECT id, platform, url, title, note, signal_type, company, role,
            tags_json, published_at, created_at
     FROM social_signals ORDER BY created_at DESC LIMIT ?`,
  ).bind(limit).all<SocialSignalRow>();
  return (result.results ?? []).map(normalizeSocialSignal);
}

export async function saveSocialSignal(input: SocialSignalInput): Promise<SocialSignalRecord> {
  const id = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  await database().prepare(
    `INSERT INTO social_signals
      (id, platform, url, title, note, signal_type, company, role, tags_json, published_at, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id,
    input.platform,
    input.url,
    input.title,
    input.note,
    input.signalType,
    input.company,
    input.role,
    JSON.stringify(input.tags),
    input.publishedAt ?? null,
    createdAt,
  ).run();
  return { ...input, id, createdAt, confidence: "个人保存·待核实" };
}

export async function deleteSocialSignal(id: string): Promise<boolean> {
  const result = await database().prepare(
    "DELETE FROM social_signals WHERE id = ?",
  ).bind(id).run();
  return Boolean(result.meta.changes);
}

function normalizeSocialSignal(row: SocialSignalRow): SocialSignalRecord {
  let tags: string[] = [];
  try {
    const value = JSON.parse(row.tags_json);
    if (Array.isArray(value)) tags = value.filter((item): item is string => typeof item === "string");
  } catch {
    tags = [];
  }
  return {
    id: row.id,
    platform: row.platform,
    url: row.url,
    title: row.title,
    note: row.note,
    signalType: row.signal_type,
    company: row.company,
    role: row.role,
    tags,
    publishedAt: row.published_at,
    createdAt: row.created_at,
    confidence: "个人保存·待核实",
  };
}

function normalizeRefresh(row: Record<string, string | null>): Record<string, unknown> {
  return {
    id: row.id,
    status: row.status,
    requestedAt: row.requested_at,
    claimedAt: row.claimed_at,
    finishedAt: row.finished_at,
    message: row.message,
  };
}
