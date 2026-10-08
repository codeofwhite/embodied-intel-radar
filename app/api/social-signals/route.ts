import { z } from "zod";
import {
  deleteSocialSignal,
  listSocialSignals,
  saveSocialSignal,
} from "@/lib/radar-db";

export const dynamic = "force-dynamic";

const MAX_BYTES = 20_000;
const signalTypes = [
  "招人/内推",
  "面试经验",
  "岗位能力画像",
  "薪酬与工作强度",
  "团队方向变化",
  "普通观点/传闻",
] as const;

const createSchema = z.object({
  url: z.string().trim().min(1).max(2_000),
  title: z.string().trim().max(160).optional().default(""),
  note: z.string().trim().max(1_000).optional().default(""),
  signalType: z.enum(signalTypes).optional().default("普通观点/传闻"),
  company: z.string().trim().max(80).optional().default(""),
  role: z.string().trim().max(100).optional().default(""),
  tags: z.array(z.string().trim().min(1).max(30)).max(10).optional().default([]),
  publishedAt: z.string().datetime().nullable().optional(),
});

const deleteSchema = z.object({ id: z.string().uuid() });

function platformFromUrl(value: string): { platform: "X" | "小红书"; url: string } {
  const parsed = new URL(value);
  if (parsed.protocol !== "https:") throw new Error("unsupported_url");
  const host = parsed.hostname.toLowerCase();
  if (host === "x.com" || host.endsWith(".x.com") || host === "twitter.com" || host.endsWith(".twitter.com")) {
    return { platform: "X", url: parsed.toString() };
  }
  if (host === "xiaohongshu.com" || host.endsWith(".xiaohongshu.com") || host === "xhslink.com" || host.endsWith(".xhslink.com")) {
    return { platform: "小红书", url: parsed.toString() };
  }
  throw new Error("unsupported_url");
}

function payloadTooLarge(request: Request): boolean {
  return Number(request.headers.get("content-length") ?? 0) > MAX_BYTES;
}

export async function GET() {
  try {
    return Response.json(
      { items: await listSocialSignals() },
      { headers: { "cache-control": "no-store" } },
    );
  } catch (error) {
    console.error("social signals read failed", error);
    return Response.json({ error: "social_signals_unavailable" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  if (payloadTooLarge(request)) return Response.json({ error: "payload_too_large" }, { status: 413 });
  try {
    const parsed = createSchema.safeParse(await request.json());
    if (!parsed.success) return Response.json({ error: "invalid_payload" }, { status: 400 });
    const target = platformFromUrl(parsed.data.url);
    const signal = await saveSocialSignal({
      ...parsed.data,
      ...target,
      title: parsed.data.title || `${target.platform} 就业线索`,
      tags: [...new Set(parsed.data.tags)],
    });
    return Response.json({ signal }, { status: 201 });
  } catch (error) {
    if (error instanceof Error && error.message === "unsupported_url") {
      return Response.json({ error: "only_x_or_xiaohongshu_https_urls" }, { status: 400 });
    }
    if (String(error).toLowerCase().includes("unique")) {
      return Response.json({ error: "url_already_saved" }, { status: 409 });
    }
    console.error("social signal save failed", error);
    return Response.json({ error: "social_signal_save_failed" }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  if (payloadTooLarge(request)) return Response.json({ error: "payload_too_large" }, { status: 413 });
  try {
    const parsed = deleteSchema.safeParse(await request.json());
    if (!parsed.success) return Response.json({ error: "invalid_payload" }, { status: 400 });
    const deleted = await deleteSocialSignal(parsed.data.id);
    if (!deleted) return Response.json({ error: "not_found" }, { status: 404 });
    return Response.json({ ok: true });
  } catch (error) {
    console.error("social signal delete failed", error);
    return Response.json({ error: "social_signal_delete_failed" }, { status: 500 });
  }
}
