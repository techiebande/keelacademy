/**
 * Session adapter for managed auth (S2.5).
 *
 * Two implementations behind one interface:
 *
 * - "clerk": real wiring. When CLERK_SECRET_KEY and
 *   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY are both present, sessions come from
 *   Clerk (the school's chosen managed provider) via auth()/currentUser().
 *   The Clerk packages are imported dynamically so a credential-free build
 *   or request never touches them.
 *
 * - "offline": the deterministic fake, per the house offline-determinism
 *   convention (the same role fake_upstream.py plays for the OpenAI API).
 *   It mirrors the semantics of a managed provider: sign-up creates an
 *   identity, sign-in mints a session, sign-out revokes it, and the session
 *   is an HMAC-signed httpOnly cookie the client cannot forge or read. It
 *   is a development stand-in, not a production auth system: pages in this
 *   mode say so, and no password is ever stored (there is nothing to
 *   protect in a local demo). When founder credentials land, the same
 *   routes render Clerk's hosted pages instead.
 *
 * No secret is ever NEXT_PUBLIC: the offline cookie secret and the Clerk
 * secret key live in server env only.
 */

import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export type AuthMode = "keel" | "clerk" | "offline";

export type SessionUser = {
  externalId: string;
  email: string;
  name: string | null;
};

const COOKIE_NAME = "keel_session";
const SESSION_MAX_AGE_S = 7 * 24 * 60 * 60;

export function authMode(): AuthMode {
  if (process.env.KEEL_AUTH_URL && process.env.KEEL_ENROLL_SECRET) return "keel";
  if (process.env.CLERK_SECRET_KEY && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return "clerk";
  }
  return "offline";
}

// ---------------------------------------------------------------------------
// "keel" mode: self-owned auth on the enroll service (schema 0015). The app
// holds only an opaque session token cookie; validation asks the enroll
// service, reached with the same shared secret every other call uses.
// ---------------------------------------------------------------------------

type KeelAuthResult =
  | { state: "ok"; data: Record<string, unknown> }
  | { state: "rejected"; code: string }
  | { state: "unreachable" };

async function keelAuthCall(path: string, body: Record<string, unknown>): Promise<KeelAuthResult> {
  const base = process.env.KEEL_AUTH_URL;
  const secret = process.env.KEEL_ENROLL_SECRET;
  if (!base || !secret) return { state: "unreachable" };
  try {
    const res = await fetch(`${base.replace(/\/$/, "")}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Keel-App-Token": secret },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (res.status === 200) {
      return { state: "ok", data: (await res.json()) as Record<string, unknown> };
    }
    let code = "error";
    try {
      code = ((await res.json()) as { error?: string }).error ?? code;
    } catch {
      // non-JSON error body: keep the generic code
    }
    return { state: "rejected", code };
  } catch {
    return { state: "unreachable" };
  }
}

export async function setKeelSessionCookie(sessionToken: string): Promise<void> {
  const store = await cookies();
  store.set(COOKIE_NAME, sessionToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
}

export async function keelSignIn(
  email: string,
  password: string,
): Promise<KeelAuthResult> {
  return keelAuthCall("/auth/login", { email, password });
}

export async function keelSignUp(
  email: string,
  password: string,
  name: string | null,
): Promise<KeelAuthResult> {
  return keelAuthCall("/auth/signup", { email, password, name });
}

export async function keelResetRequest(email: string): Promise<KeelAuthResult> {
  return keelAuthCall("/auth/reset/request", { email });
}

export async function keelResetConfirm(
  token: string,
  password: string,
): Promise<KeelAuthResult> {
  return keelAuthCall("/auth/reset/confirm", { token, password });
}

export async function keelOauthLogin(
  provider: string,
  subject: string,
  email: string,
  name: string | null,
): Promise<KeelAuthResult> {
  return keelAuthCall("/auth/oauth", { provider, subject, email, name });
}

export async function keelLogout(sessionToken: string): Promise<void> {
  await keelAuthCall("/auth/logout", { session_token: sessionToken });
}

/** OAuth providers actually configured (buttons render only for these). */
export function oauthProviders(): { id: "google" | "github"; label: string }[] {
  const out: { id: "google" | "github"; label: string }[] = [];
  if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
    out.push({ id: "google", label: "Google" });
  }
  if (process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET) {
    out.push({ id: "github", label: "GitHub" });
  }
  return out;
}

/** The session token inside an auth call's result, or null. */
export function keelSessionCookieFromResult(
  res: KeelAuthResult,
): string | null {
  if (res.state !== "ok") return null;
  const token = res.data.session_token;
  return typeof token === "string" && token.length > 0 ? token : null;
}

export async function readKeelSessionCookie(): Promise<string | null> {
  return (await cookies()).get(COOKIE_NAME)?.value ?? null;
}

export async function clearSessionCookie(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

export async function keelSessionUser(): Promise<SessionUser | null> {
  const token = await readKeelSessionCookie();
  if (!token || token.includes(".")) return null; // signed payloads belong to offline mode
  const res = await fetch(
    `${process.env.KEEL_AUTH_URL!.replace(/\/$/, "")}/auth/session`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Keel-App-Token": process.env.KEEL_ENROLL_SECRET!,
      },
      body: JSON.stringify({ session_token: token }),
      cache: "no-store",
    },
  ).then(async (r) =>
    r.ok ? ((await r.json()) as { user?: SessionUser }) : null,
  ).catch(() => null);
  const user = res?.user;
  return user && user.externalId && user.email ? user : null;
}

/** The signed-in identity, or null. Safe on any page. */
export async function getSessionUser(): Promise<SessionUser | null> {
  const mode = authMode();
  if (mode === "keel") {
    return keelSessionUser();
  }
  if (mode === "clerk") {
    const { auth, currentUser } = await import("@clerk/nextjs/server");
    const { userId } = await auth();
    if (!userId) return null;
    const user = await currentUser();
    return {
      externalId: userId,
      email: user?.primaryEmailAddress?.emailAddress ?? "",
      name: user?.fullName ?? null,
    };
  }
  const payload = await readSessionCookie();
  return payload
    ? { externalId: payload.sub, email: payload.email, name: payload.name }
    : null;
}

/** Route gate: redirect signed-out visitors to sign-in, preserving the
 *  destination so the flow returns where it started. */
export async function requireSession(next: string): Promise<SessionUser> {
  const user = await getSessionUser();
  if (!user) {
    redirect(`/sign-in?next=${encodeURIComponent(next)}`);
  }
  return user;
}

/** Check if current session user has admin privileges. */
export function isAdminUser(user: SessionUser | null): boolean {
  if (!user) return false;
  const adminEmails = (process.env.KEEL_ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  const email = user.email.trim().toLowerCase();
  // If specific admin emails configured, check list; default allow staff/admin or dev in offline mode if none configured
  if (adminEmails.length > 0) {
    return adminEmails.includes(email);
  }
  return email.endsWith("@keelacademy.com") || email.endsWith("@keel.test") || email.startsWith("admin");
}

/** Route gate: require admin session. Redirects to sign-in or access denied. */
export async function requireAdminSession(next: string = "/admin/analytics"): Promise<SessionUser> {
  const user = await requireSession(next);
  if (!isAdminUser(user)) {
    redirect(`/?error=admin_access_required`);
  }
  return user;
}

// ---------------------------------------------------------------------------
// Offline fake: cookie mint/verify + JSON identity store
// ---------------------------------------------------------------------------

type OfflinePayload = { sub: string; email: string; name: string | null; exp: number };

const INSECURE_DEFAULT_SECRET =
  "keelacademy-offline-auth-insecure-default (set KEEL_OFFLINE_AUTH_SECRET)";

let warnedInsecureSecret = false;

function offlineSecret(): string {
  const secret = process.env.KEEL_OFFLINE_AUTH_SECRET;
  if (secret) return secret;
  if (!warnedInsecureSecret) {
    warnedInsecureSecret = true;
    console.warn(
      "[auth] KEEL_OFFLINE_AUTH_SECRET is not set; the offline fake is signing " +
        "sessions with a public default. Fine for the local demo, never for production.",
    );
  }
  return INSECURE_DEFAULT_SECRET;
}

function signValue(value: string): string {
  return createHmac("sha256", offlineSecret()).update(value).digest("hex");
}

function constantTimeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  return bufA.length === bufB.length && timingSafeEqual(bufA, bufB);
}

async function readSessionCookie(): Promise<OfflinePayload | null> {
  const raw = (await cookies()).get(COOKIE_NAME)?.value;
  if (!raw || !raw.includes(".")) return null;
  const [encoded, mac] = raw.split(".");
  if (!encoded || !mac) return null;
  if (!constantTimeEqual(signValue(encoded), mac)) return null;
  try {
    const payload = JSON.parse(
      Buffer.from(encoded, "base64url").toString("utf8"),
    ) as OfflinePayload;
    if (typeof payload.sub !== "string" || typeof payload.email !== "string") return null;
    if (typeof payload.exp !== "number" || payload.exp * 1000 < Date.now()) return null;
    return payload;
  } catch {
    return null;
  }
}

export async function setOfflineSessionCookie(user: SessionUser): Promise<void> {
  const store = await cookies();
  const payload: OfflinePayload = {
    sub: user.externalId,
    email: user.email,
    name: user.name,
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_S,
  };
  const encoded = Buffer.from(JSON.stringify(payload)).toString("base64url");
  store.set(COOKIE_NAME, `${encoded}.${signValue(encoded)}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
}

export async function clearOfflineSessionCookie(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

// --- identity store: one JSON file, whole-file read, atomic replace write --

type StoredUser = { externalId: string; email: string; name: string | null };

function storePath(): string {
  return process.env.KEEL_OFFLINE_AUTH_STORE ?? "/tmp/keel-offline-auth.json";
}

export function offlineExternalId(email: string): string {
  return (
    "offline_" +
    createHash("sha256").update(email.trim().toLowerCase()).digest("hex").slice(0, 16)
  );
}

function loadStore(): { users: StoredUser[] } {
  if (!existsSync(/*turbopackIgnore: true*/ storePath())) return { users: [] };
  try {
    const parsed = JSON.parse(readFileSync(/*turbopackIgnore: true*/ storePath(), "utf8"));
    if (Array.isArray(parsed?.users)) return parsed;
  } catch {
    // unreadable store: treat as empty rather than crash the page
  }
  return { users: [] };
}

function saveStore(store: { users: StoredUser[] }): void {
  const path = storePath();
  const tmp = `${path}.tmp-${process.pid}`;
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(tmp, JSON.stringify(store, null, 2), "utf8");
  renameSync(tmp, path);
}

export function offlineSignUp(email: string, name: string | null): StoredUser | "exists" {
  const normalized = email.trim().toLowerCase();
  const store = loadStore();
  if (store.users.some((u) => u.email === normalized)) return "exists";
  const user: StoredUser = {
    externalId: offlineExternalId(normalized),
    email: normalized,
    name: name?.trim() ? name.trim() : null,
  };
  store.users.push(user);
  saveStore(store);
  return user;
}

export function offlineSignIn(email: string): StoredUser | null {
  const normalized = email.trim().toLowerCase();
  const store = loadStore();
  return store.users.find((u) => u.email === normalized) ?? null;
}
