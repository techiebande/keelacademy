/**
 * Server-side access to the enrollment service
 * (platform/grading/enroll/server.py). Same boundary discipline as the S2.4
 * reader: the app holds no database credential, only KEEL_ENROLL_URL (a
 * plain base URL) and KEEL_ENROLL_SECRET (the shared app token, server env
 * only, never NEXT_PUBLIC, so it cannot reach a client bundle).
 *
 * Every call is server-side only; import exclusively from server components
 * and server actions.
 */

import { cache } from "react";
import type { SessionUser } from "@/lib/auth";

export type Enrollment = {
  unit_id: string;
  status: string;
  enrolled_at: string;
};

export type Rebate = {
  gate_id: string;
  status: "pending" | "earned" | "paid" | "forfeited" | "expired";
  amount_cents: number;
  currency: string;
  pledged_at: string;
  window_ends_at: string;
  earned_at: string | null;
  paid_at: string | null;
  forfeited_at: string | null;
  expired_at: string | null;
};

export type StudentProfile = {
  student_id: number;
  email: string;
  display_name: string | null;
  enrollments: Enrollment[];
  budget: { tokens_cap: number; tokens_used: number } | null;
  rebates: Rebate[];
};

export type OwnSubmission = {
  id: number;
  unit_id: string;
  status: string;
  created_at: string;
  overall: "pass" | "fail" | null;
};

export type UnitPrice = { unit_id: string; amount_cents: number; currency: string };

export type SubscriptionPrice = {
  price_id: string;
  amount_cents: number;
  currency: string;
  interval: string;
};

export type SubscriptionCheckout = {
  transaction_id: string;
  url: string;
  price_id: string;
};

export type SubscriptionStatus = {
  transaction_id: string;
  status: "pending" | "active" | "trialing" | "past_due" | "paused" | "canceled";
};

export type CheckoutSession = {
  stripe_session_id: string;
  url: string;
  amount_cents: number;
  currency: string;
};

export type CheckoutStatus = {
  stripe_session_id: string;
  status: "pending" | "completed" | "expired";
  enrolled: boolean;
};

export type EnrollResult<T> =
  | { state: "ok"; data: T }
  | { state: "unreachable"; detail: string }
  | { state: "rejected"; status: number; code: string };

export function enrollBaseUrl(): string {
  return process.env.KEEL_ENROLL_URL ?? "http://127.0.0.1:8791";
}

function enrollToken(): string | null {
  return process.env.KEEL_ENROLL_SECRET ?? null;
}

async function enrollFetch<T>(path: string, init?: RequestInit): Promise<EnrollResult<T>> {
  const token = enrollToken();
  if (!token) {
    return { state: "rejected", status: 0, code: "app_not_configured" };
  }
  try {
    const res = await fetch(`${enrollBaseUrl()}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "X-Keel-App-Token": token,
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    if (res.ok) {
      return { state: "ok", data: (await res.json()) as T };
    }
    let code = `http_${res.status}`;
    try {
      code = ((await res.json()) as { error?: string }).error ?? code;
    } catch {
      // non-JSON error body: keep the http code
    }
    return { state: "rejected", status: res.status, code };
  } catch (err) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

/**
 * Link the managed-auth identity to a students row (the enrollment bridge).
 * Memoized per request so a page + its actions do not bridge repeatedly.
 * Returns the grading-core student id, or an error shape the caller can
 * surface honestly (409 = this email is linked to a different account).
 */
export const ensureStudent = cache(
  async (user: SessionUser): Promise<EnrollResult<number>> => {
    const result = await enrollFetch<{ student_id: number }>("/auth/bridge", {
      method: "POST",
      body: JSON.stringify({
        external_id: user.externalId,
        email: user.email,
        name: user.name,
      }),
    });
    if (result.state === "ok") return { state: "ok", data: result.data.student_id };
    return result;
  },
);

export function fetchProfile(studentId: number): Promise<EnrollResult<StudentProfile>> {
  return enrollFetch<StudentProfile>(`/students/${studentId}/profile`);
}

export function fetchOwnSubmissions(
  studentId: number,
): Promise<EnrollResult<{ submissions: OwnSubmission[] }>> {
  return enrollFetch<{ submissions: OwnSubmission[] }>(`/students/${studentId}/submissions`);
}

export function fetchPrice(unitId: string): Promise<EnrollResult<UnitPrice>> {
  return enrollFetch<UnitPrice>(`/price?unit=${encodeURIComponent(unitId)}`);
}

export function fetchCheckoutStatus(
  stripeSessionId: string,
): Promise<EnrollResult<CheckoutStatus>> {
  return enrollFetch<CheckoutStatus>(
    `/checkout/status?stripe_session_id=${encodeURIComponent(stripeSessionId)}`,
  );
}

export function createCheckoutSession(input: {
  studentId: number;
  unitId: string;
  successUrl: string;
  cancelUrl: string;
}): Promise<EnrollResult<CheckoutSession>> {
  return enrollFetch<CheckoutSession>("/checkout/session", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      unit_id: input.unitId,
      success_url: input.successUrl,
      cancel_url: input.cancelUrl,
    }),
  });
}

export function fetchSubscriptionPrice(): Promise<EnrollResult<SubscriptionPrice>> {
  return enrollFetch<SubscriptionPrice>("/subscription/price");
}

export function createSubscriptionCheckout(input: {
  studentId: number;
  successUrl: string;
}): Promise<EnrollResult<SubscriptionCheckout>> {
  return enrollFetch<SubscriptionCheckout>("/checkout/subscription", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      success_url: input.successUrl,
    }),
  });
}

export function fetchSubscriptionStatus(
  transactionId: string,
): Promise<EnrollResult<SubscriptionStatus>> {
  return enrollFetch<SubscriptionStatus>(
    `/subscription/status?transaction_id=${encodeURIComponent(transactionId)}`,
  );
}

export function formatPrice(amountCents: number, currency: string): string {
  const symbol = currency.toLowerCase() === "usd" ? "$" : `${currency.toUpperCase()} `;
  return `${symbol}${(amountCents / 100).toFixed(amountCents % 100 === 0 ? 0 : 2)}`;
}
