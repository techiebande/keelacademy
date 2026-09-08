/**
 * Server-side client for the Public Build Gallery service (S4.4)
 * (platform/grading/community/gallery.py via practice/server.py).
 *
 * Exposes:
 * - Public gallery project discovery & filtering
 * - Deep dive project details with verified rubric badges
 * - Student opt-in publishing and unpublishing controls
 *
 * Security: Uses KEEL_PRACTICE_URL and KEEL_ENROLL_SECRET from server environment only.
 */

export type GalleryVerdictBadge = {
  overall: "pass" | "fail";
  rubric_id: string | null;
  criteria_passed: number;
  total_criteria: number;
};

export type GalleryProjectSummary = {
  id: number;
  student_id: number;
  student_name: string;
  unit_id: string;
  unit_title: string;
  phase: number;
  submission_id: number;
  commit_sha: string;
  title: string;
  description: string;
  repo_url: string | null;
  demo_url: string | null;
  walkthrough_video_url: string | null;
  published: boolean;
  created_at: string;
  updated_at: string;
  verdict: GalleryVerdictBadge;
};

export type GalleryProjectDetail = {
  id: number;
  student_id: number;
  student_name: string;
  unit_id: string;
  unit_title: string;
  phase: number;
  submission_id: number;
  commit_sha: string;
  title: string;
  description: string;
  repo_url: string | null;
  demo_url: string | null;
  walkthrough_video_url: string | null;
  published: boolean;
  created_at: string;
  updated_at: string;
  verdict: {
    overall: string;
    rubric_id: string | null;
    rubric_version: number | null;
    issued_at: string | null;
    json: Record<string, unknown>;
  };
};

export type GalleryListResponse = {
  projects: GalleryProjectSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type StudentGalleryProject = {
  id: number;
  student_id: number;
  unit_id: string;
  unit_title: string;
  phase: number;
  submission_id: number;
  commit_sha: string;
  title: string;
  description: string;
  repo_url: string | null;
  demo_url: string | null;
  walkthrough_video_url: string | null;
  published: boolean;
  created_at: string;
  updated_at: string;
  overall: string;
  rubric_id: string | null;
};

export type PublishGalleryInput = {
  studentId: number;
  submissionId: number;
  title: string;
  description: string;
  repoUrl?: string;
  demoUrl?: string;
  walkthroughVideoUrl?: string;
};

export type UnpublishGalleryInput = {
  studentId: number;
  projectId?: number;
  unitId?: string;
};

export type GalleryResult<T> =
  | { state: "ok"; data: T }
  | { state: "unreachable"; detail: string }
  | { state: "rejected"; status: number; code: string; message?: string };

function practiceBaseUrl(): string {
  return process.env.KEEL_PRACTICE_URL ?? "http://127.0.0.1:8792";
}

function practiceToken(): string | null {
  return process.env.KEEL_ENROLL_SECRET ?? null;
}

async function galleryFetch<T>(path: string, init?: RequestInit): Promise<GalleryResult<T>> {
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
      // non-JSON error body: keep status code
    }
    return { state: "rejected", status: res.status, code, message };
  } catch (err) {
    return {
      state: "unreachable",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

export function fetchGalleryProjects(options?: {
  unitId?: string;
  phase?: number;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<GalleryResult<GalleryListResponse>> {
  const params = new URLSearchParams();
  if (options?.unitId) params.set("unit_id", options.unitId);
  if (options?.phase !== undefined) params.set("phase", String(options.phase));
  if (options?.search) params.set("search", options.search);
  if (options?.limit !== undefined) params.set("limit", String(options.limit));
  if (options?.offset !== undefined) params.set("offset", String(options.offset));

  const qs = params.toString();
  return galleryFetch<GalleryListResponse>(`/gallery${qs ? `?${qs}` : ""}`);
}

export function fetchGalleryProject(id: number): Promise<GalleryResult<GalleryProjectDetail>> {
  return galleryFetch<GalleryProjectDetail>(`/gallery/${id}`);
}

export function fetchStudentGalleryProjects(
  studentId: number,
): Promise<GalleryResult<{ student_id: number; projects: StudentGalleryProject[] }>> {
  return galleryFetch<{ student_id: number; projects: StudentGalleryProject[] }>(
    `/students/${studentId}/gallery`,
  );
}

export function fetchSubmissionGalleryProject(
  submissionId: number,
): Promise<GalleryResult<{ submission_id: number; has_gallery_project: boolean; project: StudentGalleryProject | null }>> {
  return galleryFetch<{ submission_id: number; has_gallery_project: boolean; project: StudentGalleryProject | null }>(
    `/gallery/submission/${submissionId}`,
  );
}

export function publishGalleryProject(input: PublishGalleryInput): Promise<GalleryResult<GalleryProjectSummary>> {
  return galleryFetch<GalleryProjectSummary>("/gallery/publish", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      submission_id: input.submissionId,
      title: input.title,
      description: input.description,
      repo_url: input.repoUrl,
      demo_url: input.demoUrl,
      walkthrough_video_url: input.walkthroughVideoUrl,
    }),
  });
}

export function unpublishGalleryProject(input: UnpublishGalleryInput): Promise<GalleryResult<{ ok: boolean; project_id: number; published: boolean }>> {
  return galleryFetch<{ ok: boolean; project_id: number; published: boolean }>("/gallery/unpublish", {
    method: "POST",
    body: JSON.stringify({
      student_id: input.studentId,
      project_id: input.projectId,
      unit_id: input.unitId,
    }),
  });
}
