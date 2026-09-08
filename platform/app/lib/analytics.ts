/**
 * Server-side client for the Analytics & Drop-off service (S4.7)
 * (platform/grading/analytics/engine.py via practice/server.py).
 *
 * Exposes:
 * - Macro funnel conversions
 * - High-level operations summary
 * - Per-unit drop-off & friction metrics
 * - Single unit friction drilldown
 *
 * Security: Uses KEEL_PRACTICE_URL and KEEL_ENROLL_SECRET from server environment only.
 */

export type FunnelStage = {
  id: string;
  name: string;
  count: number;
  conversion_pct: number;
  drop_off_pct: number;
};

export type MacroFunnelResponse = {
  ok: boolean;
  total_enrolled: number;
  stages: FunnelStage[];
  generated_at: string;
};

export type UnitFrictionRecord = {
  unit_id: string;
  title: string;
  phase: number;
  starts_count: number;
  completions_count: number;
  drop_off_rate_pct: number;
  median_time_to_clear_hrs: number;
  avg_attempts_to_pass: number;
  retrieval_first_try_fail_rate_pct: number;
  concierge_turn_volume: number;
  friction_score: number;
};

export type DropoffBreakdownResponse = {
  ok: boolean;
  phase: number | null;
  total_units_tracked: number;
  top_bottleneck_unit: UnitFrictionRecord | null;
  units: UnitFrictionRecord[];
  generated_at: string;
};

export type OperationsSummaryResponse = {
  ok: boolean;
  total_enrolled_students: number;
  active_30d_students: number;
  active_30d_rate_pct: number;
  weekly_pod_post_compliance_rate_pct: number;
  capstone_completion_rate_pct: number;
  total_capstone_graduates: number;
  avg_days_to_capstone: number;
  top_bottleneck_unit: UnitFrictionRecord | null;
  generated_at: string;
};

export type FailureModeRecord = {
  criterion_id: string;
  type: string;
  occurrences: number;
  sample_reasons: string[];
};

export type RetrievalSeedFailureRecord = {
  seed_index: number;
  seed_prompt: string;
  student_answer: string;
  feedback: string;
  evidence: string;
};

export type ConciergeQuestionRecord = {
  id: number;
  student_id: number;
  mode: string;
  question: string;
  created_at: string;
};

export type UnitDetailResponse = {
  ok: boolean;
  unit: UnitFrictionRecord;
  failure_modes: FailureModeRecord[];
  retrieval_seed_failures: RetrievalSeedFailureRecord[];
  concierge_questions: ConciergeQuestionRecord[];
  generated_at: string;
};

export type AnalyticsResult<T> =
  | { state: "ok"; data: T }
  | { state: "unreachable"; detail: string }
  | { state: "rejected"; status: number; code: string; message?: string };

function practiceBaseUrl(): string {
  return process.env.KEEL_PRACTICE_URL ?? "http://127.0.0.1:8792";
}

function practiceToken(): string | null {
  return process.env.KEEL_ENROLL_SECRET ?? null;
}

async function analyticsFetch<T>(path: string, init?: RequestInit): Promise<AnalyticsResult<T>> {
  const token = practiceToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["X-Keel-App-Token"] = token;
  }

  try {
    const res = await fetch(`${practiceBaseUrl()}${path}`, {
      ...init,
      cache: "no-store",
      headers,
    });
    if (res.ok) {
      return { state: "ok", data: (await res.json()) as T };
    }
    let code = `http_${res.status}`;
    let message: string | undefined;
    try {
      const errObj = (await res.json()) as { error?: string; message?: string };
      code = errObj.error ?? code;
      message = errObj.message;
    } catch {
      // non-JSON error
    }
    return { state: "rejected", status: res.status, code, message };
  } catch (err) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export function fetchAnalyticsSummary(): Promise<AnalyticsResult<OperationsSummaryResponse>> {
  return analyticsFetch<OperationsSummaryResponse>("/analytics/summary");
}

export function fetchMacroFunnel(): Promise<AnalyticsResult<MacroFunnelResponse>> {
  return analyticsFetch<MacroFunnelResponse>("/analytics/funnel");
}

export function fetchDropoffBreakdown(options?: {
  phase?: number;
}): Promise<AnalyticsResult<DropoffBreakdownResponse>> {
  const params = new URLSearchParams();
  if (options?.phase !== undefined) params.set("phase", String(options.phase));
  const qs = params.toString();
  return analyticsFetch<DropoffBreakdownResponse>(`/analytics/drop-off${qs ? `?${qs}` : ""}`);
}

export function fetchUnitAnalytics(unitId: string): Promise<AnalyticsResult<UnitDetailResponse>> {
  return analyticsFetch<UnitDetailResponse>(`/analytics/units/${encodeURIComponent(unitId)}`);
}
