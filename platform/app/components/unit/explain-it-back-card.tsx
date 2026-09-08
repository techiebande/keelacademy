"use client";

import { useState, useTransition } from "react";
import { runExplainItBackAction } from "@/app/units/[unitId]/practice-actions";
import type { ExplainItBackResult } from "@/lib/practice";

/**
 * Explain-it-back generative step (lesson UX spec U7).
 *
 * Appears after a passed completion problem. The student writes a 2-3 sentence
 * explanation judged against a pedagogical rubric (evaluation only, does not
 * block the gate).
 */
export function ExplainItBackCard({
  unitId,
  isSignedIn,
  isEnrolled,
}: {
  unitId: string;
  isSignedIn: boolean;
  isEnrolled: boolean;
}) {
  const [explanation, setExplanation] = useState("");
  const [result, setResult] = useState<ExplainItBackResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!explanation.trim()) return;

    setErrorMsg(null);
    startTransition(async () => {
      const res = await runExplainItBackAction(unitId, explanation.trim());
      if (res.state === "ok") {
        setResult(res.data);
      } else if (res.state === "unreachable") {
        setErrorMsg("The checks did not run. Try again.");
      } else {
        setErrorMsg(res.message || "Your explanation did not submit. Try again.");
      }
    });
  };

  return (
    <div className="card-dark space-y-5 border-t border-circuit-border pt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="chip chip-outline font-code-mono text-[11px]">
            EXPLAIN IT BACK
          </span>
          <h4 className="font-goga text-[16px] font-medium text-phosphor-white">
            State the boundary rule
          </h4>
        </div>
        {result ? (
          <span
            className={`chip font-code-mono text-[11px] ${
              result.passed ? "chip-live" : "chip-alert"
            }`}
          >
            {result.passed ? "PASSED" : "NOT YET"}
          </span>
        ) : null}
      </div>

      <p className="max-w-[70ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
        The tests pass. Now say it back: in 2 to 3 sentences, state the boundary rule your
        code enforces, and why downstream systems need it.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="explain-input" className="sr-only">
            Your explanation
          </label>
          <textarea
            id="explain-input"
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
            disabled={isPending}
            rows={3}
            placeholder="The extractor validates each record against a schema before it saves. Downstream jobs need that check, or one bad record poisons the queue."
            className="field-input w-full"
          />
        </div>

        {errorMsg ? (
          <p className="text-[13.5px] text-amber-300">{errorMsg}</p>
        ) : null}

        {result ? (
          <div className="rounded-lg border border-circuit-border bg-carbon-veil p-4">
            <p className="text-[14px] leading-relaxed text-phosphor-white">
              {result.feedback}
            </p>
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={isPending || !explanation.trim() || !isSignedIn || !isEnrolled}
            className="btn btn-primary btn-sm"
          >
            {isPending ? "Checking" : result ? "Submit revised explanation" : "Submit explanation"}
          </button>
          {!isSignedIn ? (
            <span className="text-[13px] text-moss-70">
              Sign in to submit your explanation.
            </span>
          ) : !isEnrolled ? (
            <span className="text-[13px] text-moss-70">
              Enroll to get feedback on your explanation.
            </span>
          ) : null}
        </div>
      </form>
    </div>
  );
}
