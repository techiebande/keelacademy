"use client";

/* eslint-disable react-hooks/set-state-in-effect -- hydrating reading position from localStorage after mount is intentional to avoid SSR mismatch */
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  loadReadingPosition,
  type StoredReadingPosition,
} from "@/lib/reading-position";

/**
 * The continue card on the /me dashboard (lesson-flow spec U3).
 *
 * Reads localStorage to surface the learner's most recent reading position
 * when active reading has taken place (scrollRatio > 0.03).
 */
export function ReadingContinueCard() {
  const [position, setPosition] = useState<StoredReadingPosition | null>(null);

  useEffect(() => {
    const pos = loadReadingPosition();
    if (pos && pos.scrollRatio > 0.03) {
      setPosition(pos);
    }
  }, []);

  if (!position) return null;

  const percent = Math.round(position.scrollRatio * 100);

  return (
    <section aria-labelledby="continue-reading-title" className="card-dark">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="chip chip-outline font-code-mono text-[11px]">CONTINUE READING</span>
          <h2 id="continue-reading-title" className="heading-md">
            Unit {position.unitId}
          </h2>
        </div>
        <span className="font-code-mono text-[13px] text-moss-70">
          {percent}% through
        </span>
      </div>

      <p className="mt-3 text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        You left off at <strong className="font-medium text-phosphor-white">{position.headingTitle}</strong> in the {position.phaseName} phase. Pick up where you left off.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Link
          href={`/units/${position.unitId}#${position.headingId}`}
          className="btn btn-primary btn-sm"
        >
          Resume Unit {position.unitId}
        </Link>
      </div>
    </section>
  );
}
