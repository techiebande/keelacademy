import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { publishGalleryProject } from "@/lib/gallery";

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
    submission_id?: number;
    title?: string;
    description?: string;
    repo_url?: string;
    demo_url?: string;
    walkthrough_video_url?: string;
  } = {};

  try {
    const text = await req.text();
    if (text) {
      body = JSON.parse(text);
    }
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (!body.submission_id || !body.title || !body.description) {
    return NextResponse.json(
      { error: "missing_required_fields", message: "submission_id, title, and description are required" },
      { status: 422 },
    );
  }

  const res = await publishGalleryProject({
    studentId: bridged.data,
    submissionId: body.submission_id,
    title: body.title,
    description: body.description,
    repoUrl: body.repo_url,
    demoUrl: body.demo_url,
    walkthroughVideoUrl: body.walkthrough_video_url,
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
