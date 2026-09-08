import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { unpublishGalleryProject } from "@/lib/gallery";

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
    project_id?: number;
    unit_id?: string;
  } = {};

  try {
    const text = await req.text();
    if (text) {
      body = JSON.parse(text);
    }
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (body.project_id === undefined && !body.unit_id) {
    return NextResponse.json(
      { error: "missing_identifier", message: "project_id or unit_id required" },
      { status: 422 },
    );
  }

  const res = await unpublishGalleryProject({
    studentId: bridged.data,
    projectId: body.project_id,
    unitId: body.unit_id,
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
