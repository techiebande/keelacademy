import type { JudgeVerdict } from "@/lib/grading";
import { humanizeId } from "@/lib/text";

export function JudgeSection({ judge }: { judge: JudgeVerdict | null | undefined }) {
  const passCount = judge?.criteria.filter((c) => c.verdict === "pass").length ?? 0;
  const totalCount = judge?.criteria.length ?? 0;

  return (
    <section id="rubric-review" aria-labelledby="rubric-title" className="card-dark scroll-mt-24">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 id="rubric-title" className="heading-md">
          Rubric review
        </h2>
        {judge ? (
          <span className="font-code-mono text-[13px] text-moss-70">
            {`${passCount} of ${totalCount} rubric criteria passed`}
          </span>
        ) : null}
      </div>

      <p className="mt-3 max-w-[74ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        We judge each criterion against the published rubric. Each one quotes the lines
        of your code it relied on.
      </p>

      {judge && judge.criteria.length > 0 ? (
        <div className="mt-7">
          {judge.criteria.map((criterion) => {
            const passed = criterion.verdict === "pass";
            return (
              <div
                key={criterion.id}
                className="border-t border-[color:var(--line-on-dark-strong)] py-5 first:border-t-0 first:pt-0"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="text-[15px] text-phosphor-white">
                    {humanizeId(criterion.id)}
                  </span>
                  <span className={passed ? "chip chip-live" : "chip chip-alert"}>
                    {passed ? "PASSED" : "NOT YET"}
                  </span>
                </div>

                {criterion.evidence ? (
                  <div className="mt-4">
                    <p className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                      Quoted from your code
                    </p>
                    <pre className="mt-3 overflow-x-auto rounded-lg border border-circuit-border bg-void-black p-4">
                      <code className="font-code-mono text-[12.5px] leading-relaxed text-moss-80">
                        {criterion.evidence}
                      </code>
                    </pre>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="mt-6 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          This submission has no rubric review.
        </p>
      )}
    </section>
  );
}
