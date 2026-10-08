import { claimRefresh, isCollectorAuthorized } from "@/lib/radar-db";

export async function POST(request: Request) {
  if (!isCollectorAuthorized(request)) return Response.json({ error: "unauthorized" }, { status: 401 });
  try {
    return Response.json({ request: await claimRefresh() });
  } catch (error) {
    console.error("collector claim failed", error);
    return Response.json({ error: "unavailable" }, { status: 503 });
  }
}
