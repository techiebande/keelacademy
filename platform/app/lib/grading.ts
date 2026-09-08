/**
 * Server-side access to the grading core through its read-only reader
 * endpoint (platform/grading/reader/server.py). The app never holds database
 * credentials: KEEL_READER_URL is a plain base URL with no secret in it,
 * and this module is imported only by server components, so nothing here
 * can reach a client bundle.
 */

const ID_PATTERN = /^\d{1,15}$/;

export type SubmissionStatus = "queued" | "grading" | "graded" | "error";

export type Layer1Check = {
  id: string;
  type: string;
  status: string;
  note: string;
  wall_s: number | null;
  exit_code: number | null;
  container_status: string | null;
  output_tail: string | null;
};

export type Layer1Result = {
  overall: string;
  checks: Layer1Check[];
  injected?: string[];
};

export type JudgeCriterion = { id: string; verdict: "pass" | "fail"; evidence: string };

export type JudgeVerdict = {
  rubric_id?: string;
  rubric_version?: string | number;
  submission_ref?: string;
  criteria: JudgeCriterion[];
  overall: "pass" | "fail";
  meta?: {
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    latency_s: number;
  };
};

export type TraceRecord = {
  ts?: string;
  caller?: string;
  model?: string;
  tier?: string;
  attempt?: number;
  latency_s?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  cost_usd?: number;
};

export type DefendQuestion = {
  id: string;
  question: string;
  anchors: string[];
};

export type DefendResult = {
  submission_ref?: string;
  tier?: string;
  questions: DefendQuestion[];
  meta?: {
    model: string;
    prompt_tokens: number;
    completion_tokens: number;
    latency_s: number;
  };
};

export type VerdictJson = {
  overall?: "pass" | "fail";
  rubric_id?: string;
  rubric_version?: number;
  layer1?: Layer1Result;
  judge?: JudgeVerdict;
  defend?: DefendResult;
  trace?: { log: string | null; call_id: string; records: TraceRecord[] };
  stub?: boolean;
};

export type Verdict = {
  rubric_id: string | null;
  rubric_version: number | null;
  overall: "pass" | "fail";
  issued_at: string;
  json: VerdictJson;
};

export type TimelineEvent = {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
};

export type SubmissionView = {
  submission: {
    id: number;
    unit_id: string;
    status: SubmissionStatus;
    commit_sha: string;
    repo_url: string | null;
    created_at: string;
    student_id: number;
    student_name: string | null;
  };
  verdict: Verdict | null;
  events: TimelineEvent[];
};

/** Three honest outcomes for a page render: data, unknown id, or service down. */
export type GradingLookup =
  | { state: "not-found" }
  | { state: "unreachable"; detail: string }
  | { state: "ok"; view: SubmissionView };

export function readerBaseUrl(): string {
  return process.env.KEEL_READER_URL ?? "http://127.0.0.1:8790";
}

export async function lookupSubmission(rawId: string): Promise<GradingLookup> {
  if (!ID_PATTERN.test(rawId)) return { state: "not-found" };
  try {
    const res = await fetch(`${readerBaseUrl()}/submissions/${rawId}`, {
      cache: "no-store",
    });
    if (res.status === 404) return { state: "not-found" };
    if (!res.ok) return { state: "unreachable", detail: `reader answered HTTP ${res.status}` };
    return { state: "ok", view: (await res.json()) as SubmissionView };
  } catch (err) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export type StudentSubmissionSummary = {
  id: number;
  unit_id: string;
  status: SubmissionStatus;
  created_at: string;
  overall: "pass" | "fail" | null;
};

export type StudentSubmissionsLookup =
  | { state: "ok"; data: { student_id: number; submissions: StudentSubmissionSummary[] } }
  | { state: "not-found" }
  | { state: "unreachable"; detail: string };

export async function fetchStudentSubmissions(studentId: number): Promise<StudentSubmissionsLookup> {
  try {
    const res = await fetch(`${readerBaseUrl()}/students/${studentId}/submissions`, {
      cache: "no-store",
    });
    if (res.status === 404) return { state: "not-found" };
    if (!res.ok) return { state: "unreachable", detail: `reader answered HTTP ${res.status}` };
    return {
      state: "ok",
      data: (await res.json()) as { student_id: number; submissions: StudentSubmissionSummary[] },
    };
  } catch (err) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

/** Tokens the grading calls for this submission charged to the student budget. */
export function budgetCharged(view: SubmissionView): {
  tokens: number;
  costUsd: number | null;
  model: string | null;
} | null {
  const records = view.verdict?.json?.trace?.records ?? [];
  if (records.length > 0) {
    const tokens = records.reduce(
      (sum, r) => sum + (r.prompt_tokens ?? 0) + (r.completion_tokens ?? 0),
      0,
    );
    const costs = records.map((r) => r.cost_usd).filter((c): c is number => typeof c === "number");
    const model = records.find((r) => r.model)?.model ?? null;
    return { tokens, costUsd: costs.length > 0 ? costs.reduce((a, b) => a + b, 0) : null, model };
  }
  const meta = view.verdict?.json?.judge?.meta;
  if (meta && typeof meta.prompt_tokens === "number") {
    return {
      tokens: meta.prompt_tokens + (meta.completion_tokens ?? 0),
      costUsd: null,
      model: meta.model ?? null,
    };
  }
  return null;
}

/**
 * Postgres prints timestamptz as "2026-08-23 12:34:56.789+00" (space
 * separator, two-digit offset). Normalize before handing it to Date.
 */
export function parseDbTimestamp(raw: string): Date | null {
  const match = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?)([+-]\d{2})?$/.exec(raw);
  const normalized = match
    ? `${match[1]}T${match[2]}${match[3] ? `${match[3]}:00` : "Z"}`
    : raw;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

const utcFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function formatUtc(raw: string): string {
  const date = parseDbTimestamp(raw);
  return date ? `${utcFormatter.format(date)} UTC` : raw;
}
