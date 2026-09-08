import { scriptPhaseLabel } from "@/lib/content";

/**
 * The phase-boundary exit marker (lesson-flow spec U2): one quiet mono line at
 * the end of a phase, which makes the boundary a legitimate stopping point
 * rather than only a change of activity. The break itself stays where it
 * always was, in the spacing before the next phase; this line is text inside
 * the phase that just ended, in the reading measure, with no border and no
 * card around it.
 *
 * The line is data-assembled, so its copy is app-owned: the names come from
 * the script's own phase vocabulary and the time from the same per-beat
 * estimates the contents rail lists. Nothing here teaches; a line that needs
 * teaching voice belongs in the script, not at its edge.
 *
 *   END OF LEARN · NEXT: PRACTICE, ABOUT 4 MIN · STOP HERE IF YOU LIKE
 *
 * The time segment is the sum of the next phase's own beat estimates, and it
 * renders only when that sum is honest: a phase with unmeasured beats has no
 * total, and printing the sum of the measured ones would read as a number and
 * be an undercount. So the whole segment drops, separator and all, rather
 * than guess.
 *
 * The id is stable per boundary (`exit-` plus the ended phase's anchor), so
 * the resume surface (spec U3) can link a returning reader straight to a
 * stopping point. It is an anchor target, not a link, and it is rendered on
 * the server: no client JavaScript.
 */
export function UnitBoundary({
  phaseId,
  nextPhaseId,
  nextEstMinutes,
}: {
  /** The anchor of the phase that just ended; the marker closes that phase. */
  phaseId: string;
  /** The anchor of the phase that follows; names what is next. */
  nextPhaseId: string;
  /** The next phase's summed beat estimate, or null when it cannot be computed. */
  nextEstMinutes: number | null;
}) {
  const ended = scriptPhaseLabel(phaseId).toUpperCase();
  const next = scriptPhaseLabel(nextPhaseId).toUpperCase();
  const time = nextEstMinutes === null ? "" : `, ABOUT ${nextEstMinutes} MIN`;

  return (
    <p id={`exit-${phaseId}`} data-keel-exit={phaseId} className="unit-boundary">
      {`END OF ${ended} · NEXT: ${next}${time} · STOP HERE IF YOU LIKE`}
    </p>
  );
}
