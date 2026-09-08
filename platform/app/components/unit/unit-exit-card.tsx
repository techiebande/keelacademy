import Link from "next/link";

/**
 * The end-of-unit exit card (lesson-flow spec U1): the designed stopping point
 * after the last phase of a unit script. Every exit is a stopping point, never
 * a dead end, and the card holds to the spec's anatomy: one chip, one honest
 * recap line, exactly one primary next action, and a wrap-up option that is
 * equally legitimate.
 *
 * Every line here is structural (names, counts, verdicts already recorded), so
 * the copy is app-owned; if a line needs teaching voice it belongs in the
 * script, not here. The recap claims only what the page's own data shows: real
 * attempt counts, real drill results, a real verdict. With no recorded
 * activity the line states what the unit covers, never what a student did.
 *
 * States, all from data the unit page already loaded:
 *
 *   signed out                the card still renders (the page is public); the
 *                             primary is the sign-in path and no line claims
 *                             anything about the anonymous reader
 *   gate passed + next unit   primary starts yaml.gate.unlocks[0]
 *   not passed yet            primary stays on this unit's build surface and a
 *                             quiet line names what opens once it passes
 *   no unlocks (phase final)  primary goes to the curriculum; no next unit is
 *                             invented
 *
 * Server component; no client JavaScript.
 */

/** The student's latest recorded outcome on this unit, or null when unknown. */
export type UnitExitVerdict = "pass" | "not-yet" | "grading" | null;

type UnitExitCardProps = {
  unitId: string;
  /** What the unit asks the student to ship, from unit.yaml. */
  deliverable: string;
  isSignedIn: boolean;
  isEnrolled: boolean;
  /** True only on a real recorded passing verdict for this unit. */
  gatePassed: boolean;
  /** yaml.gate.unlocks[0], or null when this unit unlocks nothing. */
  nextUnitId: string | null;
  /** The curriculum anchor for this unit's phase, e.g. "/curriculum#phase-3". */
  curriculumHref: string;
  /** Workbench runs recorded for this unit. Zero means none recorded. */
  practiceAttemptCount: number;
  /**
   * Distinct retrieval drills passed, or null when no retrieval attempts are
   * recorded at all (which is not the same claim as "zero passed").
   */
  retrievalPassedCount: number | null;
  /** How many retrieval seeds the unit has. */
  retrievalSeedCount: number;
  latestVerdict: UnitExitVerdict;
  /** Re-check questions for this unit that are due now. */
  dueReviewCount: number;
};

export function UnitExitCard({
  unitId,
  deliverable,
  isSignedIn,
  isEnrolled,
  gatePassed,
  nextUnitId,
  curriculumHref,
  practiceAttemptCount,
  retrievalPassedCount,
  retrievalSeedCount,
  latestVerdict,
  dueReviewCount,
}: UnitExitCardProps) {
  // The recap makes claims only from data that actually loaded. An unreachable
  // practice service leaves the counts at zero or null, and the line falls back
  // to what the unit covers, which is true regardless.
  const coverage = `What this unit ships: ${deliverable}`;
  const recap = isSignedIn ? recapLine(coverage, practiceAttemptCount, retrievalPassedCount, retrievalSeedCount, latestVerdict) : coverage;

  const primary = primaryAction(unitId, isSignedIn, isEnrolled, gatePassed, nextUnitId, curriculumHref);
  const lockedLine =
    isSignedIn && nextUnitId !== null && !gatePassed
      ? `Unit ${nextUnitId} opens when this unit passes.`
      : null;

  // "Your work is saved" is a claim about recorded work, so it renders only
  // when there is recorded work to save.
  const hasRecordedWork =
    practiceAttemptCount > 0 || retrievalPassedCount !== null || latestVerdict !== null;
  const wrapUpLine =
    isSignedIn && hasRecordedWork ? savedLine(dueReviewCount) : null;

  return (
    <div className="lesson-canvas flow">
      <div id="unit-exit" className="flow-apparatus apparatus mt-24">
        <div className="apparatus-head">
          <p className="apparatus-label">End of unit {unitId}</p>
          <span className="chip chip-outline font-code-mono text-[11px]">UNIT COMPLETE</span>
        </div>

        <p className="apparatus-note">{recap}</p>

        <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3">
          <Link href={primary.href} className="btn btn-accent btn-sm">
            {primary.label}
          </Link>
          {lockedLine ? (
            <p className="text-[13.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              {lockedLine}
            </p>
          ) : null}
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[color:var(--line-on-dark)] pt-5">
          <Link href="/me" className="btn btn-quiet btn-sm">
            Wrap up
          </Link>
          {wrapUpLine ? (
            <p className="text-[13px] leading-relaxed text-[color:var(--text-faint-on-dark)]">
              {wrapUpLine}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function recapLine(
  coverage: string,
  practiceAttemptCount: number,
  retrievalPassedCount: number | null,
  retrievalSeedCount: number,
  verdict: UnitExitVerdict,
): string {
  const sentences: string[] = [];
  if (practiceAttemptCount > 0) {
    sentences.push(
      `You ran the completion problem ${practiceAttemptCount} ${
        practiceAttemptCount === 1 ? "time" : "times"
      }.`,
    );
  }
  if (retrievalPassedCount !== null) {
    sentences.push(`${retrievalPassedCount} of ${retrievalSeedCount} retrieval drills show Passed.`);
  }
  if (verdict === "pass") {
    sentences.push("Your latest verdict on this unit is Passed.");
  } else if (verdict === "not-yet") {
    sentences.push("Your latest verdict on this unit is Not yet.");
  } else if (verdict === "grading") {
    sentences.push("Your latest submission for this unit is waiting for grading.");
  }
  return sentences.length > 0 ? sentences.join(" ") : coverage;
}

function primaryAction(
  unitId: string,
  isSignedIn: boolean,
  isEnrolled: boolean,
  gatePassed: boolean,
  nextUnitId: string | null,
  curriculumHref: string,
): { href: string; label: string } {
  if (!isSignedIn) {
    // The sign-in path wording the rest of the page already uses.
    return { href: `/sign-in?next=/units/${unitId}`, label: "Sign in" };
  }
  if (nextUnitId === null) {
    // Phase-final unit: the curriculum names what remains; no next unit is
    // invented here.
    return { href: curriculumHref, label: "See the rest of this phase" };
  }
  if (gatePassed) {
    return { href: `/units/${nextUnitId}`, label: `Start ${nextUnitId}` };
  }
  if (!isEnrolled) {
    // The checkout path wording the workbench already uses: a verdict needs an
    // active enrollment, so this student's one next action is enrolling.
    return { href: "/map", label: "Enroll from your progress map" };
  }
  return { href: "#build", label: "Open the build brief" };
}

function savedLine(dueReviewCount: number): string {
  if (dueReviewCount === 1) {
    return "Your work is saved. 1 review question from this unit is due now.";
  }
  if (dueReviewCount > 1) {
    return `Your work is saved. ${dueReviewCount} review questions from this unit are due now.`;
  }
  return "Your work is saved.";
}
