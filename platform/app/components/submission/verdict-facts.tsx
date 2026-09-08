import Link from "next/link";
import { budgetCharged, formatUtc, type SubmissionView } from "@/lib/grading";

export function VerdictFacts({ view }: { view: SubmissionView }) {
  const verdict = view.verdict;
  if (!verdict) return null;
  const charged = budgetCharged(view);

  return (
    <section
      id="verdict-record"
      aria-labelledby="record-title"
      className="card-dark scroll-mt-24"
    >
      <h2 id="record-title" className="heading-md">
        What this verdict was graded against
      </h2>
      <p className="mt-3 max-w-[74ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        We version the rubric, so each verdict links back to the exact wording we
        graded against.
      </p>

      <dl className="mt-7 grid gap-px overflow-hidden rounded-lg border border-circuit-border bg-circuit-border sm:grid-cols-2 lg:grid-cols-4">
        <Record label="Rubric">
          <dd className="mt-2 text-[15px]">
            <Link
              href={`/units/${view.submission.unit_id}#verify`}
              className="font-code-mono text-[14px] text-fern-link underline underline-offset-4 hover:text-phosphor-white"
            >
              {verdict.rubric_id ?? "unknown"}
              {verdict.rubric_version != null ? ` v${verdict.rubric_version}` : ""}
            </Link>
          </dd>
        </Record>
        <Record label="Issued (UTC)">
          <dd className="mt-2 font-code-mono text-[14px] text-phosphor-white">
            {formatUtc(verdict.issued_at)}
          </dd>
        </Record>
        <Record label="Budget used">
          <dd className="mt-2 font-code-mono text-[14px] text-phosphor-white">
            {charged
              ? `${charged.tokens.toLocaleString("en-US")} tokens${
                  charged.costUsd != null ? ` ($${charged.costUsd.toFixed(4)})` : ""
                }`
              : "0 tokens"}
          </dd>
        </Record>
        <Record label="Grading ID">
          <dd className="mt-2">
            <code className="font-code-mono text-[13px] break-all text-phosphor-white">
              {verdict.json?.trace?.call_id ?? "No run ID recorded"}
            </code>
          </dd>
        </Record>
      </dl>
    </section>
  );
}

function Record({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-ground-iron p-5">
      <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
        {label}
      </dt>
      {children}
    </div>
  );
}
