"use server";

/**
 * Auth + checkout server actions (S2.5). Every action re-checks the session
 * server-side: a Server Action is reachable by direct POST, so the session
 * check lives here, not only in the page that rendered the form.
 */

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import {
  authMode,
  clearOfflineSessionCookie,
  clearSessionCookie,
  getSessionUser,
  keelLogout,
  keelResetConfirm,
  keelResetRequest,
  keelSessionCookieFromResult,
  keelSignIn,
  keelSignUp,
  offlineSignIn,
  offlineSignUp,
  readKeelSessionCookie,
  setKeelSessionCookie,
  setOfflineSessionCookie,
} from "@/lib/auth";
import {
  createSubscriptionCheckout,
  ensureStudent,
} from "@/lib/enroll";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Only same-app paths may be used as a post-login destination. */
function safeNext(raw: FormDataEntryValue | null): string {
  const value = typeof raw === "string" ? raw : "";
  return value.startsWith("/") && !value.startsWith("//") ? value : "/me";
}

function loginError(path: string, error: string, email?: string): never {
  const params = new URLSearchParams({ error });
  if (email) params.set("email", email);
  redirect(`${path}?${params.toString()}`);
}

export async function offlineSignInAction(formData: FormData): Promise<void> {
  if (authMode() !== "offline") {
    redirect("/sign-in?error=mode");
  }
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const next = safeNext(formData.get("next"));
  if (!EMAIL_RE.test(email)) {
    loginError("/sign-in", "invalid-email", email);
  }
  const user = offlineSignIn(email);
  if (!user) {
    loginError("/sign-in", "unknown", email);
  }
  await setOfflineSessionCookie({
    externalId: user.externalId,
    email: user.email,
    name: user.name,
  });
  redirect(next);
}

export async function offlineSignUpAction(formData: FormData): Promise<void> {
  if (authMode() !== "offline") {
    redirect("/sign-up?error=mode");
  }
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const name = String(formData.get("name") ?? "").trim();
  const next = safeNext(formData.get("next"));
  if (!EMAIL_RE.test(email)) {
    loginError("/sign-up", "invalid-email", email);
  }
  if (email.length > 320 || name.length > 100) {
    loginError("/sign-up", "invalid", email);
  }
  const created = offlineSignUp(email, name || null);
  if (created === "exists") {
    loginError("/sign-up", "exists", email);
  }
  await setOfflineSessionCookie({
    externalId: created.externalId,
    email: created.email,
    name: created.name,
  });
  redirect(next);
}

export async function signOutAction(): Promise<void> {
  if (authMode() === "keel") {
    const token = await readKeelSessionCookie();
    if (token) {
      await keelLogout(token);
    }
    await clearSessionCookie();
  } else if (authMode() === "offline") {
    await clearOfflineSessionCookie();
  }
  redirect("/");
}

// ---------------------------------------------------------------------------
// "keel" mode actions (self-owned auth, schema 0015)
// ---------------------------------------------------------------------------

export async function keelSignInAction(formData: FormData): Promise<void> {
  if (authMode() !== "keel") {
    redirect("/sign-in?error=mode");
  }
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));
  if (!EMAIL_RE.test(email)) {
    loginError("/sign-in", "invalid-email", email);
  }
  const res = await keelSignIn(email, password);
  const cookie = keelSessionCookieFromResult(res);
  if (!cookie) {
    loginError("/sign-in", res.state === "rejected" ? res.code : "unreachable", email);
  }
  await setKeelSessionCookie(cookie);
  redirect(next);
}

export async function keelSignUpAction(formData: FormData): Promise<void> {
  if (authMode() !== "keel") {
    redirect("/sign-up?error=mode");
  }
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const name = String(formData.get("name") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));
  if (!EMAIL_RE.test(email)) {
    loginError("/sign-up", "invalid-email", email);
  }
  if (password.length < 10) {
    loginError("/sign-up", "weak-password", email);
  }
  const res = await keelSignUp(email, password, name || null);
  const cookie = keelSessionCookieFromResult(res);
  if (!cookie) {
    loginError("/sign-up", res.state === "rejected" ? res.code : "unreachable", email);
  }
  await setKeelSessionCookie(cookie);
  redirect(next);
}

export async function resetRequestAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  if (!EMAIL_RE.test(email)) {
    loginError("/reset-password/request", "invalid-email", email);
  }
  await keelResetRequest(email);
  // Always the same outcome: the page says what to check for, without
  // revealing whether the address has an account.
  redirect("/reset-password/request?sent=1");
}

export async function resetConfirmAction(formData: FormData): Promise<void> {
  const token = String(formData.get("token") ?? "");
  const password = String(formData.get("password") ?? "");
  if (password.length < 10) {
    loginError(`/reset-password/confirm?token=${encodeURIComponent(token)}`, "weak-password");
  }
  const res = await keelResetConfirm(token, password);
  if (res.state !== "ok") {
    loginError("/reset-password/confirm", res.state === "rejected" ? res.code : "unreachable");
  }
  redirect("/sign-in?reset=done");
}

/**
 * Start a Stripe Checkout session for one unit and send the student to the
 * hosted payment page (real Stripe in production, the offline fake in
 * credential-free environments). The {CHECKOUT_SESSION_ID} placeholder in
 * success_url is substituted by Stripe itself at redirect time.
 */
/**
 * Start a Paddle subscription checkout for the all-access plan (owner
 * decision 2026-09-07: a monthly all-access subscription replaces per-unit
 * pricing; enrollment follows the subscription). The {TRANSACTION_ID}
 * placeholder in success_url is substituted by Paddle itself at redirect
 * time, the same pattern Stripe uses with {CHECKOUT_SESSION_ID}.
 */
export async function startSubscriptionAction(): Promise<void> {
  const user = await getSessionUser();
  if (!user) {
    redirect(`/sign-in?next=${encodeURIComponent(`/checkout`)}`);
  }
  const bridged = await ensureStudent(user);
  if (bridged.state !== "ok") {
    redirect(
      `/checkout?error=${bridged.state === "rejected" ? bridged.code : "unreachable"}`,
    );
  }
  const headerList = await headers();
  const host = headerList.get("x-forwarded-host") ?? headerList.get("host") ?? "127.0.0.1:3000";
  const proto = headerList.get("x-forwarded-proto") ?? "http";
  const origin = `${proto}://${host}`;

  const checkout = await createSubscriptionCheckout({
    studentId: bridged.data,
    successUrl: `${origin}/checkout/success?transaction_id={TRANSACTION_ID}`,
  });
  if (checkout.state !== "ok") {
    redirect(
      `/checkout?error=${checkout.state === "rejected" ? checkout.code : "unreachable"}`,
    );
  }
  redirect(checkout.data.url);
}

export async function createSubscriptionCheckoutAction(): Promise<
  { state: "ok"; transactionId: string; url: string } | { state: "rejected"; code: string }
> {
  const user = await getSessionUser();
  if (!user) {
    return { state: "rejected", code: "unauthenticated" };
  }
  const bridged = await ensureStudent(user);
  if (bridged.state !== "ok") {
    return {
      state: "rejected",
      code: bridged.state === "rejected" ? bridged.code : "unreachable",
    };
  }
  const headerList = await headers();
  const host = headerList.get("x-forwarded-host") ?? headerList.get("host") ?? "127.0.0.1:3000";
  const proto = headerList.get("x-forwarded-proto") ?? "http";
  const origin = `${proto}://${host}`;

  const checkout = await createSubscriptionCheckout({
    studentId: bridged.data,
    successUrl: `${origin}/checkout/success?transaction_id={TRANSACTION_ID}`,
  });
  if (checkout.state !== "ok") {
    return {
      state: "rejected",
      code: checkout.state === "rejected" ? checkout.code : "unreachable",
    };
  }
  return {
    state: "ok",
    transactionId: checkout.data.transaction_id,
    url: checkout.data.url,
  };
}
