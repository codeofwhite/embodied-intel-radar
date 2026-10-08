import { queueRefresh } from "@/lib/radar-db";

export async function POST() {
  try {
    return Response.json(await queueRefresh(), { status: 202 });
  } catch (error) {
    console.error("refresh queue failed", error);
    return Response.json({ status: "unavailable", message: "刷新队列暂不可用" }, { status: 503 });
  }
}
