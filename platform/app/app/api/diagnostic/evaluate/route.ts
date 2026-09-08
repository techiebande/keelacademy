import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { evaluateDiagnostic } from "@/lib/practice";

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

  let body: { diagnostic_id?: string; answers?: Record<string, string> };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (!body.answers || typeof body.answers !== "object") {
    return NextResponse.json({ error: "answers object required" }, { status: 422 });
  }

  const res = await evaluateDiagnostic({
    studentId: bridged.data,
    diagnosticId: body.diagnostic_id,
    answers: body.answers,
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
