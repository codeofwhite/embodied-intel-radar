import { isCollectorAuthorized, saveSnapshot, type SnapshotPayload } from "@/lib/radar-db";

const MAX_BYTES = 2_000_000;

export async function POST(request: Request) {
  if (!isCollectorAuthorized(request)) return Response.json({ error: "unauthorized" }, { status: 401 });
  const length = Number(request.headers.get("content-length") ?? 0);
  if (length > MAX_BYTES) return Response.json({ error: "payload_too_large" }, { status: 413 });
  try {
    const payload = await request.json() as SnapshotPayload;
    if (!payload.generatedAt || !payload.jobs || !payload.events || !payload.quotes || !payload.refresh) {
      return Response.json({ error: "invalid_payload" }, { status: 400 });
    }
    await saveSnapshot(payload);
    return Response.json({ ok: true, receivedAt: new Date().toISOString() });
  } catch (error) {
    console.error("snapshot ingest failed", error);
    return Response.json({ error: "ingest_failed" }, { status: 500 });
  }
}
