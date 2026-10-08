import { latestSnapshot } from "@/lib/radar-db";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const snapshot = await latestSnapshot();
    if (!snapshot) return Response.json({ status: "empty" }, { status: 404 });
    return Response.json(snapshot, { headers: { "cache-control": "no-store" } });
  } catch (error) {
    console.error("snapshot read failed", error);
    return Response.json({ status: "unavailable" }, { status: 503 });
  }
}
