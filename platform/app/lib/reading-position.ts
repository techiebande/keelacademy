/**
 * Reading position persistence (lesson-flow spec U3).
 *
 * Model: per-device, localStorage, keyed under 'keel-reading-position'.
 * Deliberately not a progress claim or completion proof.
 *
 * Store schema:
 *   { unitId, phaseId, phaseName, headingId, headingTitle, scrollRatio, savedAt }
 *
 * Failures are silent (the feature is an enhancement).
 */

export type StoredReadingPosition = {
  unitId: string;
  phaseId: string;
  phaseName: string;
  headingId: string;
  headingTitle: string;
  scrollRatio: number;
  savedAt: number;
};

export const READING_POSITION_STORAGE_KEY = "keel-reading-position";
export const SESSION_START_KEY = "keel-session-start";
export const DISMISSED_RESUME_PREFIX = "keel-resume-dismissed-";

export function getSessionStartTime(): number {
  if (typeof window === "undefined") return Date.now();
  try {
    const existing = window.sessionStorage.getItem(SESSION_START_KEY);
    if (existing) {
      const parsed = parseInt(existing, 10);
      if (!Number.isNaN(parsed)) return parsed;
    }
    const now = Date.now();
    window.sessionStorage.setItem(SESSION_START_KEY, String(now));
    return now;
  } catch {
    return Date.now();
  }
}

export function loadReadingPosition(): StoredReadingPosition | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(READING_POSITION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      typeof parsed?.unitId === "string" &&
      typeof parsed?.phaseId === "string" &&
      typeof parsed?.headingId === "string" &&
      typeof parsed?.scrollRatio === "number" &&
      typeof parsed?.savedAt === "number"
    ) {
      return parsed as StoredReadingPosition;
    }
    return null;
  } catch {
    return null;
  }
}

export function saveReadingPosition(pos: StoredReadingPosition): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(READING_POSITION_STORAGE_KEY, JSON.stringify(pos));
  } catch {
    // Storage failures are silent
  }
}

export function isResumeDismissed(unitId: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.sessionStorage.getItem(`${DISMISSED_RESUME_PREFIX}${unitId}`) === "1";
  } catch {
    return false;
  }
}

export function dismissResume(unitId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(`${DISMISSED_RESUME_PREFIX}${unitId}`, "1");
  } catch {
    // silent
  }
}
