"use client";

import { useState } from "react";
import Link from "next/link";
import type { PlacementDiagnostic } from "@/lib/content";
import type {
  DiagnosticAttempt,
  DiagnosticEvaluateResult,
} from "@/lib/practice";

type Props = {
  diagnostic: PlacementDiagnostic;
  studentId: number;
  initialAttempts: DiagnosticAttempt[];
};

export function DiagnosticWorkbench({
  diagnostic,
  studentId,
  initialAttempts,
}: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [inFlight, setInFlight] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [latestResult, setLatestResult] = useState<DiagnosticEvaluateResult | null>(null);

  const answeredCount = Object.keys(answers).length;
  const totalQuestions = diagnostic.questions.length;
  const isComplete = answeredCount === totalQuestions;

  const handleSelectOption = (questionId: string, optionId: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: optionId }));
  };

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isComplete || inFlight) return;
    setInFlight(true);
    setErrorMsg(null);

    try {
      const res = await fetch("/api/diagnostic/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: studentId,
          diagnostic_id: diagnostic.id,
          answers,
        }),
      });

      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { error?: string };
        setErrorMsg(err.error || `Evaluation failed with status ${res.status}`);
        setInFlight(false);
        return;
      }

      const data = (await res.json()) as DiagnosticEvaluateResult;
      setLatestResult(data);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error");
    } finally {
      setInFlight(false);
    }
  };

  const handleOptOut = async () => {
    if (inFlight) return;
    setInFlight(true);
    setErrorMsg(null);

    try {
      const res = await fetch("/api/diagnostic/opt-out", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: studentId,
          diagnostic_id: diagnostic.id,
        }),
      });

      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { error?: string };
        setErrorMsg(err.error || `Opt-out failed with status ${res.status}`);
        setInFlight(false);
        return;
      }

      const data = (await res.json()) as DiagnosticEvaluateResult;
      setLatestResult(data);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Network error");
    } finally {
      setInFlight(false);
    }
  };

  return (
    <div className="space-y-8">
      {latestResult ? (
        <section aria-labelledby="result-title" className="card-dark max-w-[74ch]">
          <div className="flex flex-wrap items-baseline justify-between gap-4">
            <h2 id="result-title" className="heading-md">
              {latestResult.passed ? "You can skip ahead" : "You start at the beginning"}
            </h2>
            <span className={latestResult.passed ? "chip chip-live" : "chip chip-outline"}>
              {`${latestResult.score_pct}%`}
            </span>
          </div>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            {`You scored ${latestResult.points_earned} of ${latestResult.points_possible} points.`}
          </p>
          {latestResult.unlocked_units.length > 0 ? (
            <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              {`Open now: ${latestResult.unlocked_units.join(", ")}.`}
            </p>
          ) : null}
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            {latestResult.passed
              ? "You can still work through anything that opened early. Skipping stays optional, and strong foundations have saved many engineers."
              : "You keep your place. This is the ordinary route through the curriculum, and most students start here."}
          </p>
          <Link href="/map" className="btn btn-primary btn-sm mt-7">
            See your map
          </Link>
        </section>
      ) : (
        <form onSubmit={handleEvaluate}>
          <ol className="space-y-6">
            {diagnostic.questions.map((q, idx) => (
              <li key={q.id} className="card-dark">
                <fieldset>
                  <legend className="max-w-[74ch]">
                    <span className="font-code-mono text-[12px] text-lime-pulse">
                      {`Question ${idx + 1} of ${totalQuestions}`}
                    </span>
                    <span className="mt-3 block font-goga text-[17px] leading-snug font-medium text-phosphor-white">
                      {q.prompt}
                    </span>
                  </legend>
                  <div className="mt-6 space-y-3">
                    {q.options.map((opt) => (
                      <label
                        key={opt.id}
                        className="flex cursor-pointer items-start gap-3 rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[15px] leading-relaxed text-[color:var(--text-muted-on-dark)] hover:text-phosphor-white has-checked:border-lime-pulse has-checked:text-phosphor-white"
                      >
                        <input
                          type="radio"
                          name={q.id}
                          value={opt.id}
                          checked={answers[q.id] === opt.id}
                          onChange={() => handleSelectOption(q.id, opt.id)}
                          disabled={inFlight}
                          className="mt-1 accent-lime-pulse"
                        />
                        <span>{opt.label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              </li>
            ))}
          </ol>

          <div className="card-dark mt-8">
            <p className="font-code-mono text-[13px] text-moss-70" aria-live="polite">
              {`${answeredCount} of ${totalQuestions} answered`}
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={!isComplete || inFlight}
                className="btn btn-accent btn-sm"
              >
                {inFlight ? "Checking" : "Check my answers"}
              </button>
              <button
                type="button"
                onClick={handleOptOut}
                disabled={inFlight}
                className="btn btn-ghost btn-sm"
              >
                Skip this and start at the beginning
              </button>
            </div>
          </div>
        </form>
      )}

      {errorMsg ? (
        <p
          role="alert"
          className="rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
        >
          {errorMsg}
        </p>
      ) : null}

      {initialAttempts.length > 0 && !latestResult ? (
        <section aria-labelledby="attempts-title" className="card-dark">
          <h2 id="attempts-title" className="heading-md">
            {initialAttempts.length === 1
              ? "You took this once before"
              : `You took this ${initialAttempts.length} times before`}
          </h2>
          <ul className="mt-6">
            {initialAttempts.map((att) => (
              <li
                key={att.id}
                className="flex flex-wrap items-baseline justify-between gap-3 border-t border-[color:var(--line-on-dark-strong)] py-3 first:border-t-0 first:pt-0"
              >
                <span className="text-[15px] text-phosphor-white">
                  {`${att.score_pct}% (${att.points_earned} of ${att.points_possible} points)`}
                </span>
                <span className="font-code-mono text-[12.5px] text-[color:var(--text-faint-on-dark)]">
                  {att.created_at}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
