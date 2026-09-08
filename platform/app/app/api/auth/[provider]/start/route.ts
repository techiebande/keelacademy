import { NextRequest, NextResponse } from "next/server";
import { createHmac } from "node:crypto";

/**
 * OAuth start: GET /api/auth/{google|github}/start?next=/path
 *
 * The state parameter is a signed, expiring envelope (HMAC with the app's
 * KEEL_ENROLL_SECRET), so the callback can trust the post-login destination
 * without a server-side store.
 */

const PROVIDERS = {
  google: {
    authorize: "https://accounts.google.com/o/oauth2/v2/auth",
    scope: "openid email profile",
  },
  github: {
    authorize: "https://github.com/login/oauth/authorize",
    scope: "read:user user:email",
  },
} as const;

type ProviderId = keyof typeof PROVIDERS;

function stateSecret(): string {
  return process.env.KEEL_ENROLL_SECRET ?? process.env.KEEL_OFFLINE_AUTH_SECRET ?? "keel-oauth-state-dev";
}

function sign(payload: string): string {
  return createHmac("sha256", stateSecret()).update(payload).digest("base64url");
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ provider: string }> },
) {
  const { provider } = await params;
  const conf = PROVIDERS[provider as ProviderId];
  const idEnv = provider === "google" ? "GOOGLE_CLIENT_ID" : "GITHUB_CLIENT_ID";
  const secretEnv = provider === "google" ? "GOOGLE_CLIENT_SECRET" : "GITHUB_CLIENT_SECRET";
  if (!conf || !process.env[idEnv] || !process.env[secretEnv]) {
    return NextResponse.redirect(new URL("/sign-in?error=mode", request.url));
  }

  const url = new URL(request.url);
  const next = url.searchParams.get("next");
  const safeNext =
    next && next.startsWith("/") && !next.startsWith("//") ? next : "/me";
  const payload = Buffer.from(
    JSON.stringify({ exp: Date.now() + 10 * 60 * 1000, next: safeNext }),
  ).toString("base64url");
  const state = `${payload}.${sign(payload)}`;

  const redirectUri = `${url.origin}/api/auth/${provider}/callback`;
  const authorize = new URL(conf.authorize);
  authorize.searchParams.set("client_id", process.env[idEnv]!);
  authorize.searchParams.set("redirect_uri", redirectUri);
  if (provider === "google") {
    authorize.searchParams.set("response_type", "code");
    authorize.searchParams.set("prompt", "select_account");
  }
  authorize.searchParams.set("scope", conf.scope);
  authorize.searchParams.set("state", state);
  return NextResponse.redirect(authorize);
}
