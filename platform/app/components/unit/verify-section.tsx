import type { Check, CurriculumAnchor, Rubric, UnitYaml } from "@/lib/content";
import { humanizeId } from "@/lib/text";

const LAYER_INFO = [
  {
    num: 1,
    name: "Automated checks",
    note: "The automated checks below run your work in isolation. They show Passed or Not yet.",
  },
  {
    num: 2,
    name: "Rubric review",
    note: "A grader reads your submission against the rubric below and quotes your work for every criterion.",
  },
  {
    num: 3,
    name: "Defend your work",
    note: "You answer questions generated from the work you submitted.",
  },
  {
    num: 4,
    name: "Recorded walkthrough",
    note: "You record yourself walking through what you built and why.",
  },
];

function expectLabel(expect: Check["expect"]): { text: string } {
  if (expect === "exit_zero") return { text: "exit 0" };
  if (expect === "exit_nonzero") return { text: "exit non-zero" };
  return { text: `output contains "${(expect as { output_contains: string }).output_contains}"` };
}

/** "a", "a and b", "a, b and c" */
function listOf(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/**
 * The four pieces below are placed by a unit script, with its own words in
 * between, so none of them has to introduce itself.
 */
export function ProveItCard({ curriculum }: { curriculum: CurriculumAnchor | null }) {
  if (!curriculum?.proveIt) return null;
  return (
    <div className="apparatus">
      <div className="apparatus-head">
        <p className="apparatus-label">What this phase must prove</p>
      </div>
      <p className="apparatus-note">{curriculum.proveIt}</p>
    </div>
  );
}

export function GradingModesCard({ unit }: { unit: UnitYaml }) {
  const applies = LAYER_INFO.filter((layer) => unit.verify.layers.includes(layer.num));
  const appliesHere =
    applies.length > 0
      ? `This unit is graded by ${listOf(applies.map((layer) => layer.name.toLowerCase()))}.`
      : "This unit carries no grade. A later review checks your work.";

  return (
    <div className="apparatus">
      <div className="apparatus-head">
        <p className="apparatus-label">How this unit is graded</p>
      </div>
      <div className="space-y-4">
        <p className="apparatus-note">
          {appliesHere} A grader works from every criterion below, exactly as written.
        </p>
        <details className="reveal reveal-flush">
          <summary>How your work gets checked</summary>
          <div className="reveal-body grid gap-4 sm:grid-cols-2">
            {LAYER_INFO.map((layer) => {
              const appliesToUnit = unit.verify.layers.includes(layer.num);
              return (
                <div
                  key={layer.name}
                  className={`space-y-2 rounded-lg border border-circuit-border p-5 ${
                    appliesToUnit
                      ? "border-lime-pulse/40 bg-ground-iron"
                      : "bg-ground-iron/40 opacity-60"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-code-mono text-[11px] text-moss-70">
                      {layer.num} of 4
                    </span>
                    <span
                      className={`chip ${appliesToUnit ? "chip-live" : "chip-outline"} text-[10px]`}
                    >
                      {appliesToUnit ? "THIS UNIT" : "AT GATES"}
                    </span>
                  </div>
                  <p className="font-goga text-[15px] font-medium text-phosphor-white">
                    {layer.name}
                  </p>
                  <p className="text-[12.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                    {layer.note}
                  </p>
                </div>
              );
            })}
          </div>
        </details>
      </div>
    </div>
  );
}

export function AutomatedChecksCard({ checks }: { checks: Check[] | null }) {
  if (!checks || checks.length === 0) return null;
  return (
    <div className="apparatus">
      <div className="apparatus-head">
          <h3 className="apparatus-label">{checks.length} automated checks</h3>
        <span className="chip chip-outline font-code-mono text-[11px]">ISOLATED</span>
      </div>

      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Passes when</th>
              <th scope="col">Command</th>
            </tr>
          </thead>
          <tbody>
            {checks.map((check) => {
              const { text } = expectLabel(check.expect);
              return (
                <tr key={check.id}>
                  <td className="font-medium text-phosphor-white">{humanizeId(check.id)}</td>
                  <td>
                    <span className="chip chip-outline font-code-mono text-[11px]">
                      {text}
                    </span>
                  </td>
                  <td>
                    <code className="code-inline">{check.run}</code>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function RubricCard({ rubric }: { rubric: Rubric | null }) {
  if (!rubric) return null;
  return (
    <div className="apparatus">
      <div className="apparatus-head">
        <h3 className="apparatus-label">
          {rubric.criteria.length} rubric criteria
        </h3>
        <span className="chip chip-outline font-code-mono text-[11px]">
          {rubric.id} v{rubric.version}
        </span>
      </div>

      <div className="space-y-3">
        {rubric.criteria.map((criterion, idx) => (
          <div
            key={criterion.id}
            className="rounded-lg border border-circuit-border bg-carbon-veil p-5"
          >
            <div className="flex flex-wrap items-center gap-2 font-code-mono text-[12px] text-moss-70">
              <span className="font-medium text-lime-pulse">Criterion {idx + 1}</span>
              <span>/</span>
              <h4 className="font-goga text-[15px] font-medium text-phosphor-white">
                {humanizeId(criterion.id)}
              </h4>
            </div>
            <details className="reveal reveal-flush mt-3">
              <summary>What the grader must find</summary>
              <div className="reveal-body space-y-2">
                <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                  {criterion.description}
                </p>
                <p className="pt-1 font-code-mono text-[12.5px] text-moss-70">
                  Must quote:{" "}
                  <span className="text-phosphor-white">{criterion.evidence}</span>
                </p>
              </div>
            </details>
          </div>
        ))}
      </div>

      <SampleVerdictCard />
    </div>
  );
}

/**
 * A static, app-owned example of one Layer-2 verdict (M6.3), shown under the
 * rubric so the student knows the shape of what comes back: one verdict per
 * criterion, each with a verbatim quote from their own work, and an overall
 * line that fails if any criterion fails. The text below is invented; a real
 * verdict quotes the student's own submission.
 */
function SampleVerdictCard() {
  const sampleCriteria: { id: string; verdict: "pass" | "fail"; evidence: string }[] = [
    {
      id: "problem-stated-plainly",
      verdict: "pass",
      evidence: "\"OmniCart receives about 4,000 return requests a month.\"",
    },
    {
      id: "target-process-measurable",
      verdict: "fail",
      evidence: "\"## How it should work\" names no target time.",
    },
  ];
  return (
    <details className="reveal reveal-flush pt-2">
      <summary>See a sample verdict</summary>
      <div className="reveal-body space-y-3 rounded-lg border border-circuit-border bg-carbon-veil p-5">
        <p className="text-[13px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          A made-up example of what the grader returns. Every criterion carries
          a verdict and a quote from your own words. One failed criterion fails
          the whole brief, and you can resubmit.
        </p>
        <div className="space-y-2">
          {sampleCriteria.map((c) => (
            <div
              key={c.id}
              className="flex flex-col gap-1 rounded border border-circuit-border p-3 font-code-mono text-[12px]"
            >
              <div className="flex items-center justify-between gap-3">
                <code className="text-phosphor-white">{c.id}</code>
                <span className={`chip ${c.verdict === "pass" ? "chip-live" : "chip-alert"} text-[10px]`}>
                  {c.verdict.toUpperCase()}
                </span>
              </div>
              <p className="text-moss-70">Evidence: {c.evidence}</p>
            </div>
          ))}
        </div>
        <p className="font-code-mono text-[12px] text-phosphor-white">
          OVERALL: FAIL
        </p>
      </div>
    </details>
  );
}
