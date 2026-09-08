import Link from "next/link";
import { ContentArriving } from "@/components/content-arriving";
import type { SubmissionContract, UnitYaml } from "@/lib/content";

type SubmissionCardProps = {
  unit: UnitYaml;
  contract: SubmissionContract | null;
};

/**
 * Both pieces below are placed by a unit script, with its own words in between,
 * so neither has to open with a sentence introducing itself.
 */
export function DeliverableCallout({ unit }: { unit: UnitYaml }) {
  return (
    <div className="apparatus">
      <div className="apparatus-head">
        <p className="apparatus-label">What you ship</p>
      </div>
      <p className="max-w-[68ch] text-[16px] leading-relaxed text-phosphor-white">
        {unit.build.deliverable}
      </p>
    </div>
  );
}

export function SubmissionContractCard({ unit, contract }: SubmissionCardProps) {
  if (unit.build.submission === "file") {
    return <FileSubmissionCard unit={unit} />;
  }
  if (unit.build.submission === "recording") {
    return (
      <div className="card-dark space-y-4">
        <div className="border-b border-phosphor-blue-black pb-4">
          <h3 className="eyebrow text-[12px]">How to submit it</h3>
        </div>
        <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          This unit asks for a recorded walkthrough. Submission opens with the
          recording flow on this page; nothing to push and nothing to upload yet.
        </p>
      </div>
    );
  }
  return <RepoSubmissionCard unit={unit} contract={contract} />;
}

function FileSubmissionCard({ unit }: { unit: UnitYaml }) {
  return (
    <div className="space-y-8">
      <div className="card-dark space-y-6">
        <div className="border-b border-phosphor-blue-black pb-4">
          <h3 className="eyebrow text-[12px]">How to submit it</h3>
        </div>
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg bg-carbon-veil border border-circuit-border">
            <span className="eyebrow text-[11px]">The file you author</span>
            <code className="font-code-mono text-[13px] text-lime-pulse">brief.md</code>
          </div>
          <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            Write your deliverable as a markdown file on your own machine, following the
            template in the completion problem. When it is ready, paste the complete file
            into the workbench on this page and submit it for grading. No repository, no
            push, no upload form.
          </p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="card-dark space-y-3">
          <span className="eyebrow text-[11px]">Who grades it</span>
          <p className="text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            The evaluation judge reads your brief against unit {unit.id}&apos;s rubric and
            quotes verbatim evidence for every criterion. The verdict comes back on this
            page, criterion by criterion.
          </p>
        </div>
        <div className="card-dark space-y-3">
          <span className="eyebrow text-[11px]">What a pass does</span>
          <p className="text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            A passing verdict completes the unit and unlocks what follows it. A fail names
            the criteria that missed, and you can revise and resubmit.
          </p>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-6 rounded-lg bg-carbon-veil border border-circuit-border">
        <span className="text-[15px] text-phosphor-white">
          Your brief is graded in the completion workbench on this page.
        </span>
        <Link href="#completion-problem" className="btn btn-accent btn-sm">
          Go to the workbench
        </Link>
      </div>
    </div>
  );
}

function RepoSubmissionCard({ unit, contract }: SubmissionCardProps) {
  return (
    <div className="space-y-8">
        {/* Submission contract */}
        <div className="card-dark space-y-6">
          <div className="border-b border-phosphor-blue-black pb-4">
            <h3 className="eyebrow text-[12px]">
              How to submit it
            </h3>
          </div>

          {contract ? (
            <div className="space-y-6">
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="w-1/3">File</th>
                      <th>What it has to do</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contract.files.map((file) => (
                      <tr key={file.path}>
                        <td>
                          <code className="code-inline">{file.path}</code>
                        </td>
                        <td className="text-[14.5px] text-[color:var(--text-muted-on-dark)]">{file.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {contract.cli ? (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-lg bg-carbon-veil border border-circuit-border">
                  <span className="eyebrow text-[11px]">
                    The command the automated checks run
                  </span>
                  <code className="font-code-mono text-[13px] text-lime-pulse">
                    {contract.cli}
                  </code>
                </div>
              ) : null}
            </div>
          ) : (
            <ContentArriving what="The submission contract for this unit" />
          )}
        </div>

        {/* Repo naming + data variant */}
        <div className="grid gap-6 md:grid-cols-2">
          <div className="card-dark space-y-3">
            <span className="eyebrow text-[11px]">
              What to name your repository
            </span>
            <div className="block">
              <code className="code-inline text-[15px] font-code-mono text-phosphor-white">
                keel-{unit.id}-solution
              </code>
            </div>
            <p className="text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              Push it to GitHub under that exact name. GitHub matches that name to
              unit {unit.id}; a typo skips the automated checks entirely.
            </p>
          </div>

          <div className="card-dark space-y-3">
            <span className="eyebrow text-[11px]">
              The data you build against
            </span>
            <div className="block">
              <code className="code-inline text-[15px] font-code-mono text-lime-pulse">
                {unit.build.data_variant}
              </code>
            </div>
            <p className="text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              The automated checks run against this fixture corpus. It ships with the unit, so
              run them locally first; you will get the same result the grader gets.
            </p>
          </div>
        </div>

        {/* Submit guide link */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-6 rounded-lg bg-carbon-veil border border-circuit-border">
          <span className="text-[15px] text-phosphor-white">Push your work for grading.</span>
          <Link href="/submit" className="btn btn-accent btn-sm">
            Read how submitting works
          </Link>
        </div>
    </div>
  );
}
