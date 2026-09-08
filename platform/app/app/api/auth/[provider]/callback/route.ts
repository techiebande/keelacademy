import { NextRequest, NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "node:crypto";
import { setKeelSessionCookie, keelOauthLogin } from "@/lib/auth";

/**
 * OAuth callback: GET /api/auth/{google|github}/callback?code=...&state=...
 *
 * Verifies the signed state envelope, exchanges the code server-side (the
 * client secrets never leave the server), resolves a stable subject id plus a
 * provider-verified email, and mints a keel session through the enroll
 * service's /auth/oauth.
 */

function stateSecret(): string {
  return process.env.KEEL_ENROLL_SECRET ?? process.env.KEEL_OFFLINE_AUTH_SECRET ?? "keel-oauth-state-dev";
}

function verifyState(raw: string): { next: string } | null {
  if (!raw.includes(".")) return null;
  const [payload, mac] = raw.split(".");
  const expected = createHmac("sha256", stateSecret()).update(payload).digest("base64url");
  const a = Buffer.from(mac);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (typeof parsed.exp !== "number" || parsed.exp < Date.now()) return null;
    const next = parsed.next;
    return next && typeof next === "string" && next.startsWith("/") && !next.startsWith("//")
      ? { next }
      : null;
  } catch {
    return null;
  }
}

type OAuthIdentity = { subject: string; email: string; name: string | null };

async function googleIdentity(code: string, redirectUri: string): Promise<OAuthIdentity | null> {
  const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: process.env.GOOGLE_CLIENT_ID!,
      client_secret: process.env.GOOGLE_CLIENT_SECRET!,
      redirect_uri: redirectUri,
      grant_type: "authorization_code",
    }),
  });
  if (!tokenRes.ok) return null;
  const tokens = (await tokenRes.json()) as { id_token?: string; access_token?: string };
  if (tokens.id_token) {
    const [, payloadB64] = tokens.id_token.split(".");
    try {
      const claims = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
      if (claims.sub && claims.email && claims.email_verified !== false) {
        return { subject: String(claims.sub), email: claims.email, name: claims.name ?? null };
      }
    } catch {
      // fall through to the userinfo endpoint
    }
  }
  if (!tokens.access_token) return null;
  const info = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (!info?.sub || !info?.email) return null;
  return { subject: String(info.sub), email: info.email, name: info.name ?? null };
}

async function githubIdentity(code: string, redirectUri: string): Promise<OAuthIdentity | null> {
  const tokenRes = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      code,
      client_id: process.env.GITHUB_CLIENT_ID!,
      client_secret: process.env.GITHUB_CLIENT_SECRET!,
      redirect_uri: redirectUri,
    }),
  });
  if (!tokenRes.ok) return null;
  const tokens = (await tokenRes.json()) as { access_token?: string };
  if (!tokens.access_token) return null;
  const headers = {
    Authorization: `Bearer ${tokens.access_token}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "keelacademy-app",
  };
  const user = await fetch("https://api.github.com/user", { headers })
    .then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (!user?.id) return null;
  let email: string | undefined = typeof user.email === "string" ? user.email : undefined;
  if (!email) {
    const emails = await fetch("https://api.github.com/user/emails", { headers })
      .then((r) => (r.ok ? (r.json() as Promise<{ email: string; primary: boolean; verified: boolean }[]>) : null))
      .catch(() => null);
    email = emails?.find((e) => e.primary && e.verified)?.email ?? emails?.find((e) => e.verified)?.email;
  }
  if (!email) return null;
  return { subject: String(user.id), email, name: user.name ?? user.login ?? null };
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ provider: string }> },
) {
  const { provider } = await params;
  if (provider !== "google" && provider !== "github") {
    return NextResponse.redirect(new URL("/sign-in?error=oauth", request.url));
  }
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = verifyState(url.searchParams.get("state") ?? "");
  if (!code || !state) {
    return NextResponse.redirect(new URL("/sign-in?error=oauth", request.url));
  }

  const redirectUri = `${url.origin}/api/auth/${provider}/callback`;
  const identity =
    provider === "google"
      ? await googleIdentity(code, redirectUri)
      : await githubIdentity(code, redirectUri);
  if (!identity) {
    return NextResponse.redirect(new URL("/sign-in?error=oauth", request.url));
  }

  const res = await keelOauthLogin(provider, identity.subject, identity.email, identity.name);
  const token = res.state === "ok" ? res.data.session_token : null;
  if (typeof token !== "string" || !token) {
    const code2 = res.state === "rejected" ? res.code : "unreachable";
    return NextResponse.redirect(new URL(`/sign-in?error=${encodeURIComponent(code2)}`, request.url));
  }
  await setKeelSessionCookie(token);
  return NextResponse.redirect(new URL(state.next, request.url));
}
