import type { Metadata } from "next";
import Link from "next/link";
import { requireSession } from "@/lib/auth";
import {
  ensureStudent,
  fetchProfile,
  fetchOwnSubmissions,
  formatPrice,
  type OwnSubmission,
} from "@/lib/enroll";
import { fetchStudentGates } from "@/lib/gates";
import { formatUtc } from "@/lib/grading";
import {
  buildProgressMap,
  type ResolvedPhase,
  type ResolvedModuleCard,
} from "@/lib/map";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Progress map",
  description:
    "Every phase and unit in the OmniCart operations pipeline, with your enrollment, submission, and gate status.",
  robots: { index: false },
};

const CHECKOUT_ERRORS: Record<string, string> = {
  unreachable: "We could not reach enrollment. Try again.",
  app_not_configured: "Enrollment is not configured yet. Try again.",
  stripe_not_wired: "Payments are not configured yet.",
  stripe_unreachable: "The payment provider did not answer. Nothing was charged.",
  stripe_error: "The payment provider rejected the request. Nothing was charged.",
  email_linked_to_other_account:
    "This email belongs to a different account. Sign in with that account to enroll.",
};

type Props = { searchParams: Promise<{ checkout?: string; phase?: string }> };

export default async function MapPage({ searchParams }: Props) {
  const { checkout } = await searchParams;
  const user = await requireSession("/map");
  const bridged = await ensureStudent(user);

  if (bridged.state !== "ok") {
    return (
      <div className="shell section">
        <div className="card-dark max-w-[60ch]">
          <p className="eyebrow">Profile unavailable</p>
          <h1 className="heading-lg mt-3">We could not load your map</h1>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            You are signed in, but your progress would not load.
            Nothing is lost. Refresh and the map will load.
          </p>
          <Link href="/me" className="btn btn-ghost btn-sm mt-7">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  const studentId = bridged.data;
  const [profileResult, submissionsResult, gatesLookup] = await Promise.all([
    fetchProfile(studentId),
    fetchOwnSubmissions(studentId),
    fetchStudentGates(studentId),
  ]);

  const profile = profileResult.state === "ok" ? profileResult.data : null;
  const submissions = submissionsResult.state === "ok" ? submissionsResult.data.submissions : [];
  const gates = gatesLookup.state === "ok" ? gatesLookup.data : null;

  const mapState = buildProgressMap(profile, submissions, gates);

  return (
    <div>
      <header className="shell border-b border-[color:var(--line-on-dark)] pb-12 pt-14">
        <div className="flex flex-wrap items-start justify-between gap-8">
          <div className="max-w-[62ch]">
            <p className="eyebrow">OmniCart Operations · your build map</p>
            <h1 className="heading-xl mt-4">The whole system, phase by phase</h1>
            <p className="lead mt-5">
              Thirteen phases, one invoice reconciliation and dispute triage
              pipeline. Every card names the unit&apos;s component, whether
              you can open it, and your last verdict.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="chip chip-outline">Student #{studentId}</span>
            <Link href="/me" className="btn btn-ghost btn-sm">
              Open dashboard
            </Link>
          </div>
        </div>

        {checkout ? (
          <div
            role="alert"
            className="mt-8 rounded-lg border border-circuit-border bg-carbon-veil p-5"
          >
            <p className="flex flex-wrap items-center gap-3 text-[15px] leading-relaxed text-phosphor-white">
              <span className="chip chip-alert">CHECKOUT FAILED</span>
              {CHECKOUT_ERRORS[checkout] ?? "Checkout could not start. Nothing was charged."}
            </p>
          </div>
        ) : null}

        <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-circuit-border bg-circuit-border sm:grid-cols-2 lg:grid-cols-5">
          <MetricCard
            label="Phase tracks"
            value={`${mapState.stats.unlockedPhases} / ${mapState.stats.totalPhases}`}
            detail="Tracks open to you right now"
          />
          <MetricCard
            label="Units passed"
            value={`${mapState.stats.passedUnits} / ${mapState.stats.authoredUnits}`}
            detail="Of the units written so far"
          />
          <MetricCard
            label="Gates cleared"
            value={`${mapState.stats.clearedGates} / ${mapState.stats.totalGates}`}
            detail="Phase 5 integration and capstone"
          />
          <MetricCard
            label="Rebates earned"
            value={formatPrice(mapState.stats.earnedRebatesCents, "usd")}
            detail={
              mapState.stats.earnedRebatesCents > 0
                ? "Credited to your payment method"
                : "15% back at each of the two gates"
            }
          />
          <MetricCard
            label="Grading budget"
            value={
              mapState.stats.tokensCap > 0
                ? `${Math.round((mapState.stats.tokensUsed / mapState.stats.tokensCap) * 100)}%`
                : "Not set"
            }
            detail={
              mapState.stats.tokensCap > 0
                ? `${mapState.stats.tokensUsed.toLocaleString("en-US")} of ${mapState.stats.tokensCap.toLocaleString("en-US")} used`
                : "No grading budget cap assigned yet"
            }
          />
        </div>

        <nav aria-label="Jump to phase" className="mt-10 flex flex-wrap gap-2">
          {mapState.phases.map((p) => (
            <a
              key={p.phase.id}
              href={`#${p.phase.id}`}
              className="chip chip-outline hover:border-moss-70 hover:text-phosphor-white"
            >
              P{p.phase.phase}
            </a>
          ))}
          <a
            href="#graduation"
            className="chip chip-outline hover:border-moss-70 hover:text-phosphor-white"
          >
            Graduation
          </a>
        </nav>
      </header>

      <div className="shell">
        <section aria-labelledby="pipeline-title" className="section-tight">
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div className="max-w-[58ch]">
              <h2 id="pipeline-title" className="heading-lg">
                How the phases connect
              </h2>
              <p className="mt-3 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                Four tracks form one pipeline. Each track ships a component the next one
                needs.
              </p>
            </div>
            <span className="chip chip-outline">Anchor client: OmniCart Operations</span>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <PipelineTrack
              title="1. Intake and foundations"
              phases="Phases 0 to 1"
              role="Docker runtime, pytest harnesses, and the async HTTP intake endpoint."
            />
            <PipelineTrack
              title="2. Extraction and grounding"
              phases="Phases 2 to 4"
              role="Model behaviour, strict Pydantic extraction (unit 3.2.1), and grounded search over supplier agreements."
            />
            <PipelineTrack
              title="3. Agents and adaptation"
              phases="Phases 5 to 6"
              role="Dispute routing agent, hard stop conditions, and domain adaptation."
              gateBadge="15% rebate gate"
            />
            <PipelineTrack
              title="4. Evaluation, ops, capstone"
              phases="Phases 7 to 12"
              role="Automated evaluation in CI, cost routing, audit logging, and production deployment."
              gateBadge="15% rebate gate"
            />
          </div>
        </section>

        <div className="space-y-10 pb-4">
          {mapState.phases.map((phase) => (
            <PhaseSection key={phase.phase.id} phase={phase} />
          ))}
        </div>

        <section id="graduation" aria-labelledby="graduation-title" className="section scroll-mt-24">
          <p className="eyebrow">After phase 12</p>
          <h2 id="graduation-title" className="heading-lg mt-3">
            What graduation requires
          </h2>
          <p className="mt-3 max-w-[62ch] text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Five checks stand between you and graduation. Clear all five and we publish
            your record.
          </p>
          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <GradCheck
              num="01"
              title="Golden set accuracy"
              description="We measure precision and recall on held-out adversarial dispute cases you have never seen."
            />
            <GradCheck
              num="02"
              title="Defend your work"
              description="Answer short unscripted questions about the code you submitted."
            />
            <GradCheck
              num="03"
              title="Technical stakeholder review"
              description="A simulated technical review that asks for telemetry, cost caps, and audit logs."
            />
            <GradCheck
              num="04"
              title="Business owner review"
              description="A simulated commercial review on unit economics and what your scope excludes."
            />
            <GradCheck
              num="05"
              title="Real outreach"
              description="Send one outreach email to a real business, with a priced scope of work attached."
            />
            <div className="rounded-lg border border-circuit-border bg-carbon-veil p-5">
              <p className="eyebrow">Your record</p>
              <p className="mt-3 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                Clearing all five publishes a profile linking every verdict to the exact
                commit you pushed.
              </p>
              <Link href="/submit" className="btn btn-ghost btn-sm mt-6">
                Read the submission guide
              </Link>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="bg-ground-iron p-5">
      <p className="stat-number">{value}</p>
      <p className="stat-label">{label}</p>
      <p className="mt-2 text-[13px] leading-snug text-[color:var(--text-faint-on-dark)]">
        {detail}
      </p>
    </div>
  );
}

function PipelineTrack({
  title,
  phases,
  role,
  gateBadge,
}: {
  title: string;
  phases: string;
  role: string;
  gateBadge?: string;
}) {
  return (
    <div className="rounded-lg border border-circuit-border bg-ground-iron p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-goga text-[15.5px] font-medium text-phosphor-white">
          {title}
        </span>
        {gateBadge ? <span className="chip chip-outline">{gateBadge}</span> : null}
      </div>
      <p className="mt-2 text-[12px] font-medium uppercase tracking-[0.6px] text-moss-70">
        {phases}
      </p>
      <p className="mt-3 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        {role}
      </p>
    </div>
  );
}

function PhaseSection({
  phase,
}: {
  phase: ResolvedPhase;
}) {
  const p = phase.phase;
  const isLocked = !phase.isTrackUnlocked;

  return (
    <section id={p.id} aria-labelledby={`${p.id}-title`} className="card-dark scroll-mt-24">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="max-w-[64ch]">
          <div className="flex flex-wrap items-center gap-3">
            <span className="chip chip-outline">Phase {p.phase}</span>
            <span className="text-[12px] font-medium uppercase tracking-[0.6px] text-moss-70">
              ~{p.est_hours} {p.est_hours === 1 ? "hour" : "hours"}
            </span>
            {p.badge ? <span className="chip chip-outline">{p.badge}</span> : null}
          </div>
          <h2 id={`${p.id}-title`} className="heading-md mt-4">
            {p.title}
          </h2>
          <p className="mt-2 text-[14px] leading-relaxed text-[color:var(--text-faint-on-dark)]">
            Its job in the pipeline: {p.pipeline_role}
          </p>
        </div>
        {phase.gateCleared ? (
          <span className="chip chip-live">GATE CLEARED</span>
        ) : isLocked ? (
          <span className="chip chip-outline">TRACK LOCKED</span>
        ) : (
          <span className="chip chip-outline">TRACK OPEN</span>
        )}
      </div>

      <div className="mt-7 grid gap-6 md:grid-cols-2">
        <div>
          <p className="eyebrow">Why it exists</p>
          <p className="mt-2 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            {p.why}
          </p>
        </div>
        <div>
          <p className="eyebrow">What you walk away with</p>
          <p className="mt-2 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            {p.outcome}
          </p>
        </div>
      </div>

      {phase.lockReason ? (
        <p className="mt-6 rounded-md border border-circuit-border bg-carbon-veil p-4 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {phase.lockReason}
        </p>
      ) : null}

      {phase.gateRule ? (
        <div className="mt-6 flex flex-wrap items-start justify-between gap-4 rounded-lg border border-circuit-border bg-carbon-veil p-5">
          <div className="max-w-[60ch]">
            <div className="flex flex-wrap items-center gap-3">
              <h3 className="heading-md">{phase.gateRule.title}</h3>
              {phase.gateRule.rebate ? (
                <span className="chip chip-outline">15% rebate</span>
              ) : null}
            </div>
            <p className="mt-2 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              {phase.gateCleared
                ? `Cleared on ${formatUtc(phase.gateCleared.passed_at)}.`
                : phase.gateRule.summary}
            </p>
          </div>
          <span className={phase.gateCleared ? "chip chip-live" : "chip chip-outline"}>
            {phase.gateCleared ? "CLEARED" : "LOCKED"}
          </span>
        </div>
      ) : null}

      <div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {phase.modules.map((card) => (
          <ModuleCard
            key={card.module.id}
            card={card}
          />
        ))}
      </div>
    </section>
  );
}

function verdictLabel(sub: OwnSubmission): string {
  if (sub.overall === "pass") return "PASSED";
  if (sub.overall === "fail") return "NOT YET";
  return sub.status.toUpperCase();
}

function ModuleCard({
  card,
}: {
  card: ResolvedModuleCard;
}) {
  const m = card.module;
  const sub = card.latestSubmission;

  return (
    <div className="flex flex-col justify-between rounded-lg border border-circuit-border bg-carbon-veil p-5">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-code-mono text-[13px] text-moss-70">Unit {m.id}</span>
          <StatusChip status={card.status} />
        </div>
        <h4 className="font-goga mt-3 text-[15.5px] font-medium leading-snug text-phosphor-white">
          {m.title}
        </h4>
        <p className="mt-2 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {m.description}
        </p>

        {card.lockReason && !card.isAuthored ? (
          <p className="mt-3 text-[13px] leading-relaxed text-[color:var(--text-faint-on-dark)]">
            {card.lockReason}
          </p>
        ) : null}

        {sub ? (
          <div className="mt-4 border-t border-[color:var(--line-on-dark)] pt-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link
                href={`/submissions/${sub.id}`}
                className="text-[13px] text-fern-link underline underline-offset-4 hover:text-phosphor-white"
              >
                Submission #{sub.id}
              </Link>
              <span className="chip chip-outline">{verdictLabel(sub)}</span>
            </div>
            <p className="mt-2 text-[12px] text-[color:var(--text-faint-on-dark)]">
              {formatUtc(sub.created_at)}
            </p>
          </div>
        ) : null}
      </div>

      <div className="mt-5">
        {card.isAuthored ? (
          card.isEnrolled ? (
            <Link href={`/units/${m.id}`} className="btn btn-primary btn-sm">
              Open unit
            </Link>
          ) : (
            <Link href="/checkout" className="btn btn-accent btn-sm">
              Get all access
            </Link>
          )
        ) : (
          <p className="text-[13px] text-[color:var(--text-faint-on-dark)]">
            Content in progress. Nothing to open yet.
          </p>
        )}
      </div>
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  switch (status) {
    case "passed":
      return <span className="chip chip-live">PASSED</span>;
    case "failed":
      return <span className="chip chip-alert">NOT YET</span>;
    case "error":
      return <span className="chip chip-alert">GRADING ERROR</span>;
    case "grading":
      return <span className="chip chip-outline">GRADING</span>;
    case "queued":
      return <span className="chip chip-outline">QUEUED</span>;
    case "enrolled":
      return <span className="chip chip-outline">ENROLLED</span>;
    case "available":
      return <span className="chip chip-outline">OPEN</span>;
    case "locked":
    case "not_authored_locked":
      return <span className="chip chip-outline">LOCKED</span>;
    case "not_authored_unlocked":
    case "not_authored":
    default:
      return <span className="chip chip-outline">PLANNED</span>;
  }
}

function GradCheck({
  num,
  title,
  description,
}: {
  num: string;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-lg border border-circuit-border bg-ground-iron p-5">
      <div className="flex items-baseline gap-3">
        <span className="font-code-mono text-[13px] text-moss-70">{num}</span>
        <h3 className="font-goga text-[15.5px] font-medium text-phosphor-white">
          {title}
        </h3>
      </div>
      <p className="mt-2 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        {description}
      </p>
    </div>
  );
}
