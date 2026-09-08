import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/auth";
import { ensureStudent } from "@/lib/enroll";
import { sendSimulationTurn } from "@/lib/simulation";

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

  let body: { simulation_id?: number; message?: string } = {};
  try {
    const text = await req.text();
    if (text) {
      body = JSON.parse(text);
    }
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (!body.simulation_id || !body.message || !body.message.trim()) {
    return NextResponse.json(
      { error: "missing_fields", message: "simulation_id and message are required" },
      { status: 422 },
    );
  }

  const res = await sendSimulationTurn({
    simulationId: body.simulation_id,
    studentId: bridged.data,
    message: body.message,
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
