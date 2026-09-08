import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  assertValidUnitId,
  loadCurriculumMap,
  loadUnit,
  oldestVerified,
  type MapModule,
  type MapPhase,
  type Unit,
} from "@/lib/content";
import {
  PracticeRouteStrip,
  WorkedExampleCard,
  CompletionWorkbenchCard,
  RetrievalDrillCard,
} from "@/components/unit/practice-section";
import {
  DeliverableCallout,
  SubmissionContractCard,
} from "@/components/unit/build-section";
import {
  ProveItCard,
  GradingModesCard,
  AutomatedChecksCard,
  RubricCard,
} from "@/components/unit/verify-section";
import { UnstuckList } from "@/components/unit/unstuck-section";
import { ConciergePanel } from "@/components/unit/concierge-panel";
import { UnitScript } from "@/components/unit/unit-script";
import { UnitExitCard } from "@/components/unit/unit-exit-card";
import { MermaidRuntime } from "@/components/unit/mermaid-runtime";
import { CodeFigureRuntime } from "@/components/unit/code-figure";
import { ChapterOpener } from "@/components/unit/chapter-opener";
import { ResumeBanner } from "@/components/unit/resume-banner";
import { ReadingTracker } from "@/components/unit/reading-tracker";
import { getSessionUser } from "@/lib/auth";
import { fetchStudentSubmissions, parseDbTimestamp } from "@/lib/grading";
import { ensureStudent, fetchProfile } from "@/lib/enroll";
import {
  fetchConciergeTurns,
  fetchPracticeAttempts,
  fetchPracticeManifest,
  fetchPracticeRoute,
  fetchRecheckSchedule,
  fetchRetrievalAttempts,
  fetchReviewQueue,
  type ConciergeTurn,
  type PracticeAttemptSummary,
  type PracticeRouteData,
  type RetrievalAttemptSummary,
  type ReviewQueueItem,
} from "@/lib/practice";

export const dynamic = "force-dynamic";

function tryLoadUnit(unitId: string): Unit | null {
  try {
    return loadUnit(unitId);
  } catch {
    return null;
  }
}

/**
 * A unit id the curriculum map knows about but nobody has written yet. The map
 * does not link to these, but a typed or bookmarked id still lands here, and a
 * planned unit is a real answer where a 404 is a wrong one.
 */
function findPlannedUnit(unitId: string): { phase: MapPhase; module: MapModule } | null {
  for (const phase of loadCurriculumMap().phases) {
    const entry = phase.modules.find((m) => m.id === unitId);
    if (entry) return { phase, module: entry };
  }
  return null;
}

type Props = {
  params: Promise<{ unitId: string }>;
};

export async function generateMetadata(
  props: Props,
): Promise<Metadata> {
  const { unitId } = await props.params;
  const unit = tryLoadUnit(unitId);
  if (!unit) {
    const planned = findPlannedUnit(unitId);
    if (planned) {
      return {
        title: `Unit ${unitId}: ${planned.module.title} (planned)`,
        description: planned.module.description,
        robots: { index: false },
      };
    }
    return { title: "Unit not found" };
  }
  return {
    title: `Unit ${unit.yaml.id}: ${unit.script?.title ?? unit.curriculum?.title ?? unit.yaml.id}`,
    description: unit.yaml.build.deliverable,
  };
}

export default async function UnitPage(props: Props) {
  const { unitId } = await props.params;
  try {
    assertValidUnitId(unitId);
  } catch {
    notFound();
  }
  const unit = tryLoadUnit(unitId);
  if (!unit) {
    const planned = findPlannedUnit(unitId);
    if (!planned) notFound();
    return <PlannedUnit phase={planned.phase} module={planned.module} />;
  }

  const {
    yaml,
    script,
    workedExample,
    completionProblem,
    checks,
    contract,
    rubric,
    faq,
    curriculum,
  } = unit;

  /**
   * Every lesson is authored as a unit script, so a lesson file without a
   * `::: phase` line is an authoring mistake rather than a state a student can
   * reach. Failing loudly names the file and the missing marker; rendering a
   * partial page would hide it until someone read the whole unit.
   */
  if (!script) {
    throw new Error(
      `Unit ${yaml.id}: ${yaml.learn ?? "learn.md"} is not a unit script. ` +
        `Every lesson needs a "::: phase learn" line. See platform/app/AGENTS.md.`,
    );
  }

  const user = await getSessionUser();
  const isSignedIn = !!user;
  let isEnrolled = false;
  let studentId: number | null = null;
  let practiceAttempts: PracticeAttemptSummary[] = [];
  let retrievalAttempts: RetrievalAttemptSummary[] = [];
  let dueSeedIndices: number[] = [];
  let priorReviewItems: ReviewQueueItem[] = [];
  let routeData: PracticeRouteData | null = null;
  let conciergeTurns: ConciergeTurn[] = [];

  if (user) {
    const studentRes = await ensureStudent(user);
    if (studentRes.state === "ok") {
      studentId = studentRes.data;
      const profileRes = await fetchProfile(studentId);
      if (profileRes.state === "ok") {
        isEnrolled = profileRes.data.enrollments.some(
          (e) => e.unit_id === unitId && e.status === "active",
        );
      }
      const attemptsRes = await fetchPracticeAttempts(studentId, unitId);
      if (attemptsRes.state === "ok") {
        practiceAttempts = attemptsRes.data.attempts;
      }
      const retrievalRes = await fetchRetrievalAttempts(studentId, unitId);
      if (retrievalRes.state === "ok") {
        retrievalAttempts = retrievalRes.data.attempts;
      }
      const scheduleRes = await fetchRecheckSchedule(studentId, unitId);
      if (scheduleRes.state === "ok") {
        dueSeedIndices = scheduleRes.data.seeds
          .filter((s) => s.status === "due")
          .map((s) => s.seed_index);
      }
      const reviewQueueRes = await fetchReviewQueue(studentId);
      if (reviewQueueRes.state === "ok") {
        priorReviewItems = reviewQueueRes.data.items.filter(
          (item) => item.unit_id !== unitId,
        );
      }
      if (isEnrolled) {
        const routeRes = await fetchPracticeRoute(studentId, unitId);
        if (routeRes.state === "ok") {
          routeData = routeRes.data;
        }
        const turnsRes = await fetchConciergeTurns(studentId, unitId);
        if (turnsRes.state === "ok") {
          conciergeTurns = turnsRes.data.turns;
        }
      }
    }
  }

  const manifestRes = await fetchPracticeManifest(unitId);
  const practiceManifest = manifestRes.state === "ok" ? manifestRes.data : null;
  const practiceServiceDown = manifestRes.state === "unreachable";

  /**
   * The student's latest verdict on this unit, and from it the unit's own gate
   * state for the exit card. Derived, and said here plainly: the gates reader
   * tracks the two milestone gate rules only, so a unit-to-unit unlock like
   * 3.2.1 -> 3.2.2 has no gate state to read on this page. The strongest
   * available signal is the latest verdict on this unit's submissions, the
   * same rule the progress map uses to call a unit passed. No verdict on
   * record, or the reader is down, means not passed; the card never fakes it.
   */
  let latestVerdict: "pass" | "not-yet" | "grading" | null = null;
  if (studentId !== null) {
    const submissionsRes = await fetchStudentSubmissions(studentId);
    if (submissionsRes.state === "ok") {
      const own = submissionsRes.data.submissions
        .filter((s) => s.unit_id === unitId)
        .sort(
          (a, b) =>
            (parseDbTimestamp(b.created_at)?.getTime() ?? 0) -
            (parseDbTimestamp(a.created_at)?.getTime() ?? 0),
        );
      const latest = own[0] ?? null;
      if (latest?.overall === "pass") latestVerdict = "pass";
      else if (latest?.overall === "fail") latestVerdict = "not-yet";
      else if (latest) latestVerdict = "grading";
    }
  }
  const gatePassed = latestVerdict === "pass";

  /** Distinct retrieval drills passed, or null when no drill attempts exist. */
  const retrievalPassedCount =
    retrievalAttempts.length > 0
      ? new Set(retrievalAttempts.filter((a) => a.passed).map((a) => a.seed_index)).size
      : null;

  const phaseEntry =
    loadCurriculumMap().phases.find((p) => p.phase === yaml.phase) ?? null;

  /**
   * The apparatus a script can place, keyed by the name it uses in a `::: ` marker.
   *
   * Built here rather than inside the renderer so every data prop stays exactly
   * where the page already fetched it, and so the script parser never has to know
   * that React exists. A unit that is not a script ignores this entirely.
   */
  const slots: Record<string, ReactNode> = {
    route: (
      <PracticeRouteStrip
        routeData={routeData}
        isEnrolled={isEnrolled}
        isSignedIn={isSignedIn}
        serviceDown={practiceServiceDown}
      />
    ),
    "worked-example": (
      <WorkedExampleCard workedExample={workedExample} routeData={routeData} />
    ),
    workbench: (
      <CompletionWorkbenchCard
        unitId={yaml.id}
        completionProblem={completionProblem}
        manifest={practiceManifest}
        initialAttempts={practiceAttempts}
        isEnrolled={isEnrolled}
        isSignedIn={isSignedIn}
        serviceDown={practiceServiceDown}
      />
    ),
    retrieval: (
      <RetrievalDrillCard
        unitId={yaml.id}
        retrievalSeeds={yaml.practice.retrieval_seeds}
        initialRetrievalAttempts={retrievalAttempts}
        dueSeedIndices={dueSeedIndices}
        isEnrolled={isEnrolled}
        isSignedIn={isSignedIn}
        serviceDown={practiceServiceDown}
        reviewItems={priorReviewItems}
      />
    ),
    deliverable: <DeliverableCallout unit={yaml} />,
    submission: <SubmissionContractCard unit={yaml} contract={contract} />,
    "prove-it": <ProveItCard curriculum={curriculum} />,
    "grading-modes": <GradingModesCard unit={yaml} />,
    checks: <AutomatedChecksCard checks={checks} />,
    rubric: <RubricCard rubric={rubric} />,
    unstuck: <UnstuckList unit={yaml} faq={faq} />,
    ask: (
      <ConciergePanel
        unitId={yaml.id}
        isEnrolled={isEnrolled}
        isSignedIn={isSignedIn}
        serviceDown={practiceServiceDown}
        routeData={routeData}
        initialTurns={conciergeTurns}
        embedded
      />
    ),
  };

  return (
    <article className="min-h-screen pb-24">
      <MermaidRuntime />
      <CodeFigureRuntime />
      <ChapterOpener
        unitId={yaml.id}
        phase={yaml.phase}
        title={script.title}
        specs={unitSpecs(yaml, checks?.length ?? 0, rubric?.criteria.length ?? 0, script.estMinutes)}
        beats={script.phases.flatMap((phase) =>
          phase.contents.map((entry) => ({ id: entry.id, name: entry.name, estMinutes: entry.estMinutes })),
        )}
      />
      <ResumeBanner unitId={yaml.id} />
      <ReadingTracker unitId={yaml.id} phases={script.phases} />
      <UnitScript
        phases={script.phases}
        preamble={script.preamble}
        slots={slots}
        checked={oldestVerified(yaml.last_verified)}
      />
      {/*
        The designed exit (lesson-flow spec U1), only for script units: it sits
        after this throw-guarded point, so a fixed-layout unit can never reach
        it. Fills the content track like the other apparatus.
      */}
      <UnitExitCard
        unitId={yaml.id}
        deliverable={yaml.build.deliverable}
        isSignedIn={isSignedIn}
        isEnrolled={isEnrolled}
        gatePassed={gatePassed}
        nextUnitId={yaml.gate.unlocks[0] ?? null}
        curriculumHref={phaseEntry ? `/curriculum#${phaseEntry.id}` : "/curriculum"}
        practiceAttemptCount={practiceAttempts.length}
        retrievalPassedCount={retrievalPassedCount}
        retrievalSeedCount={yaml.practice.retrieval_seeds.length}
        latestVerdict={latestVerdict}
        dueReviewCount={dueSeedIndices.length}
      />
    </article>
  );
}

/**
 * The unit's measurable facts, phrased for the opener's one mono line.
 *
 * Every cell is self-describing, because there is no label column to read them
 * against: "UNLOCKS 3.2.2" rather than a "Unlocks" heading over "3.2.2".
 */
function unitSpecs(yaml: Unit["yaml"], checkCount: number, criterionCount: number, estMinutes?: number): string[] {
  const specs = [
    `PHASE ${yaml.phase}`,
    yaml.est_hours
      ? `~${yaml.est_hours} ${yaml.est_hours === 1 ? "HOUR" : "HOURS"}`
      : "CORE DELIVERABLE",
    gradedOn(checkCount, criterionCount),
    yaml.prereq_units.length > 0 ? `NEEDS ${yaml.prereq_units.join(", ")}` : "ENTRY POINT",
    yaml.gate.unlocks.length > 0 ? `UNLOCKS ${yaml.gate.unlocks.join(", ")}` : "PHASE GATE",
    "OMNISUPPLY OPERATIONS DATA",
  ];
  if (estMinutes && estMinutes > 0) {
    // Insert reading time after hours, so scanner sees workload then read length.
    specs.splice(2, 0, `~${estMinutes} MIN READ`);
  }
  return specs;
}

/**
 * What this unit is actually graded on. A conceptual unit has no automated
 * checks, and "0 CHECKS" read as a gap in the platform rather than as the truth
 * about the unit, so each combination gets named for what it is.
 */
function gradedOn(checkCount: number, criterionCount: number): string {
  const criteria = `${criterionCount} ${criterionCount === 1 ? "CRITERION" : "CRITERIA"}`;
  if (checkCount > 0 && criterionCount > 0) return `${checkCount} AUTOMATED CHECKS, ${criteria}`;
  if (checkCount > 0) return `${checkCount} AUTOMATED CHECKS`;
  if (criterionCount > 0) return `RUBRIC REVIEW, ${criteria}`;
  return "NOT GRADED YET";
}

/** The page for a unit that is mapped but not written yet. No enrollment, no fake sections. */
function PlannedUnit({ phase, module }: { phase: MapPhase; module: MapModule }) {
  return (
    <article className="shell section">
      <nav
        aria-label="Breadcrumb"
        className="flex items-center gap-2 font-code-mono text-[12px] tracking-wider text-moss-70"
      >
        <Link href="/curriculum" className="transition-colors hover:text-phosphor-white">
          CURRICULUM
        </Link>
        <span className="opacity-40">/</span>
        <Link
          href={`/curriculum#${phase.id}`}
          className="transition-colors hover:text-phosphor-white"
        >
          PHASE-{phase.phase}
        </Link>
        <span className="opacity-40">/</span>
        <span className="text-phosphor-white">UNIT-{module.id}</span>
      </nav>

      <div className="mt-8 max-w-[68ch]">
        <span className="chip chip-outline">PLANNED</span>
        <h1 className="heading-xl mt-5">{module.title}</h1>
        <p className="mt-5 text-[16px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {module.description}
        </p>
        <p className="mt-6 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          This unit is mapped and its place in the build is fixed. The lesson, the practice
          set and the rubric are not written yet: nothing here is enrollable, and nothing
          is hiding behind a payment. When the unit opens, this page becomes the unit:
          same URL, nothing to re-bookmark.
        </p>
        <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          It sits in Phase {phase.phase}, {phase.title}. {phase.outcome}
        </p>
        <div className="mt-9 flex flex-wrap gap-4">
          <Link href={`/curriculum#${phase.id}`} className="btn btn-primary btn-sm">
            See the rest of this phase
          </Link>
          <Link href="/curriculum" className="btn btn-ghost btn-sm">
            Units open today
          </Link>
        </div>
      </div>
    </article>
  );
}
