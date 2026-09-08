import Link from "next/link";
import {
  listUnits,
  loadCurriculumMap,
  loadPlacementDiagnostic,
  loadUnit,
} from "@/lib/content";

export const dynamic = "force-dynamic";

export default function HomePage() {
  const units = listUnits();
  const first = units[0];
  const firstUnit = first ? loadUnit(first.id) : null;
  const rubricCriteria = firstUnit?.rubric?.criteria ?? [];

  // Every figure on this page is read from content/, so the landing claims
  // cannot drift from the curriculum they describe.
  const map = loadCurriculumMap();
  const phaseCount = map.phases.length;
  const totalHours = map.phases.reduce((sum, p) => sum + p.est_hours, 0);
  const placement = loadPlacementDiagnostic("placement-phase-1");

  return (
    <div>
      {/* Hero */}
      <section className="shell grid items-center gap-16 pb-24 pt-16 lg:grid-cols-[1.05fr_0.95fr] lg:pt-24">
        <div>
          <p className="eyebrow">Applied AI engineering program</p>
          <h1 className="display-heading mt-5">
            Stop demoing.{" "}
            <span className="text-lime-pulse">
              Ship an AI system that survives real invoices.
            </span>
          </h1>
          <p className="lead mt-6">
            Most AI courses end right where things get interesting, at the
            moment the demo meets messy vendor PDFs and the model starts
            inventing totals. I have watched brilliant engineers stall at
            exactly that wall. Keel starts there: across {phaseCount}{" "}
            phases you build an invoice reconciliation and dispute triage
            pipeline for OmniCart Operations, a simulated B2B
            distributor, from first commit to deployed system. Every
            submission runs against real tests and a published rubric. It
            passes only when the work holds up.
          </p>
          <div className="mt-9 flex flex-wrap gap-4">
            <Link href="/sign-up" className="btn btn-accent">
              Start building
            </Link>
            <Link href="/curriculum" className="btn btn-ghost">
              See the curriculum
            </Link>
          </div>
          <p className="mt-5 text-[14px] text-[color:var(--text-faint-on-dark)]">
            Enroll per unit. Clear a milestone gate. Get 15% back.
          </p>
        </div>

        {/* Grading preview panel: the real rubric, loaded live from content */}
        {rubricCriteria.length > 0 ? (
          <aside
            aria-label="What passing looks like"
            className="code-block code-window"
          >
            <span className="code-title" aria-hidden>
              rubric-{first.id}.yaml
            </span>
            <div className="flex items-center justify-between gap-4">
              <p className="eyebrow">What passing looks like</p>
              <span className="chip chip-outline">Unit {first.id}</span>
            </div>
            <p className="mt-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              Here is the deal: every unit publishes its rubric before you
              build. Automated checks and rubric review grade your submission
              against each criterion, and each verdict has to quote the lines
              of your own code that earned it. No quotes, no pass.
            </p>
            <ul className="mt-6 space-y-5">
              {rubricCriteria.slice(0, 4).map((criterion) => (
                <li key={criterion.id} className="flex gap-3.5">
                  <svg
                    aria-hidden
                    className="mt-1 shrink-0"
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="none"
                  >
                    <circle cx="8" cy="8" r="7" stroke="var(--color-lime-pulse)" strokeWidth="1.4" />
                    <path
                      d="M4.8 8.2l2.1 2.1 4.3-4.6"
                      stroke="var(--color-lime-pulse)"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <div>
                    <p className="font-goga text-[15px] font-medium text-phosphor-white">
                      {criterion.id
                        .split("-")
                        .map((w, i) =>
                          i === 0
                            ? w.charAt(0).toUpperCase() + w.slice(1)
                            : w,
                        )
                        .join(" ")}
                    </p>
                    <p className="mt-1 text-[13.5px] leading-relaxed text-[color:var(--text-faint-on-dark)]">
                      {criterion.description.split(".")[0]}.
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            <p className="mt-7 border-t border-[color:var(--line-on-dark)] pt-4 text-[12.5px] text-[color:var(--text-faint-on-dark)]">
              This is the real rubric for Unit {first.id}, loaded live from
              the curriculum, the same file the grader reads.{" "}
              {firstUnit?.checks?.length ?? 0} automated checks run on every
              submission first.
            </p>
          </aside>
        ) : null}
      </section>

      {/* Stats */}
      <section aria-label="Program at a glance" className="shell pb-24">
        <div className="grid grid-cols-2 gap-x-8 gap-y-10 md:grid-cols-4">
          <div>
            <p className="stat-number">{phaseCount}</p>
            <p className="stat-label">Phases, one system</p>
          </div>
          <div>
            <p className="stat-number">{totalHours}</p>
            <p className="stat-label">Hours of real build work</p>
          </div>
          <div>
            <p className="stat-number">3</p>
            <p className="stat-label">Ways every milestone is checked</p>
          </div>
          <div>
            <p className="stat-number">15%</p>
            <p className="stat-label">Rebate at each milestone gate</p>
          </div>
        </div>
      </section>

      {/* How a unit works */}
      <section className="section" id="how-it-works">
        <div className="shell">
          <div className="max-w-[62ch]">
            <p className="eyebrow">How a unit works</p>
            <h2 className="heading-xl mt-4">
              Six steps. Same loop, every unit: you will know it by heart
              by week two.
            </h2>
            <p className="lead mt-5">
              Each unit is a small build with the same heartbeat: learn the
              concept, practice on a parallel task, ship the deliverable, get
              it graded, get unstuck fast, move on. No surprises after unit
              one, because the surprise budget goes to the ideas, where it belongs.
            </p>
          </div>

          <ol className="mt-14 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[
              {
                step: "01",
                title: "Learn",
                body: "One written lesson, read start to finish. It opens with the concept, grounds it in the client's numbers, then shows exactly what you are about to produce, with checkpoints you answer before you peek. (Peeking is allowed. Peeking first is noticeable.)",
              },
              {
                step: "02",
                title: "Practice",
                body: "Study a fully worked example of a parallel task, then fill the gaps in a completion problem. Automated checks grade every save, so you always know exactly where you stand.",
              },
              {
                step: "03",
                title: "Build",
                body: "Ship the deliverable to your own git repository. The deliverable and the submission contract are published up front, so you will never have to guess what 'done' means.",
              },
              {
                step: "04",
                title: "Verify",
                body: "Push, and automated checks plus rubric review get to work. Every verdict quotes evidence from your code, so a Not yet always tells you what to fix.",
              },
              {
                step: "05",
                title: "Unstuck",
                body: "Every unit lists the ways it usually breaks, each with its fix. And an assistant that has read that exact unit answers questions, even at 2am.",
              },
              {
                step: "06",
                title: "Move on",
                body: "Pass a unit and the next one opens. Pass a milestone gate and 15% comes back to your card. Only verified work moves you forward, and that is the whole transcript.",
              },
            ].map((item) => (
              <li
                key={item.step}
                className="card-dark p-7"
              >
                <span className="text-[12px] font-medium tracking-[0.12em] text-moss-70">
                  STEP {item.step}
                </span>
                <h3 className="heading-md mt-3">
                  {item.title}
                </h3>
                <p className="mt-2.5 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  {item.body}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Grading */}
      <section className="section" id="grading">
        <div className="shell">
          <div className="max-w-[62ch]">
            <p className="eyebrow">Graded for real</p>
            <h2 className="heading-xl mt-4">
              A pass means the work held up. Here is exactly how we check.
            </h2>
            <p className="lead mt-5">
              This program grades what you shipped, against a bar you read
              before you started. Three stages, every milestone:
            </p>
          </div>

          <div className="mt-14 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[
              {
                num: "1",
                title: "Automated checks",
                body: "Your code runs in an isolated run against the unit's test suite and data. Results list each automated check as Passed or Not yet, with the full command output, so you see exactly what the grader saw.",
              },
              {
                num: "2",
                title: "Rubric review",
                body: "A language model reads your submission against the unit's published criteria and quotes the lines of your code behind every verdict. No quoted evidence? The verdict reads Not yet. That is the rule that keeps the whole system honest.",
              },
              {
                num: "3",
                title: "Defend the build",
                body: "Milestone work gets defended out loud, once to a technical reviewer and once to the budget holder. Both are AI playing a written brief you can read first, and your side is scored against a rubric. Paste-and-pray does not survive this room.",
              },
            ].map((stage) => (
              <article key={stage.num} className="card-dark p-8">
                <div className="flex items-baseline gap-4">
                  <span className="font-goga text-[28px] font-medium text-phosphor-white">
                    {stage.num}
                  </span>
                  <h3 className="font-goga text-[20px] font-medium text-phosphor-white">
                    {stage.title}
                  </h3>
                </div>
                <p className="mt-3 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  {stage.body}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* Support */}
      <section className="shell section-tight" id="support">
        <div className="card-dark p-8 lg:p-12">
          <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr]">
            <div>
              <p className="eyebrow">Support on every unit</p>
              <h2 className="heading-lg mt-4">
                Help that shows up at 2am, scoped to the exact lesson.
              </h2>
              <p className="mt-5 max-w-[46ch] text-[16px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                Stuck is normal; stuck for a week is a curriculum bug, and we
                treat it like one. Each unit ships its failure modes with
                fixes, plus an assistant that knows the lesson.
              </p>
              <div className="mt-8 flex flex-wrap gap-4">
                <Link href="/curriculum" className="btn btn-primary">
                  Browse the units
                </Link>
                <Link href="/faq" className="btn btn-ghost">
                  Read the FAQ
                </Link>
              </div>
            </div>
            <ul className="space-y-7">
              {[
                {
                  title: "An assistant scoped to the unit",
                  body: "Ask why a concept works. Ask for another exercise. Ask about the error that has been glaring at you since midnight. It answers from the curriculum only, so it will not hallucinate a syllabus.",
                },
                {
                  title: "Planned failure modes, published",
                  body: "Every unit lists what usually breaks, each with its fix linked. Most stuck moments end in one click, and the rest end in the assistant.",
                },
                {
                  title: "A pod that ships with you",
                  body: "Each week you post what shipped, what broke, and what is next. Peers review milestone work against the same rubric the platform uses: harsh, but it is the same harsh for everyone.",
                },
                {
                  title: "A public gallery of real work",
                  body: "Passed projects can go public with their verification attached. Employers never have to take your word for it, because they can read the verdict.",
                },
              ].map((item) => (
                <li key={item.title} className="flex gap-4">
                  <span
                    aria-hidden
                    className="mt-[9px] h-2 w-2 shrink-0 rounded-full bg-lime-pulse"
                  />
                  <div>
                    <h3 className="font-goga text-[17px] font-medium text-phosphor-white">
                      {item.title}
                    </h3>
                    <p className="mt-1 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                      {item.body}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Units */}
      <section className="shell section" id="units">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-[56ch]">
            <p className="eyebrow">Curriculum units</p>
            <h2 className="heading-lg mt-4">
              Start here. These units are open today.
            </h2>
            <p className="mt-4 text-[16px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              Every unit page shows the lesson, the practice set, the
              deliverable, and the rubric: all four, before you pay a cent.
            </p>
          </div>
          <Link href="/curriculum" className="btn btn-ghost btn-sm">
            All {phaseCount} phases
          </Link>
        </div>

        {units.length > 0 ? (
          <ul className="mt-10 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {units.map((u) => {
              const unit = loadUnit(u.id);
              return (
                <li key={u.id} className="card-dark flex flex-col p-7">
                  <div className="flex items-center justify-between gap-3">
                    <span className="chip chip-outline">Unit {u.id}</span>
                    <span className="text-[13px] text-[color:var(--text-faint-on-dark)]">
                      Phase {u.phase}
                    </span>
                  </div>
                  <h3 className="mt-4 font-goga text-[19px] font-medium leading-snug text-phosphor-white">
                    {unit?.script?.title ?? unit?.curriculum?.title ?? `Unit ${u.id}`}
                  </h3>
                  <p className="mt-2 line-clamp-3 text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                    {unit?.yaml.build.deliverable}
                  </p>
                  <div className="mt-6 flex-1" />
                  <Link href={`/units/${u.id}`} className="btn btn-ghost btn-sm self-start">
                    Open the unit
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : null}
      </section>

      {/* Final CTA */}
      <section className="shell pb-8">
        <div className="card-dark flex flex-col items-start justify-between gap-8 p-12 md:flex-row md:items-center">
          <div>
            <h2 className="heading-lg">Your first submission is one push away. Seriously.</h2>
            <p className="mt-3 max-w-[48ch] text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              Create an account
              {placement ? `, take the ${placement.est_minutes}-minute placement check or skip it,` : ","} and
              open your first unit in the same session.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-4">
            <Link href="/sign-up" className="btn btn-primary">
              Start building
            </Link>
            <Link href="/pricing" className="btn btn-ghost">
              See pricing
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
