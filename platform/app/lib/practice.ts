/**
 * Server-side client for the practice grading service
 * (platform/grading/practice/server.py).
 *
 * Same security discipline as enroll.ts: the app holds KEEL_PRACTICE_URL
 * (plain base URL) and KEEL_ENROLL_SECRET (shared app token in server env only,
 * never NEXT_PUBLIC).
 *
 * Every call is server-side only; import exclusively from server components
 * and server actions.
 */

export type PracticeManifest = {
  unit_id: string;
  kind?: "code" | "conceptual";
  base_rel: string;
  readme_markdown: string;
  base_files: Record<string, string>;
  editable_files: string[];
  checks: { id: string; type: string }[];
};

export type PracticeCheckResult = {
  id: string;
  type: string;
  status: "pass" | "fail" | "error";
  note: string;
  wall_s: number | null;
  exit_code: number | null;
  container_status: string | null;
  output_tail: string | null;
};

export type PracticeAttemptResult = {
  ok: boolean;
  attempt_id: number;
  student_id: number;
  unit_id: string;
  passed: boolean;
  pass_count: number;
  total_checks: number;
  checks: PracticeCheckResult[];
  created_at: string;
};

export type PracticeAttemptSummary = {
  id: number;
  student_id: number;
  unit_id: string;
  passed: boolean;
  pass_count: number;
  total_checks: number;
  checks: PracticeCheckResult[];
  created_at: string;
};

export type RetrievalSeed = {
  index: number;
  prompt: string;
};

export type RetrievalAttemptResult = {
  ok: boolean;
  attempt_id: number;
  student_id: number;
  unit_id: string;
  seed_index: number;
  seed_prompt: string;
  passed: boolean;
  feedback: string;
  evidence: string;
  tokens_charged: number;
  created_at: string;
};

export type RetrievalAttemptSummary = {
  id: number;
  student_id: number;
  unit_id: string;
  seed_index: number;
  seed_prompt: string;
  passed: boolean;
  feedback: string;
  evidence: string;
  tokens_charged: number;
  created_at: string;
};

export type RecheckSeedStatus = "upcoming" | "due" | "retired";

export type RecheckSeed = {
  unit_id: string;
  seed_index: number;
  seed_prompt: string;
  stage: number;
  status: RecheckSeedStatus;
  mastery?: "unstarted" | "attempted" | "familiar" | "proficient" | "mastered";
  last_pass_at: string | null;
  due_at: string | null;
};

export type RecheckSchedule = {
  student_id: number;
  now: string;
  due_count: number;
  seeds: RecheckSeed[];
};

export type PracticeRouteStep = {
  id: "lesson" | "retrieval" | "worked_example" | "completion";
  title: string;
  type: "concept" | "drill" | "scaffold" | "workbench";
  status: "done" | "current" | "upcoming" | "optional" | "scaffold" | "retry";
  passed_count?: number;
  total_count?: number;
  summary: string;
};

export type ScaffoldCallout = {
  type: "drill_retry" | "completion_retry";
  seed_index?: number;
  seed_prompt?: string;
  target_file: string;
  target_section: string;
  anchor: string;
  url: string;
  summary: string;
  action_label: string;
};

export type PracticeRouteData = {
  student_id: number;
  unit_id: string;
  enrolled: boolean;
  status: "in_progress" | "fast_pass" | "scaffold_active" | "standard" | "completed" | "unenrolled";
  recommended_step: "lesson" | "retrieval" | "worked_example" | "completion" | "build" | null;
  fast_pass_eligible: boolean;
  fast_pass_active: boolean;
  scaffold_active: boolean;
  summary: string;
  steps: PracticeRouteStep[];
  scaffold_callout: ScaffoldCallout | null;
  scaffold_mapping?: {
    seed_index: number;
    seed_prompt: string;
    target_file: string;
    target_section: string;
    anchor: string;
    url: string;
    summary: string;
  }[];
};

export type PracticeResult<T> =
  | { state: "ok"; data: T }
  | { state: "unreachable"; detail: string }
  | { state: "rejected"; status: number; code: string; message?: string };

export function practiceBaseUrl(): string {
  return process.env.KEEL_PRACTICE_URL ?? "http://127.0.0.1:8792";
}

function practiceToken(): string | null {
  return process.env.KEEL_ENROLL_SECRET ?? null;
}

async function practiceFetch<T>(path: string, init?: RequestInit): Promise<PracticeResult<T>> {
  const token = practiceToken();
  if (!token) {
    return { state: "rejected", status: 0, code: "app_not_configured" };
  }
  try {
    const res = await fetch(`${practiceBaseUrl()}${path}`, {
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
    let message: string | undefined;
    try {
      const errObj = (await res.json()) as { error?: string; message?: string };
      code = errObj.error ?? code;
      message = errObj.message;
    } catch {
      // non-JSON error body: keep http status code
    }
    return { state: "rejected", status: res.status, code, message };
  } catch (err) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export function fetchPracticeManifest(unitId: string): Promise<PracticeResult<PracticeManifest>> {
  return practiceFetch<PracticeManifest>(`/practice/manifest?unit=${encodeURIComponent(unitId)}`);
}

export function submitPracticeAttempt(input: {
  studentId: number;
  unitId: string;
  files: Record<string, string>;
  answer?: string;
}): Promise<PracticeResult<PracticeAttemptResult>> {
  return practiceFetch<PracticeAttemptResult>("/practice/attempt", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      unit_id: input.unitId,
      files: input.files,
      answer: input.answer,
    }),
  });
}

export function fetchPracticeAttempts(
  studentId: number,
  unitId: string,
): Promise<PracticeResult<{ attempts: PracticeAttemptSummary[] }>> {
  return practiceFetch<{ attempts: PracticeAttemptSummary[] }>(
    `/practice/attempts?student_id=${studentId}&unit=${encodeURIComponent(unitId)}`,
  );
}

export function fetchRetrievalSeeds(
  unitId: string,
): Promise<PracticeResult<{ unit_id: string; seeds: RetrievalSeed[] }>> {
  return practiceFetch<{ unit_id: string; seeds: RetrievalSeed[] }>(
    `/practice/retrieval/seeds?unit=${encodeURIComponent(unitId)}`,
  );
}

export function submitRetrievalAttempt(input: {
  studentId: number;
  unitId: string;
  seedIndex: number;
  seedPrompt: string;
  answer: string;
}): Promise<PracticeResult<RetrievalAttemptResult>> {
  return practiceFetch<RetrievalAttemptResult>("/practice/retrieval/attempt", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      unit_id: input.unitId,
      seed_index: input.seedIndex,
      seed_prompt: input.seedPrompt,
      answer: input.answer,
    }),
  });
}

export function fetchRetrievalAttempts(
  studentId: number,
  unitId: string,
): Promise<PracticeResult<{ attempts: RetrievalAttemptSummary[] }>> {
  return practiceFetch<{ attempts: RetrievalAttemptSummary[] }>(
    `/practice/retrieval/attempts?student_id=${studentId}&unit=${encodeURIComponent(unitId)}`,
  );
}

export function fetchRecheckSchedule(
  studentId: number,
  unitId?: string,
): Promise<PracticeResult<RecheckSchedule>> {
  const unitParam = unitId ? `&unit=${encodeURIComponent(unitId)}` : "";
  return practiceFetch<RecheckSchedule>(
    `/practice/retrieval/schedule?student_id=${studentId}${unitParam}`,
  );
}

export type ReviewQueueItem = {
  review_id: string;
  unit_id: string;
  seed_index: number;
  seed_prompt: string;
  mastery: "unstarted" | "attempted" | "familiar" | "proficient" | "mastered";
  stage: number;
  due_at: string | null;
};

export type ReviewQueueResponse = {
  student_id: number;
  now: string;
  due_count: number;
  items: ReviewQueueItem[];
};

export function fetchReviewQueue(
  studentId: number,
): Promise<PracticeResult<ReviewQueueResponse>> {
  return practiceFetch<ReviewQueueResponse>(
    `/practice/review/queue?student_id=${studentId}`,
  );
}

export function fetchPracticeRoute(
  studentId: number,
  unitId: string,
): Promise<PracticeResult<PracticeRouteData>> {
  return practiceFetch<PracticeRouteData>(
    `/practice/route?student_id=${studentId}&unit=${encodeURIComponent(unitId)}`,
  );
}

export type ConciergeMode = "teach" | "guard";

export type ConciergeTurn = {
  id: number;
  student_id: number;
  unit_id: string;
  mode: ConciergeMode;
  question: string;
  answer: string;
  tokens_charged: number;
  created_at: string;
};

export type ConciergeAskResult = {
  ok: boolean;
  turn_id: number;
  student_id: number;
  unit_id: string;
  mode: ConciergeMode;
  mode_reason: string;
  answer: string;
  tokens_charged: number;
  created_at: string;
};

export function fetchConciergeTurns(
  studentId: number,
  unitId: string,
): Promise<PracticeResult<{ turns: ConciergeTurn[] }>> {
  return practiceFetch<{ turns: ConciergeTurn[] }>(
    `/concierge/turns?student_id=${studentId}&unit=${encodeURIComponent(unitId)}`,
  );
}

export function askConcierge(input: {
  studentId: number;
  unitId: string;
  question: string;
}): Promise<PracticeResult<ConciergeAskResult>> {
  return practiceFetch<ConciergeAskResult>("/concierge/ask", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      unit_id: input.unitId,
      question: input.question,
    }),
  });
}

export type DiagnosticQuestionBreakdown = {
  question_id: string;
  category: string;
  points_possible: number;
  points_earned: number;
  correct: boolean;
  submitted_answer: string;
  correct_answer: string;
  explanation: string;
};

export type DiagnosticAttempt = {
  id: number;
  student_id: number;
  diagnostic_id: string;
  passed: boolean;
  score_pct: number;
  points_earned: number;
  points_possible: number;
  route: "1.3_skip" | "baseline_0.1" | "opt_out";
  answers: Record<string, string>;
  breakdown: DiagnosticQuestionBreakdown[];
  created_at: string;
};

export type DiagnosticEvaluateResult = {
  ok: boolean;
  attempt_id: number;
  student_id: number;
  diagnostic_id: string;
  passed: boolean;
  score_pct: number;
  passing_threshold_pct?: number;
  points_earned: number;
  points_possible: number;
  route: "1.3_skip" | "baseline_0.1" | "opt_out";
  unlocked_units: string[];
  breakdown: DiagnosticQuestionBreakdown[];
  created_at: string;
};

export function fetchDiagnosticAttempts(
  studentId: number,
): Promise<PracticeResult<{ student_id: number; attempts: DiagnosticAttempt[] }>> {
  return practiceFetch<{ student_id: number; attempts: DiagnosticAttempt[] }>(
    `/diagnostic/attempts?student_id=${studentId}`,
  );
}

export function evaluateDiagnostic(input: {
  studentId: number;
  diagnosticId?: string;
  answers: Record<string, string>;
}): Promise<PracticeResult<DiagnosticEvaluateResult>> {
  return practiceFetch<DiagnosticEvaluateResult>("/diagnostic/evaluate", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      diagnostic_id: input.diagnosticId || "placement-phase-1",
      answers: input.answers,
    }),
  });
}

export function optOutDiagnostic(input: {
  studentId: number;
  diagnosticId?: string;
}): Promise<PracticeResult<DiagnosticEvaluateResult>> {
  return practiceFetch<DiagnosticEvaluateResult>("/diagnostic/opt-out", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      diagnostic_id: input.diagnosticId || "placement-phase-1",
    }),
  });
}

export type PodPeer = {
  student_id: number;
  display_name: string;
  is_self: boolean;
  joined_at: string;
};

export type PodDetails = {
  pod_id: number;
  name: string;
  cohort_week: string;
  discord_channel_id: string | null;
  discord_role_id: string | null;
  discord_channel_url: string | null;
  joined_at: string;
  peers: PodPeer[];
};

export type PodPost = {
  id: number;
  pod_id: number;
  student_id: number;
  author_name: string;
  week_number: number;
  shipped_text: string;
  broke_text: string;
  next_text: string;
  discord_message_id: string | null;
  created_at: string;
};

export type PodMembersResponse = {
  student_id: number;
  has_pod: boolean;
  pod: PodDetails | null;
};

export type PodAssignResponse = {
  ok: boolean;
  student_id: number;
  pod_id: number;
  name: string;
  cohort_week: string;
  discord_channel_id: string | null;
  discord_role_id: string | null;
  joined_at: string;
  newly_assigned: boolean;
};

export type PodPostSubmitResult = {
  ok: boolean;
  post_id: number;
  pod_id: number;
  student_id: number;
  week_number: number;
  shipped_text: string;
  broke_text: string;
  next_text: string;
  discord_message_id: string | null;
  created_at: string;
};

export function fetchPodMembers(
  studentId: number,
): Promise<PracticeResult<PodMembersResponse>> {
  return practiceFetch<PodMembersResponse>(`/pod/members?student_id=${studentId}`);
}

export function assignPod(input: {
  studentId: number;
  cohortWeek?: string;
}): Promise<PracticeResult<PodAssignResponse>> {
  return practiceFetch<PodAssignResponse>("/pod/assign", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      cohort_week: input.cohortWeek,
    }),
  });
}

export function fetchPodPosts(
  podId: number,
  weekNumber?: number,
): Promise<PracticeResult<{ pod_id: number; week_number: number | null; posts: PodPost[] }>> {
  const weekParam = weekNumber !== undefined ? `&week=${weekNumber}` : "";
  return practiceFetch<{ pod_id: number; week_number: number | null; posts: PodPost[] }>(
    `/pod/posts?pod_id=${podId}${weekParam}`,
  );
}

export function submitPodPost(input: {
  studentId: number;
  podId: number;
  weekNumber: number;
  shippedText: string;
  brokeText: string;
  nextText: string;
}): Promise<PracticeResult<PodPostSubmitResult>> {
  return practiceFetch<PodPostSubmitResult>("/pod/posts", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      pod_id: input.podId,
      week_number: input.weekNumber,
      shipped_text: input.shippedText,
      broke_text: input.brokeText,
      next_text: input.nextText,
    }),
  });
}

export type DigestLocationPillar = {
  active_unit: string;
  active_unit_title: string;
  completed_units: string[];
  completed_count: number;
  current_route_step: string;
  is_idle: boolean;
  is_completed: boolean;
  headline: string;
  note: string;
};

export type DigestNextUnlocksPillar = {
  next_units: { unit_id: string; title: string; phase: number; description: string }[];
  next_phase: number;
  summary: string;
};

export type DigestPodHighlight = {
  post_id: number;
  author: string;
  is_self: boolean;
  week_number: number;
  shipped: string;
  broke: string;
  next: string;
};

export type DigestPodActivityPillar = {
  has_pod: boolean;
  pod_id: number | null;
  pod_name: string;
  highlights: DigestPodHighlight[];
  summary: string;
};

export type DigestRebateMilestone = {
  gate_id: string;
  unit_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  window_ends_at: string;
  earned_at: string | null;
};

export type DigestRebateStatusPillar = {
  earned_cents: number;
  pledged_cents: number;
  currency: string;
  milestones: DigestRebateMilestone[];
  summary: string;
};

export type DigestPillars = {
  current_location: DigestLocationPillar;
  next_unlocks: DigestNextUnlocksPillar;
  pod_activity: DigestPodActivityPillar;
  rebate_status: DigestRebateStatusPillar;
};

export type DigestContentJson = {
  student_id: number;
  display_name: string;
  email: string;
  cohort_week: string;
  generated_at: string;
  pillars: DigestPillars;
};

export type DigestRecord = {
  id: number;
  student_id: number;
  cohort_week: string;
  content_json: DigestContentJson;
  email_to: string;
  delivered_at: string | null;
  created_at: string;
};

export type LatestDigestResponse = {
  student_id: number;
  has_digest: boolean;
  digest: DigestRecord | null;
};

export function fetchLatestDigest(
  studentId: number,
): Promise<PracticeResult<LatestDigestResponse>> {
  return practiceFetch<LatestDigestResponse>(`/digest/latest?student_id=${studentId}`);
}

export type ExplainItBackResult = {
  ok: boolean;
  passed: boolean;
  feedback: string;
  score: number;
};

export function evaluateExplainItBack(params: {
  studentId: number;
  unitId: string;
  explanation: string;
}): Promise<PracticeResult<ExplainItBackResult>> {
  return practiceFetch<ExplainItBackResult>("/practice/explain/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      student_id: params.studentId,
      unit_id: params.unitId,
      explanation: params.explanation,
    }),
  });
}
