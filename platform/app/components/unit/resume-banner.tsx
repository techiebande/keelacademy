"use client";

/* eslint-disable react-hooks/set-state-in-effect -- hydrating reading position from localStorage after mount is intentional to avoid SSR mismatch */
import { useEffect, useState } from "react";
import {
  loadReadingPosition,
  getSessionStartTime,
  isResumeDismissed,
  dismissResume,
  type StoredReadingPosition,
} from "@/lib/reading-position";

/**
 * The unit-page resume banner (lesson-flow spec U3).
 *
 * Renders when the stored reading position is for THIS unit, saved during a
 * previous session, with scrollRatio > 0.03, and has not been dismissed for
 * this session.
 *
 * Renders null without JavaScript or when no previous position exists.
 */
export function ResumeBanner({ unitId }: { unitId: string }) {
  const [position, setPosition] = useState<StoredReadingPosition | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (isResumeDismissed(unitId)) return;
    const pos = loadReadingPosition();
    const sessionStart = getSessionStartTime();

    if (
      pos &&
      pos.unitId === unitId &&
      pos.savedAt < sessionStart &&
      pos.scrollRatio > 0.03
    ) {
      setPosition(pos);
    }
  }, [unitId]);

  if (!position || dismissed) return null;

  const handleDismiss = () => {
    dismissResume(unitId);
    setDismissed(true);
  };

  return (
    <div className="lesson-canvas flow mt-6">
      <aside
        aria-label="Resume reading"
        className="flow-apparatus"
      >
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-circuit-border bg-carbon-veil px-5 py-3.5">
          <p className="text-[14px] leading-relaxed text-phosphor-white">
            <span className="font-code-mono text-[11px] uppercase tracking-wider text-moss-70 mr-2.5">
              RESUME
            </span>
            You stopped at <strong className="font-medium text-phosphor-white">{position.headingTitle}</strong> in {position.phaseName}.
          </p>
          <div className="flex items-center gap-3">
            <a
              href={`#${position.headingId}`}
              className="btn btn-accent btn-sm"
            >
              Resume there
            </a>
            <button
              type="button"
              onClick={handleDismiss}
              aria-label="Dismiss resume notice"
              className="btn btn-quiet btn-sm"
            >
              Dismiss
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}
