import type { Metadata } from "next";
import Link from "next/link";
import { listUnits, loadCurriculumMap, loadPlacementDiagnostic } from "@/lib/content";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "FAQ",
  description: "How Keel Academy works. How grading works. What exists today.",
};

export default function FaqPage() {
  const units = listUnits();
  const liveList = units.map((u) => u.id).join(", ");

  // Every number below is read from content/ so the answers cannot drift from
  // the curriculum they describe.
  const map = loadCurriculumMap();
  const phaseCount = map.phases.length;
  const totalHours = map.phases.reduce((sum, p) => sum + p.est_hours, 0);
  const monthsAtFifteen = Math.round(totalHours / 15 / 4.33);
  const monthsAtTwelve = Math.round(totalHours / 12 / 4.33);
  const placement = loadPlacementDiagnostic("placement-phase-1");
  const placementLine = placement
    ? `Pass the ${placement.est_minutes}-minute placement check and we open ${placement.pass_skip_units.length} Phase 1 units for you.`
    : "";

  const FAQS = [
    {
      question: "What is Keel Academy?",
      answer: `Keel Academy is where tutorials end and the real work starts. You learn applied AI engineering through projects: one production system built end to end, a return reconciliation and dispute triage pipeline for OmniCart Operations, a simulated multi-brand e-commerce retailer. The curriculum has ${phaseCount} phases and ${totalHours} hours of build work, and every hour of it is building.`,
    },
    {
      question: "How does grading actually work?",
      answer:
        "Here is the part we are proudest of. You submit by pushing a git repository. Your code runs first against the unit automated checks in an isolated run, so the result never depends on your machine. Then a language model grades it against the unit's published rubric, and it has to quote the lines of your own code that earned each verdict. You read the rubric before you start, and you see the same verdict text the grader wrote. No black boxes.",
    },
    {
      question: "Can I get through this with another AI tool?",
      answer:
        "You can write code with one. Every working engineer does. You cannot hand in output you do not understand. Rubric review quotes your own code back at you. Automated checks run your code. The two capstone defences are live conversations with a technical reviewer and a budget holder. Pasted answers do not pass, and honestly, that is the feature.",
    },
    {
      question: "How long does it take?",
      answer: `At 12 to 15 hours a week, ${totalHours} hours works out to roughly ${monthsAtFifteen} to ${monthsAtTwelve} months. ${placementLine}`.trim(),
    },
    {
      question: "What exists right now?",
      answer:
        `The platform runs today. It handles accounts and per-unit enrollment. It runs the full grading loop. It runs practice drills, the assistant, pods and the gallery. We publish units as we finish them${liveList ? `: open today: unit ${liveList}` : ""}. No unit asks for a video today. We have not built recorded walkthroughs yet. Every unit page states what automated checks and rubric review grade and what opens next.`,
    },
    {
      question: "What does it cost?",
      answer:
        "You enroll one unit at a time and the price is on the unit before you pay. There is no subscription. There are two milestone gates, one at the Phase 5 integration project and one at the capstone. You commit to a window for a gate up front, and clearing it inside that window returns 15% of what you paid for the unit as a refund to the card you paid with. Clearing the gate records the rebate straight away. A person issues the refund. No script issues it automatically.",
    },
    {
      question: "Who is this for?",
      answer:
        "It fits engineers who want AI systems work: the unglamorous, employable kind. That work covers model integration and structured outputs. It covers retrieval and agents. It covers evaluation, governance and deployment, plus the client conversations that come with shipping for a business. You write code each week, and you are comfortable with Python and APIs. Complete beginners start with a general programming foundation; we will still be here when you are ready.",
    },
    {
      question: "What do I leave with?",
      answer:
        "You leave with a deployed system. It passed a published bar. You keep the verdicts and two defences. You keep a proposal you can send to a real client. Automated checks and rubric review checked every piece against a rubric you read before you started. That is not a certificate. It is better: it is checkable.",
    },
  ];

  return (
    <div>
      <header className="shell pb-12 pt-14">
        <p className="eyebrow">FAQ</p>
        <h1 className="heading-xl mt-4">Straight answers</h1>
        <p className="lead mt-5">
          If your question is missing, that is a bug. Tell us and it will
          land here. Everything below describes how the program behaves today.
        </p>
      </header>

      <div className="shell pb-24">
        <div className="space-y-4">
          {FAQS.map((faq) => (
            <details key={faq.question} className="faq-item card-dark group" id={faq.question
              .toLowerCase()
              .replace(/[^a-z0-9]+/g, "-")
              .replace(/(^-|-$)/g, "")}>
              <summary className="flex items-center justify-between gap-6 p-6">
                <h2 className="font-goga text-[17.5px] font-medium text-phosphor-white">
                  {faq.question}
                </h2>
                <svg
                  aria-hidden
                  className="faq-chevron text-[color:var(--text-faint-on-dark)]"
                  width="14"
                  height="14"
                  viewBox="0 0 14 14"
                  fill="none"
                >
                  <path
                    d="M5 3l4.5 4L5 11"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </summary>
              <div className="px-6 pb-6">
                <p className="max-w-[70ch] text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  {faq.answer}
                </p>
              </div>
            </details>
          ))}
        </div>

        <div className="mt-12 flex flex-wrap gap-4">
          <Link href="/curriculum" className="btn btn-ghost btn-sm">
            See the curriculum
          </Link>
          <Link href="/pricing" className="btn btn-ghost btn-sm">
            See pricing
          </Link>
          <Link href="/sign-up" className="btn btn-primary btn-sm">
            Start building
          </Link>
        </div>
      </div>
    </div>
  );
}
