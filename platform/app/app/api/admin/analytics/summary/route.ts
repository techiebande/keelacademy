import { NextResponse } from "next/server";
import { getSessionUser, isAdminUser } from "@/lib/auth";
import { fetchAnalyticsSummary } from "@/lib/analytics";

export async function GET(req: Request) {
  // Check authorization: either internal admin token in header OR signed in admin session
  const authHeader = req.headers.get("Authorization") || req.headers.get("X-Keel-Admin-Token") || req.headers.get("X-Keel-App-Token");
  const serverToken = process.env.KEEL_ENROLL_SECRET;

  let isAuthed = false;
  if (serverToken && authHeader && (authHeader === serverToken || authHeader === `Bearer ${serverToken}`)) {
    isAuthed = true;
  } else {
    const user = await getSessionUser();
    if (user && isAdminUser(user)) {
      isAuthed = true;
    } else if (!user) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    } else {
      return NextResponse.json({ error: "forbidden_admin_required" }, { status: 403 });
    }
  }

  if (!isAuthed) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const res = await fetchAnalyticsSummary();
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
