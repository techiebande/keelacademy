"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { runPracticeAttemptAction } from "@/app/units/[unitId]/practice-actions";
import type {
  PracticeAttemptResult,
  PracticeAttemptSummary,
  PracticeCheckResult,
  PracticeManifest,
} from "@/lib/practice";
import { formatUtc } from "@/lib/grading";
import { countWords, findBannedWords } from "@/lib/text";

type PracticeWorkbenchProps = {
  unitId: string;
  manifest: PracticeManifest | null;
  initialAttempts: PracticeAttemptSummary[];
  isEnrolled: boolean;
  isSignedIn: boolean;
  serviceDown: boolean;
};

export function PracticeWorkbench({
  unitId,
  manifest,
  initialAttempts,
  isEnrolled,
  isSignedIn,
  serviceDown,
}: PracticeWorkbenchProps) {
  const editableFiles = manifest?.editable_files ?? [];
  const baseFiles = manifest?.base_files ?? {};
  const isConceptual = manifest?.kind === "conceptual";

  // Form state for each editable file
  const [fileContents, setFileContents] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const fname of editableFiles) {
      initial[fname] = baseFiles[fname] ?? "";
    }
    return initial;
  });

  // Conceptual units submit one prose answer, not a file map.
  const [answer, setAnswer] = useState("");

  const [activeFile, setActiveFile] = useState<string>(editableFiles[0] ?? "");
  const [isPending, startTransition] = useTransition();
  const [latestResult, setLatestResult] = useState<PracticeAttemptResult | null>(
    null,
  );
  const [attempts, setAttempts] = useState<PracticeAttemptSummary[]>(initialAttempts);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);

  // Live feedback for the conceptual brief editor (M6.1): word count plus the
  // standing banned-word warning, so problems surface before submission.
  const answerWords = isConceptual ? countWords(answer) : 0;
  const bannedHits = isConceptual ? findBannedWords(answer) : [];

  function handleFileChange(filename: string, content: string) {
    setFileContents((prev) => ({ ...prev, [filename]: content }));
  }

  function handleResetFile(filename: string) {
    if (baseFiles[filename] !== undefined) {
      setFileContents((prev) => ({ ...prev, [filename]: baseFiles[filename] }));
    }
  }

  function handleResetAll() {
    const reset: Record<string, string> = {};
    for (const fname of editableFiles) {
      reset[fname] = baseFiles[fname] ?? "";
    }
    setFileContents(reset);
    setAnswer("");
  }

  function handleSubmit() {
    setErrorBanner(null);
    startTransition(async () => {
      const res = isConceptual
        ? await runPracticeAttemptAction(unitId, {}, answer)
        : await runPracticeAttemptAction(unitId, fileContents);
      if (res.state === "ok") {
        setLatestResult(res.data);
        const newSummary: PracticeAttemptSummary = {
          id: res.data.attempt_id,
          student_id: res.data.student_id,
          unit_id: res.data.unit_id,
          passed: res.data.passed,
          pass_count: res.data.pass_count,
          total_checks: res.data.total_checks,
          checks: res.data.checks,
          created_at: res.data.created_at,
        };
        setAttempts((prev) => [newSummary, ...prev]);
      } else if (res.state === "unreachable") {
        setErrorBanner(
          "The checks did not run. Your work in the editor remains. Try again.",
        );
      } else if (res.state === "rejected") {
        setErrorBanner(
          res.message ||
            (res.code === "not_enrolled"
              ? "Running the checks needs an active enrollment in this unit."
              : "The checks did not run. You kept your budget. Try again."),
        );
      }
    });
  }

  if (serviceDown || !manifest) {
    return (
      <div className="rounded-lg border border-circuit-border bg-carbon-veil p-5">
        <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          The practice editor is down. The lesson and worked example above remain. Reload.
        </p>
      </div>
    );
  }

  return (
    <div data-keel-practice-workbench className="space-y-6">
      {/* Workbench panel */}
      <div className="card-dark p-0 overflow-hidden border border-circuit-border">
        {/* Header bar */}
        <div className="flex items-center justify-between gap-4 p-3.5 bg-carbon-veil border-b border-phosphor-blue-black">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-lime-pulse" />
            <span className="font-code-mono text-[12px] font-medium text-phosphor-white">
              practice
            </span>
          </div>

          <div>
            <button
              type="button"
              onClick={handleResetAll}
              disabled={isPending}
              className="text-[12px] font-code-mono text-moss-70 hover:text-phosphor-white transition-colors"
            >
              Reset all files
            </button>
          </div>
        </div>

        {/* File tabs (code units only) */}
        {!isConceptual && (
          <div className="flex items-center gap-1 p-2 bg-ground-iron border-b border-phosphor-blue-black overflow-x-auto">
            {editableFiles.map((fname) => (
              <button
                key={fname}
                type="button"
                onClick={() => setActiveFile(fname)}
                className={`px-3.5 py-1.5 rounded text-[13px] font-code-mono transition-colors ${
                  activeFile === fname
                    ? "bg-carbon-veil text-lime-pulse font-medium"
                    : "text-moss-70 hover:text-phosphor-white"
                }`}
              >
                {fname}
              </button>
            ))}
          </div>
        )}

        {/* Editor area */}
        <div className="p-4 bg-void-black/80 space-y-2">
          <div className="flex items-center justify-between text-[11px] font-code-mono text-moss-70">
            <span>
              {isConceptual ? (
                <>Editing: <span className="text-phosphor-white">brief.md</span></>
              ) : (
                <>
                  Editing: <span className="text-phosphor-white">{activeFile}</span>
                </>
              )}
            </span>
            {!isConceptual && (
              <button
                type="button"
                onClick={() => handleResetFile(activeFile)}
                disabled={isPending}
                className="hover:text-phosphor-white transition-colors"
              >
                Reset this file
              </button>
            )}
          </div>

          {isConceptual ? (
            <>
              <textarea
                aria-label="Answer editor for brief.md"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                disabled={isPending || !isEnrolled}
                rows={18}
                className="w-full font-code-mono text-[13.5px] leading-relaxed p-4 bg-void-black text-moss-80 border border-circuit-border rounded-lg focus:border-lime-pulse focus:outline-none resize-y"
                placeholder={"Paste your complete brief.md here, including the four mandated section headings, before submitting it for grading."}
              />
              <div className="flex flex-wrap items-baseline justify-between gap-3 font-code-mono text-[11.5px]">
                <span className="text-moss-70" aria-live="polite">
                  {answerWords === 1 ? "1 word" : `${answerWords} words`}
                </span>
                {bannedHits.length > 0 ? (
                  <span role="alert" className="text-amber-300">
                    {`Banned words in your brief: ${bannedHits.join(", ")}. Say what should happen, not what tool does it.`}
                  </span>
                ) : null}
              </div>
            </>
          ) : (
            <textarea
              aria-label={`Code editor for ${activeFile}`}
              value={fileContents[activeFile] ?? ""}
              onChange={(e) => handleFileChange(activeFile, e.target.value)}
              disabled={isPending || !isEnrolled}
              rows={16}
              spellCheck={false}
              className="w-full font-code-mono text-[13.5px] leading-relaxed p-4 bg-void-black text-moss-80 border border-circuit-border rounded-lg focus:border-lime-pulse focus:outline-none resize-y"
            />
          )}
        </div>

        {/* Submit action strip */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-carbon-veil border-t border-phosphor-blue-black">
          <div className="text-[13px] text-[color:var(--text-muted-on-dark)]">
            {!isSignedIn ? (
              <p>
                <Link
                  href={`/sign-in?next=/units/${unitId}#practice`}
                  className="text-fern-link underline hover:text-phosphor-white"
                >
                  Sign in
                </Link>{" "}
                and enroll to submit your work here.
              </p>
            ) : !isEnrolled ? (
              <p>
                Submitting for grading needs an active enrollment in this unit.{" "}
                <Link
                  href={`/map`}
                  className="text-fern-link underline hover:text-phosphor-white"
                >
                  Enroll from your progress map
                </Link>
                .
              </p>
            ) : isConceptual ? (
              <p>
                The evaluation judge reads your brief against the unit rubric and
                quotes verbatim evidence for every criterion.
              </p>
            ) : (
              <p>
                These automated checks grade a submission. They run in isolation. They cost
                nothing.
              </p>
            )}
          </div>

          <div>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isPending || !isEnrolled}
              className="btn btn-accent btn-sm"
            >
              {isPending ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-void-black animate-pulse" />
                  {isConceptual ? "Grading your brief" : "Running the checks"}
                </>
              ) : isConceptual ? (
                "Submit the brief for grading"
              ) : (
                "Run the checks"
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Error banner */}
      {errorBanner ? (
        <p
          role="alert"
          className="rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14px] leading-relaxed text-phosphor-white"
        >
          {errorBanner}
        </p>
      ) : null}

      {/* Latest attempt results */}
      {latestResult ? (
        <div className="card-dark space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-phosphor-blue-black pb-4">
            <div className="flex items-center gap-3">
              <span
                className={`chip ${
                  latestResult.passed ? "chip-live" : "chip-alert"
                }`}
              >
                {latestResult.passed ? "PASSED" : "NOT YET"}
              </span>
              <span className="font-code-mono text-[13px] text-phosphor-white">
                {`${latestResult.pass_count} / ${latestResult.total_checks} checks passing`}
              </span>
            </div>
            <span className="font-code-mono text-[12px] text-moss-70">
              {`Attempt #${latestResult.attempt_id}`}
            </span>
          </div>

          <div className="space-y-3">
            {latestResult.checks.map((check) => (
              <CheckCard key={check.id} check={check} />
            ))}
          </div>
        </div>
      ) : null}

      {/* Attempt history */}
      {attempts.length > 0 ? (
        <div className="card-dark space-y-4">
          <h4 className="eyebrow text-[12px]">
            {`Practice attempt history (${attempts.length})`}
          </h4>

          <div className="space-y-2.5">
            {attempts.map((att) => (
              <div
                key={att.id}
                className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg bg-carbon-veil border border-circuit-border font-code-mono text-[12.5px]"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`chip ${att.passed ? "chip-live" : "chip-outline"} text-[10px]`}
                  >
                    {att.passed ? "PASSED" : "NOT YET"}
                  </span>
                  <span className="text-phosphor-white">
                    {`${att.pass_count} / ${att.total_checks} passing`}
                  </span>
                  <span className="text-moss-70">
                    {`attempt #${att.id}`}
                  </span>
                </div>
                <span className="text-moss-70 text-[11px]">
                  {formatUtc(att.created_at)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CheckCard({ check }: { check: PracticeCheckResult }) {
  const isPass = check.status === "pass";
  return (
    <div
      className={`p-4 rounded-lg border bg-carbon-veil space-y-2 ${
        isPass ? "border-lime-pulse/40" : "border-circuit-border"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 font-code-mono text-[12px]">
        <div className="flex items-center gap-2">
          <code className="text-phosphor-white font-medium">{check.id}</code>
          <span className="chip chip-outline text-[10px]">{check.type}</span>
        </div>

        <div className="flex items-center gap-3">
          {check.wall_s !== null ? (
            <span className="text-moss-70">
              {check.wall_s.toFixed(2)}s
            </span>
          ) : null}
          <span
            className={`chip ${isPass ? "chip-live" : "chip-alert"} text-[10px]`}
          >
            {check.status.toUpperCase()}
          </span>
        </div>
      </div>

      <p className="text-[13.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">{check.note}</p>

      {check.output_tail ? (
        <details className="pt-2 text-[12px] font-code-mono">
          <summary className="cursor-pointer text-moss-70 hover:text-phosphor-white transition-colors">
            See the output
          </summary>
          <pre className="mt-2 p-3 rounded bg-void-black text-moss-80 border border-circuit-border overflow-x-auto text-[11.5px] whitespace-pre-wrap">
            {check.output_tail}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
