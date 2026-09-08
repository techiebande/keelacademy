import Link from "next/link";
import { formatUtc, type SubmissionView } from "@/lib/grading";

export function SubmissionFacts({
  view,
  studentEmail,
}: {
  view: SubmissionView;
  studentEmail?: string | null;
}) {
  const s = view.submission;
  return (
    <dl className="mt-px grid gap-px overflow-hidden rounded-lg border border-circuit-border bg-circuit-border sm:grid-cols-2 lg:grid-cols-4">
      <Fact label="Account">
        <dd className="mt-2 text-[15px] text-phosphor-white">
          {studentEmail ?? s.student_name ?? `Student #${s.student_id}`}
        </dd>
      </Fact>
      <Fact label="Unit">
        <dd className="mt-2 text-[15px]">
          <Link
            href={`/units/${s.unit_id}`}
            className="text-fern-link underline underline-offset-4 hover:text-phosphor-white"
          >
            Unit {s.unit_id}
          </Link>
        </dd>
      </Fact>
      <Fact label="Commit">
        <dd className="mt-2 text-[15px]">
          <code className="font-code-mono text-[14px] text-phosphor-white">
            {s.commit_sha.slice(0, 10)}
          </code>
        </dd>
      </Fact>
      <Fact label="Pushed (UTC)">
        <dd className="mt-2 font-code-mono text-[14px] text-phosphor-white">
          {formatUtc(s.created_at)}
        </dd>
      </Fact>
    </dl>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-ground-iron p-5">
      <dt className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
        {label}
      </dt>
      {children}
    </div>
  );
}
