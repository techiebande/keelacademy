import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  assertValidUnitId,
  loadCurriculumMap,
  loadUnit,
  type MapModule,
  type MapPhase,
  type Unit,
} from "@/lib/content";
import { CompletionWorkbenchCard, RetrievalDrillCard } from "@/components/unit/practice-section";
import { SubmissionContractCard } from "@/components/unit/build-section";
import { AutomatedChecksCard, RubricCard } from "@/components/unit/verify-section";
import { ConciergePanel } from "@/components/unit/concierge-panel";
import { LessonBody } from "@/components/unit/lesson-body";
import { UnitExitCard } from "@/components/unit/unit-exit-card";
import { MermaidRuntime } from "@/components/unit/mermaid-runtime";
import { CodeFigureRuntime } from "@/components/unit/code-figure";
import { ChapterOpener } from "@/components/unit/chapter-opener";
import { ResumeBanner } from "@/components/unit/resume-banner";
import { ReadingTracker } from "@/components/unit/reading-tracker";
import { getSessionUser } from "@/lib/auth";
import { fetchStudentSubmissions, parseDbTimestamp } from "@/lib/grading";
import { ensureStudent, enrollInUnit, fetchProfile, fetchSubscriptionPrice, formatPrice } from "@/lib/enroll";
import { UnitPaywallCard } from "@/components/unit/unit-paywall-card";
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
    title: `Unit ${unit.yaml.id}: ${unit.lesson.title}`,
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

  const { yaml, lesson, assignment, checks, contract, rubric } = unit;

  const user = await getSessionUser();
  const isSignedIn = !!user;
  const isFreeSample = unitId === "0.1";
  let isEnrolled = false;
  let hasActiveSub = false;
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
        const sub = profileRes.data.subscription;
        hasActiveSub = sub?.status === "active" || sub?.status === "trialing";
        isEnrolled = profileRes.data.enrollments.some(
          (e) => e.unit_id === unitId && e.status === "active",
        );
        if ((hasActiveSub || isFreeSample) && !isEnrolled) {
          const enrollRes = await enrollInUnit({ studentId, unitId });
          if (enrollRes.state === "ok" && enrollRes.data.enrolled) {
            isEnrolled = true;
          }
        }
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

  const isCodeUnit = (yaml.kind ?? "code") === "code";
  const hasAccess = isFreeSample || hasActiveSub || isEnrolled;

  if (!hasAccess) {
    const priceRes = await fetchSubscriptionPrice();
    const priceLabel =
      priceRes.state === "ok"
        ? formatPrice(priceRes.data.amount_cents, priceRes.data.currency)
        : "$49";

    return (
      <article className="min-h-screen pb-24">
        <ChapterOpener
          unitId={yaml.id}
          phase={yaml.phase}
          title={lesson.title}
          specs={unitSpecs(yaml, checks?.length ?? 0, rubric?.criteria.length ?? 0, lesson.estMinutes)}
          beats={openerBeats(lesson)}
        />
        <UnitPaywallCard unitId={yaml.id} priceLabel={priceLabel} />
      </article>
    );
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

  return (
    <article className="min-h-screen pb-24">
      <MermaidRuntime />
      <CodeFigureRuntime />
      <ChapterOpener
        unitId={yaml.id}
        phase={yaml.phase}
        title={lesson.title}
        specs={unitSpecs(yaml, checks?.length ?? 0, rubric?.criteria.length ?? 0, lesson.estMinutes)}
        beats={openerBeats(lesson)}
      />
      <ResumeBanner unitId={yaml.id} />
      <ReadingTracker unitId={yaml.id} lesson={lesson} />
      <LessonBody lesson={lesson} assignment={assignment} />
      {/*
        The platform's own apparatus, after every authored word. Each card is
        labelled by what it is and says nothing about the lesson: the assignment
        above has already said, in the author's words, what to build and how it
        is checked.
      */}
      <div className="lesson-canvas flow unit-script-layout">
        <div className="flow unit-script-body">
          {isCodeUnit ? (
            <div className="flow-apparatus">
              <CompletionWorkbenchCard
                unitId={yaml.id}
                manifest={practiceManifest}
                initialAttempts={practiceAttempts}
                isEnrolled={isEnrolled}
                isSignedIn={isSignedIn}
                serviceDown={practiceServiceDown}
              />
            </div>
          ) : null}
          <div id="submission" className="flow-apparatus">
            <SubmissionContractCard unit={yaml} contract={contract} />
          </div>
          {checks ? (
            <div id="checks" className="flow-apparatus">
              <AutomatedChecksCard checks={checks} />
            </div>
          ) : null}
          {rubric ? (
            <div id="rubric" className="flow-apparatus">
              <RubricCard rubric={rubric} />
            </div>
          ) : null}
          <div id="recall" className="flow-apparatus">
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
          </div>
          <div className="flow-apparatus">
            <ConciergePanel
              unitId={yaml.id}
              isEnrolled={isEnrolled}
              isSignedIn={isSignedIn}
              serviceDown={practiceServiceDown}
              routeData={routeData}
              initialTurns={conciergeTurns}
              embedded
            />
          </div>
        </div>
      </div>
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

/** The opener's list of beats: every `##` heading across the chapters, with its share of the read time. */
function openerBeats(lesson: Unit["lesson"]): { id: string; name: string; estMinutes?: number }[] {
  return lesson.chapters.flatMap((chapter) => {
    const sections = chapter.headings.filter((h) => h.level === 2);
    const minutesEach = sections.length > 0 ? Math.max(1, Math.round(chapter.estMinutes / sections.length)) : undefined;
    return sections.map((h) => ({ id: h.id, name: h.text, estMinutes: minutesEach }));
  });
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
    "LANTERN HOME DATA",
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
