import type { Metadata } from "next";
import Link from "next/link";
import { listUnits } from "@/lib/content";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "How to submit",
  description:
    "How to name your repository, push a commit for grading, and read the verdict that comes back.",
};

const STATUS_TAXONOMY = [
  {
    status: "QUEUED",
    summary: "Your push arrived.",
    detail:
      "We recorded the commit. It waits in line to run, and nothing has run yet.",
  },
  {
    status: "GRADING",
    summary: "Your code is running.",
    detail:
      "The automated checks execute first. Rubric review reads the same commit afterwards.",
  },
  {
    status: "GRADED",
    summary: "There is a verdict.",
    detail:
      "Passed or Not yet. Every automated check and every rubric criterion quotes the lines it relied on.",
  },
  {
    status: "ERROR",
    summary: "Grading stopped early.",
    detail:
      "The run broke, or you had spent your grading budget. We wrote no verdict, and this does not count as an attempt.",
  },
];

const LIFECYCLE_STEPS = [
  {
    name: "You push to main",
    detail: "Commit your work and push it. That push is the submission.",
    code: "git add .\ngit commit -m 'unit 3.2.1: reconcile invoice lines'\ngit push origin main",
  },
  {
    name: "We accept the commit",
    detail: "GitHub sends a webhook. We verify its signature and enqueue grading.",
    code: "keel: submission received for commit 4f2a1c9",
  },
  {
    name: "Automated checks run in isolation",
    detail:
      "We clone your repository into a fresh, isolated run with nothing left over from anyone else. The unit's automated checks run against it.",
    code: "pytest -v tests/",
  },
  {
    name: "The rubric review reads your code",
    detail:
      "We judge each criterion against the published rubric. Each one quotes the lines it relied on: no quote, no verdict.",
    code: "criterion 1: Passed",
  },
];

export default function SubmitPage() {
  const units = listUnits();
  const first = units[0];
  const unitId = first ? first.id : "0.1";

  return (
    <div className="pb-24">
      <header className="shell pb-12 pt-14">
        <p className="eyebrow">Submitting work</p>
        <h1 className="heading-xl mt-4 max-w-[24ch]">How to push your work for grading</h1>
        <p className="lead mt-5">
          You write code in your own repository. Push it and grading starts on
          its own, with nothing to upload and no form to fill in. Pushing{" "}
          <em>is</em> the submission.
        </p>
      </header>

      <div className="shell space-y-12">
        <section aria-labelledby="repo-title" className="card-dark border-l-2 border-l-lime-pulse">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 id="repo-title" className="heading-md">
              Name the repository like this
            </h2>
            <span className="chip chip-outline">REQUIRED</span>
          </div>
          <p className="mt-4 max-w-[68ch] text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Each unit gets its own repository. Include the unit id in the name so we
            know which unit a push belongs to.
          </p>
          <div className="mt-6 flex flex-col justify-between gap-2 rounded-lg border border-circuit-border bg-carbon-veil p-4 font-code-mono text-[14px] sm:flex-row sm:items-center">
            <span className="text-phosphor-white">
              keel-<span className="font-medium text-lime-pulse">{unitId}</span>-your-suffix
            </span>
            <span className="text-[12px] text-[color:var(--text-faint-on-dark)]">
              Unit {unitId}
            </span>
          </div>
          <p className="mt-4 max-w-[68ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            The suffix is yours. Anything you like goes there.
          </p>
        </section>
        <section aria-labelledby="after-title" className="space-y-6">
          <div className="max-w-[62ch]">
            <p className="eyebrow">Four steps, no waiting on a person</p>
            <h2 id="after-title" className="heading-lg mt-3">
              What happens after the push
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              Every submission goes through the same four steps in the same order.
            </p>
          </div>

          <ol className="grid gap-6 md:grid-cols-2">
            {LIFECYCLE_STEPS.map((step, idx) => (
              <li
                key={step.name}
                className="card-dark flex flex-col justify-between space-y-4 p-7"
              >
                <div className="space-y-2">
                  <span className="font-code-mono text-[12px] font-medium text-lime-pulse">
                    Step {idx + 1}
                  </span>
                  <h3 className="font-goga text-[18px] font-medium text-phosphor-white">
                    {step.name}
                  </h3>
                  <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                    {step.detail}
                  </p>
                </div>
                <div className="overflow-x-auto rounded-lg border border-circuit-border bg-void-black p-3.5">
                  <pre className="font-code-mono text-[12.5px] whitespace-pre-wrap text-moss-80">
                    <code>{step.code}</code>
                  </pre>
                </div>
              </li>
            ))}
          </ol>
        </section>
        <section aria-labelledby="status-title" className="card-dark">
          <div className="border-b border-phosphor-blue-black pb-4">
            <p className="eyebrow">Four states, nothing hidden</p>
            <h2 id="status-title" className="heading-md mt-2">
              What each status means
            </h2>
          </div>

          <div className="mt-6 grid gap-5 sm:grid-cols-2">
            {STATUS_TAXONOMY.map((item) => (
              <div
                key={item.status}
                className="space-y-2 rounded-lg border border-circuit-border bg-carbon-veil p-5"
              >
                <span
                  className={`chip ${
                    item.status === "GRADED"
                      ? "chip-live"
                      : item.status === "ERROR"
                        ? "chip-alert"
                        : "chip-outline"
                  }`}
                >
                  {item.status}
                </span>
                <p className="text-[14.5px] font-medium text-phosphor-white">{item.summary}</p>
                <p className="text-[13.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  {item.detail}
                </p>
              </div>
            ))}
          </div>
        </section>
        <section aria-labelledby="gaps-title" className="card-dark max-w-[74ch]">
          <h2 id="gaps-title" className="heading-md">
            What is not here yet
          </h2>
          <ul className="mt-5 space-y-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            <li>
              There is no submit button because you submit by pushing. We would rather say so
              than build a button that just tells you to go and push.
            </li>
            <li>
              We grade only written units. Phase 0 and unit 3.2.1 are open today. The rest
              is being written and shows as planned until it is ready.
            </li>
            <li>
              We have not built the recorded walkthrough. No unit needs a video.
            </li>
          </ul>
        </section>

        <section
          aria-labelledby="accounts-title"
          className="card-dark flex flex-col justify-between gap-6 sm:flex-row sm:items-center"
        >
          <div className="max-w-[56ch] space-y-1.5">
            <h2 id="accounts-title" className="heading-md">
              Accounts and payments
            </h2>
            <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              An account is free. You pay per unit when you start one. Enrolling links
              your pushes to your grading record.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-3">
            <Link href="/me" className="btn btn-accent btn-sm">
              Your dashboard
            </Link>
            <Link href="/pricing" className="btn btn-ghost btn-sm">
              What a unit costs
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
