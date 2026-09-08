import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { askConcierge } from "@/lib/practice";

export async function POST(req: Request) {
  const user = await getSessionUser();
  if (!user) {
    return NextResponse.json(
      { error: "not_signed_in", message: "Sign in required" },
      { status: 401 },
    );
  }

  const studentRes = await ensureStudent(user);
  if (studentRes.state !== "ok") {
    return NextResponse.json(
      { error: "student_bridge_failed", message: "Unable to load student profile" },
      { status: 500 },
    );
  }

  try {
    const body = await req.json();
    const unitId = body.unit_id ?? body.unitId;
    const question = body.question;

    if (!unitId || !question || typeof question !== "string" || !question.trim()) {
      return NextResponse.json(
        { error: "invalid_payload", message: "unit_id and question required" },
        { status: 422 },
      );
    }

    const res = await askConcierge({
      studentId: studentRes.data,
      unitId: String(unitId),
      question: question.trim(),
    });

    if (res.state === "ok") {
      return NextResponse.json(res.data);
    }
    if (res.state === "unreachable") {
      return NextResponse.json(
        { error: "service_unreachable", detail: res.detail },
        { status: 502 },
      );
    }
    return NextResponse.json(
      { error: res.code, message: res.message },
      { status: res.status || 500 },
    );
  } catch (err) {
    return NextResponse.json(
      { error: "bad_request", detail: err instanceof Error ? err.message : String(err) },
      { status: 400 },
    );
  }
}
