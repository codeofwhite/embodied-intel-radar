import { getRefresh } from "@/lib/radar-db";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await context.params;
    const refresh = await getRefresh(id);
    if (!refresh) return Response.json({ status: "missing" }, { status: 404 });
    return Response.json(refresh, { headers: { "cache-control": "no-store" } });
  } catch (error) {
    console.error("refresh status failed", error);
    return Response.json({ status: "unavailable" }, { status: 503 });
  }
}
