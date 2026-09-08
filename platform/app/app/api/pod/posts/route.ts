import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { fetchPodPosts, submitPodPost } from "@/lib/practice";

export async function GET(req: Request) {
  const user = await getSessionUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const podIdStr = searchParams.get("pod_id");
  const weekStr = searchParams.get("week");

  if (!podIdStr || !/^\d+$/.test(podIdStr)) {
    return NextResponse.json({ error: "pod_id required" }, { status: 400 });
  }

  const weekNumber = weekStr && /^\d+$/.test(weekStr) ? parseInt(weekStr, 10) : undefined;
  const res = await fetchPodPosts(parseInt(podIdStr, 10), weekNumber);

  if (res.state === "ok") {
    return NextResponse.json(res.data, { status: 200 });
  }
  if (res.state === "unreachable") {
    return NextResponse.json(
      { error: "service_unreachable", detail: res.detail },
      { status: 502 },
    );
  }
  return NextResponse.json(
    { error: res.code, message: res.message },
    { status: res.status },
  );
}

export async function POST(req: Request) {
  const user = await getSessionUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const bridged = await ensureStudent(user);
  if (bridged.state !== "ok") {
    return NextResponse.json(
      { error: "grading profile unavailable" },
      { status: 502 },
    );
  }

  let body: {
    pod_id?: number;
    week_number?: number;
    shipped_text?: string;
    broke_text?: string;
    next_text?: string;
  };

  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (!body.pod_id || typeof body.pod_id !== "number") {
    return NextResponse.json({ error: "pod_id required" }, { status: 422 });
  }
  if (!body.week_number || typeof body.week_number !== "number" || body.week_number < 1) {
    return NextResponse.json({ error: "week_number >= 1 required" }, { status: 422 });
  }
  if (!body.shipped_text || typeof body.shipped_text !== "string" || !body.shipped_text.trim()) {
    return NextResponse.json({ error: "shipped_text required" }, { status: 422 });
  }
  if (!body.broke_text || typeof body.broke_text !== "string" || !body.broke_text.trim()) {
    return NextResponse.json({ error: "broke_text required" }, { status: 422 });
  }
  if (!body.next_text || typeof body.next_text !== "string" || !body.next_text.trim()) {
    return NextResponse.json({ error: "next_text required" }, { status: 422 });
  }

  const res = await submitPodPost({
    studentId: bridged.data,
    podId: body.pod_id,
    weekNumber: body.week_number,
    shippedText: body.shipped_text,
    brokeText: body.broke_text,
    nextText: body.next_text,
  });

  if (res.state === "ok") {
    return NextResponse.json(res.data, { status: 200 });
  }
  if (res.state === "unreachable") {
    return NextResponse.json(
      { error: "service_unreachable", detail: res.detail },
      { status: 502 },
    );
  }
  return NextResponse.json(
    { error: res.code, message: res.message },
    { status: res.status },
  );
}
