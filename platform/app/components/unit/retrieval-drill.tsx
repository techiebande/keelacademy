"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { runRetrievalAttemptAction } from "@/app/units/[unitId]/practice-actions";
import type {
  RetrievalAttemptResult,
  RetrievalAttemptSummary,
  ReviewQueueItem,
} from "@/lib/practice";
import { formatUtc } from "@/lib/grading";

type RetrievalDrillProps = {
  unitId: string;
  seeds: string[];
  initialAttempts: RetrievalAttemptSummary[];
  dueSeedIndices?: number[];
  isEnrolled: boolean;
  isSignedIn: boolean;
  serviceDown: boolean;
  reviewItems?: ReviewQueueItem[];
};

type DrillQuestion = {
  unitId: string;
  seedIndex: number;
  prompt: string;
  isReview: boolean;
};

export function RetrievalDrill({
  unitId,
  seeds,
  initialAttempts,
  dueSeedIndices = [],
  isEnrolled,
  isSignedIn,
  serviceDown,
  reviewItems = [],
}: RetrievalDrillProps) {
  const questions: DrillQuestion[] = [
    ...seeds.map((prompt, seedIndex) => ({
      unitId,
      seedIndex,
      prompt,
      isReview: false,
    })),
    ...reviewItems.map((r) => ({
      unitId: r.unit_id,
      seedIndex: r.seed_index,
      prompt: r.seed_prompt,
      isReview: true,
    })),
  ];

  const [currentIndex, setCurrentIndex] = useState<number>(() =>
    dueSeedIndices.length > 0 ? Math.min(...dueSeedIndices) : 0,
  );
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isPending, startTransition] = useTransition();
  const [latestResult, setLatestResult] = useState<RetrievalAttemptResult | null>(
    null,
  );
  const [attempts, setAttempts] = useState<RetrievalAttemptSummary[]>(
    initialAttempts,
  );
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [dueSet, setDueSet] = useState<Set<number>>(() => new Set(dueSeedIndices));

  const currentQuestion = questions[currentIndex] ?? null;
  const currentSeed = currentQuestion?.prompt ?? "";
  const currentAnswer = answers[currentIndex] ?? "";

  function handleAnswerChange(val: string) {
    setAnswers((prev) => ({ ...prev, [currentIndex]: val }));
  }

  function handleClearAnswer() {
    setAnswers((prev) => ({ ...prev, [currentIndex]: "" }));
    setLatestResult(null);
  }

  function handleSelectQuestion(index: number) {
    setCurrentIndex(index);
    setLatestResult(null);
    setErrorBanner(null);
  }

  function handleNextQuestion() {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex((prev) => prev + 1);
      setLatestResult(null);
      setErrorBanner(null);
    }
  }

  function handleSubmit() {
    if (!currentAnswer.trim() || !currentQuestion) return;
    setErrorBanner(null);
    startTransition(async () => {
      const res = await runRetrievalAttemptAction(
        currentQuestion.unitId,
        currentQuestion.seedIndex,
        currentQuestion.prompt,
        currentAnswer.trim(),
      );
      if (res.state === "ok") {
        setLatestResult(res.data);
        if (res.data.passed) {
          // A passing attempt on a due seed is the re-check: clear it locally.
          setDueSet((prev) => {
            if (!prev.has(currentQuestion.seedIndex)) return prev;
            const next = new Set(prev);
            next.delete(currentQuestion.seedIndex);
            return next;
          });
        }
        const newSummary: RetrievalAttemptSummary = {
          id: res.data.attempt_id,
          student_id: res.data.student_id,
          unit_id: res.data.unit_id,
          seed_index: res.data.seed_index,
          seed_prompt: res.data.seed_prompt,
          passed: res.data.passed,
          feedback: res.data.feedback,
          evidence: res.data.evidence,
          tokens_charged: res.data.tokens_charged,
          created_at: res.data.created_at,
        };
        setAttempts((prev) => [newSummary, ...prev]);
      } else if (res.state === "unreachable") {
        setErrorBanner(
          "The lesson did not grade your answer. What you typed remains. Try again.",
        );
      } else if (res.state === "rejected") {
        if (res.code === "budget_exceeded" || res.status === 429) {
          setErrorBanner(
            "You used the grading and question budget for this unit. This answer stayed ungraded. Your dashboard shows the budget.",
          );
        } else if (res.code === "not_enrolled" || res.status === 403) {
          setErrorBanner(
            "Grading a drill answer needs an active enrollment in this unit.",
          );
        } else {
          setErrorBanner(
            res.message ||
              "Your answer stayed ungraded. You kept your budget. Try again.",
          );
        }
      }
    });
  }

  if (serviceDown) {
    return (
      <div className="rounded-lg border border-circuit-border bg-carbon-veil p-5">
        <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          The drills are down. The lesson above remains. Reload.
        </p>
      </div>
    );
  }

  if (!questions || questions.length === 0) {
    return null;
  }

  return (
    <div data-keel-retrieval-drill className="space-y-6">
      {/* Question tabs */}
      <div className="card-dark p-0 overflow-hidden border border-circuit-border">
        <div className="flex items-center justify-between gap-4 p-3.5 bg-carbon-veil border-b border-phosphor-blue-black">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-lime-pulse" />
            <span className="font-code-mono text-[12px] font-medium text-phosphor-white">
              retrieval
            </span>
          </div>

          <span className="font-code-mono text-[12px] text-moss-70">
            Question {currentIndex + 1} of {questions.length}
          </span>
        </div>

        {/* Question selector tabs */}
        <div className="flex items-center gap-1 p-2 bg-ground-iron border-b border-phosphor-blue-black overflow-x-auto">
          {questions.map((_, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSelectQuestion(idx)}
              className={`px-3 py-1.5 rounded text-[12.5px] font-code-mono transition-colors flex items-center gap-2 ${
                currentIndex === idx
                  ? "bg-carbon-veil text-lime-pulse font-medium"
                  : "text-moss-70 hover:text-phosphor-white"
              }`}
            >
              Question {idx + 1}
              {dueSet.has(idx) ? (
                <span data-keel-drill-due className="chip chip-alert text-[9px]">
                  DUE
                </span>
              ) : null}
            </button>
          ))}
        </div>

        {/* Prompt & Answer area */}
        <div className="p-6 bg-void-black/80 space-y-5">
          {dueSet.has(currentIndex) ? (
            <div
              data-keel-drill-due
              className="rounded border border-circuit-border bg-carbon-veil p-3.5 text-[13px] text-phosphor-white"
            >
              <p>
                This question is due for review. A passing answer clears the due flag.
              </p>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <span className="eyebrow text-[11px]">
              Explain from memory
            </span>
            <p className="text-[16px] leading-relaxed text-phosphor-white">
              {currentSeed}
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between text-[12px] text-moss-70">
              <label
                htmlFor={`retrieval-answer-${currentIndex}`}
                className="font-code-mono text-[11px] uppercase tracking-wider"
              >
                Your answer, in your own words
              </label>
              {currentAnswer ? (
                <button
                  type="button"
                  onClick={handleClearAnswer}
                  disabled={isPending}
                  className="hover:text-phosphor-white transition-colors"
                >
                  Clear
                </button>
              ) : null}
            </div>

            <textarea
              id={`retrieval-answer-${currentIndex}`}
              aria-label={`Retrieval answer for question ${currentIndex + 1}`}
              value={currentAnswer}
              onChange={(e) => handleAnswerChange(e.target.value)}
              disabled={isPending || !isEnrolled}
              rows={5}
              placeholder="Explain the idea in your own words. Describe how it works and name its parts."
              spellCheck={false}
              className="w-full text-[14.5px] leading-relaxed p-4 bg-void-black text-phosphor-white border border-circuit-border rounded-lg focus:border-lime-pulse focus:outline-none resize-y"
            />
          </div>
        </div>

        {/* Action bar */}
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
                and enroll to run the drills here.
              </p>
            ) : !isEnrolled ? (
              <p>
                Running the drills needs an active enrollment in this unit.{" "}
                <Link
                  href={`/map`}
                  className="text-fern-link underline hover:text-phosphor-white"
                >
                  Enroll from your progress map
                </Link>
                .
              </p>
            ) : (
              <p>
                The lesson grades your answer. Wrong answers return for review.
              </p>
            )}
          </div>

          <div>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isPending || !isEnrolled || !currentAnswer.trim()}
              className="btn btn-accent btn-sm"
            >
              {isPending ? (
                <>
                  <span className="h-2 w-2 rounded-full bg-void-black animate-pulse" />
                  Grading your answer
                </>
              ) : (
                "Grade this answer"
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

      {/* Latest verdict display */}
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
              <span className="text-[14.5px] font-medium text-phosphor-white">
                {latestResult.passed
                  ? "That explanation passes"
                  : "Not yet"}
              </span>
            </div>

            <div className="flex items-center gap-3 font-code-mono text-[11px] text-moss-70">
              <span>
                {latestResult.tokens_charged} tokens used
              </span>
              <span>
                Attempt #{latestResult.attempt_id}
              </span>
            </div>
          </div>

          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-carbon-veil border border-circuit-border space-y-1.5">
              <span className="eyebrow text-[11px]">
                Feedback on your answer
              </span>
              <p className="text-[14.5px] leading-relaxed text-phosphor-white">
                {latestResult.feedback}
              </p>
            </div>

            {latestResult.evidence ? (
              <div className="p-4 rounded-lg bg-carbon-veil border border-circuit-border space-y-1.5">
                <span className="eyebrow text-[11px]">
                  The lesson passage your answer met
                </span>
                <p className="font-code-mono text-[13px] leading-relaxed text-moss-80">
                  &ldquo;{latestResult.evidence}&rdquo;
                </p>
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="button"
              onClick={handleClearAnswer}
              className="btn btn-ghost btn-sm text-[12px]"
            >
              Try again
            </button>

            {currentIndex < questions.length - 1 ? (
              <button
                type="button"
                onClick={handleNextQuestion}
                className="btn btn-accent btn-sm text-[12px]"
              >
                Next question
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Retrieval Attempt history */}
      {attempts.length > 0 ? (
        <div className="card-dark space-y-4">
          <h4 className="eyebrow text-[12px]">
            {`Every drill answer you have given (${attempts.length})`}
          </h4>

          <div className="space-y-2.5">
            {attempts.map((att) => (
              <div
                key={att.id}
                className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-lg bg-carbon-veil border border-circuit-border font-code-mono text-[12px]"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`chip ${att.passed ? "chip-live" : "chip-outline"} text-[10px]`}
                  >
                    {att.passed ? "PASSED" : "NOT YET"}
                  </span>
                  <span className="text-phosphor-white">
                    Question {att.seed_index + 1}
                  </span>
                  <span className="text-moss-70">
                    {att.tokens_charged} tokens
                  </span>
                  <span className="text-moss-70">
                    attempt #{att.id}
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
