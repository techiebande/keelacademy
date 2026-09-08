import type { Layer1Check, Layer1Result } from "@/lib/grading";
import { humanizeId } from "@/lib/text";

function CheckRow({ check }: { check: Layer1Check }) {
  const passed = check.status === "pass";
  return (
    <div className="border-t border-[color:var(--line-on-dark-strong)] py-5 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-[15px] text-phosphor-white">{humanizeId(check.id)}</span>

        <div className="flex items-center gap-3">
          {typeof check.wall_s === "number" ? (
            <span className="font-code-mono text-[13px] text-[color:var(--text-faint-on-dark)]">
              {check.wall_s.toFixed(2)}s
            </span>
          ) : null}
          <span className={passed ? "chip chip-live" : "chip chip-alert"}>
            {passed ? "PASSED" : "NOT YET"}
          </span>
        </div>
      </div>

      {check.note ? (
        <p className="mt-3 max-w-[76ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {check.note}
        </p>
      ) : null}

      {check.output_tail ? (
        <details className="mt-4">
          <summary className="cursor-pointer text-[14px] text-fern-link underline underline-offset-4 hover:text-phosphor-white">
            Show what the automated check printed
          </summary>
          <pre className="mt-3 overflow-x-auto rounded-lg border border-circuit-border bg-void-black p-4">
            <code className="font-code-mono text-[12.5px] leading-relaxed text-moss-80">
              {check.output_tail}
            </code>
          </pre>
        </details>
      ) : null}
    </div>
  );
}

export function Layer1Section({ layer1 }: { layer1: Layer1Result | null | undefined }) {
  const passCount = layer1?.checks.filter((c) => c.status === "pass").length ?? 0;
  const totalCount = layer1?.checks.length ?? 0;

  return (
    <section id="automated-checks" aria-labelledby="checks-title" className="card-dark scroll-mt-24">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h2 id="checks-title" className="heading-md">
          Automated checks
        </h2>
        {layer1 ? (
          <span className="font-code-mono text-[13px] text-moss-70">
            {`${passCount} of ${totalCount} automated checks passed`}
          </span>
        ) : null}
      </div>

      <p className="mt-3 max-w-[74ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        These run your code in an isolated run. They are the same automated checks
        you can run before pushing.
      </p>

      {layer1 && layer1.checks.length > 0 ? (
        <div className="mt-7">
          {layer1.checks.map((check) => (
            <CheckRow key={check.id} check={check} />
          ))}
        </div>
      ) : (
        <p className="mt-6 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          This submission has no check results.
        </p>
      )}
    </section>
  );
}
