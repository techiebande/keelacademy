"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import type {
  ConciergeMode,
  ConciergeTurn,
  PracticeRouteData,
} from "@/lib/practice";

type ConciergePanelProps = {
  unitId: string;
  isEnrolled: boolean;
  isSignedIn: boolean;
  serviceDown?: boolean;
  routeData: PracticeRouteData | null;
  initialTurns: ConciergeTurn[];
  /**
   * A unit script places this panel inside its own phase section and introduces
   * it in its own words, so it takes the section wrapper and the built-in heading
   * off. Both stay on for any unit still rendering the fixed layout.
   */
  embedded?: boolean;
};

/**
 * The service sends its own reason string for its own records. The student reads
 * this instead, so internal wording never reaches the page.
 */
function reasonFor(mode: ConciergeMode): string {
  return mode === "guard"
    ? "You finished the practice route for this unit. Questions now walk through steps with you, but it does not write the deliverable."
    : "You are on the practice route. It explains concepts and writes extra exercises on request.";
}

export function ConciergePanel({
  unitId,
  isEnrolled,
  isSignedIn,
  serviceDown = false,
  routeData,
  initialTurns,
  embedded = false,
}: ConciergePanelProps) {
  const [turns, setTurns] = useState<ConciergeTurn[]>(initialTurns);
  const [question, setQuestion] = useState("");
  const [isPending, startTransition] = useTransition();
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isBudgetExhausted, setIsBudgetExhausted] = useState(false);
  const [showHistory, setShowHistory] = useState(true);

  // Derive initial mode and reason from server-provided route state
  const initialMode: ConciergeMode =
    routeData?.status === "completed" ? "guard" : "teach";

  const [currentMode, setCurrentMode] = useState<ConciergeMode>(
    turns.length > 0 ? turns[turns.length - 1].mode : initialMode,
  );
  const [modeReason, setModeReason] = useState<string>(
    reasonFor(turns.length > 0 ? turns[turns.length - 1].mode : initialMode),
  );
  const [latestAnswer, setLatestAnswer] = useState<string | null>(
    turns.length > 0 ? turns[turns.length - 1].answer : null,
  );
  const [latestTokens, setLatestTokens] = useState<number | null>(
    turns.length > 0 ? turns[turns.length - 1].tokens_charged : null,
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isPending) return;

    const submittedQuestion = question.trim();
    setErrorMsg(null);
    setIsBudgetExhausted(false);

    startTransition(async () => {
      try {
        const res = await fetch("/api/concierge/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            unit_id: unitId,
            question: submittedQuestion,
          }),
        });

        if (res.status === 429) {
          setIsBudgetExhausted(true);
          setErrorMsg(
            "You used the grading and question budget for this unit. No more questions can go through. Your dashboard shows the budget.",
          );
          return;
        }

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          setErrorMsg(
            errData.message ||
              "That question did not go through. You kept your budget. Try it again.",
          );
          return;
        }

        const data = await res.json();
        const newTurn: ConciergeTurn = {
          id: data.turn_id,
          student_id: data.student_id,
          unit_id: data.unit_id,
          mode: data.mode,
          question: submittedQuestion,
          answer: data.answer,
          tokens_charged: data.tokens_charged,
          created_at: data.created_at,
        };

        setTurns((prev) => [...prev, newTurn]);
        setCurrentMode(data.mode);
        setModeReason(reasonFor(data.mode));
        setLatestAnswer(data.answer);
        setLatestTokens(data.tokens_charged);
        setQuestion("");
      } catch {
        setErrorMsg(
          "That question did not reach the assistant. You kept your budget. Try it again.",
        );
      }
    });
  };

  const panel = (
      <div className="card-dark space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 border-b border-phosphor-blue-black pb-5">
          {embedded ? null : (
          <div className="space-y-2 max-w-[62ch]">
            <h2 className="heading-lg text-phosphor-white">
              Ask about this unit
            </h2>
            <p className="text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              An assistant that has read this unit and nothing else. Ask about a concept.
              Ask for another exercise. Ask about an error. It is an AI, so it does not
              write your deliverable.
            </p>
          </div>
          )}
          {/* How it is answering right now */}
          <div className="p-4 rounded-lg bg-carbon-veil border border-circuit-border space-y-1.5 shrink-0 max-w-[280px]">
            {currentMode === "teach" ? (
              <span className="chip chip-live text-[11px]">EXPLAINS FREELY</span>
            ) : (
              <span className="chip chip-outline text-[11px]">GUIDED</span>
            )}
            <p className="text-[12px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              {modeReason}
            </p>
          </div>
        </div>

        {/* Service State Gate */}
        {serviceDown ? (
          <div className="p-4 rounded-lg bg-carbon-veil border border-circuit-border text-[14px] text-phosphor-white">
            The assistant is down. Your earlier questions remain. Try again.
          </div>
        ) : !isSignedIn ? (
          <div className="p-6 rounded-lg bg-carbon-veil border border-circuit-border space-y-3">
            <p className="text-[15px] text-phosphor-white">
              Sign in to ask about this unit.
            </p>
            <Link
              href={`/sign-in?next=/units/${unitId}#concierge`}
              className="btn btn-primary btn-sm"
            >
              Sign in
            </Link>
          </div>
        ) : !isEnrolled ? (
          <div className="p-6 rounded-lg bg-carbon-veil border border-circuit-border space-y-3">
            <p className="text-[15px] text-phosphor-white">
              You ask questions on Unit {unitId} after you enroll in it.
            </p>
            <Link href={`/units/${unitId}#build`} className="btn btn-primary btn-sm">
              See enrollment steps
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Question Input Box */}
            <form
              onSubmit={handleSubmit}
              className="space-y-4"
            >
              <div className="flex items-center justify-between gap-4">
                <label
                  htmlFor="concierge-question"
                  className="eyebrow text-[11px]"
                >
                  Your question
                </label>
              </div>

              <textarea
                id="concierge-question"
                rows={3}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={
                  currentMode === "teach"
                    ? "Ask about a concept in this lesson."
                    : "Paste the error and what you expected."
                }
                disabled={isPending || isBudgetExhausted}
                className="field-input text-[14.5px]"
              />

              {errorMsg ? (
                <p
                  role="alert"
                  className="rounded-lg border border-circuit-border bg-carbon-veil p-3.5 text-[13.5px] leading-relaxed text-phosphor-white"
                >
                  {errorMsg}
                </p>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-[12px] text-[color:var(--text-faint-on-dark)]">
                  Answers come from an AI. Check anything it tells you against the lesson.
                </span>
                <button
                  type="submit"
                  disabled={!question.trim() || isPending || isBudgetExhausted}
                  className="btn btn-accent btn-sm"
                >
                  {isPending ? <span>Working…</span> : <span>Ask</span>}
                </button>
              </div>
            </form>

            {/* Latest Reply */}
            {latestAnswer ? (
              <div className="p-6 rounded-lg bg-carbon-veil border border-lime-pulse/40 space-y-3">
                <div className="flex items-center justify-between border-b border-phosphor-blue-black pb-2">
                  <div className="flex items-center gap-2 font-code-mono text-[11px]">
                    <span className="text-lime-pulse font-medium">ANSWER</span>
                  </div>
                  {latestTokens !== null ? (
                    <span className="font-code-mono text-[11px] text-moss-70">
                      {latestTokens} tokens used
                    </span>
                  ) : null}
                </div>
                <div className="text-[14.5px] leading-relaxed text-phosphor-white whitespace-pre-wrap">
                  {latestAnswer}
                </div>
              </div>
            ) : null}

            {/* Turn History */}
            {turns.length > 0 ? (
              <div className="space-y-4 pt-2">
                <button
                  type="button"
                  onClick={() => setShowHistory((prev) => !prev)}
                  aria-expanded={showHistory}
                  className="font-code-mono text-[12px] text-moss-70 hover:text-phosphor-white transition-colors"
                >
                  Everything you have asked here ({turns.length}){" "}
                  <span aria-hidden>{showHistory ? "▲" : "▼"}</span>
                </button>

                {showHistory ? (
                  <div className="space-y-3">
                    {turns.map((turn, index) => (
                      <div key={turn.id ?? index} className="p-4 rounded-lg bg-ground-iron border border-circuit-border space-y-2">
                        <div className="flex items-center justify-between gap-3 font-code-mono text-[12px]">
                          <span className="text-phosphor-white font-medium truncate">
                            {turn.question}
                          </span>
                          <span className="shrink-0 text-[11px] text-moss-70">
                            {turn.tokens_charged} tokens
                          </span>
                        </div>
                        <div className="text-[13.5px] leading-relaxed text-[color:var(--text-muted-on-dark)] whitespace-pre-wrap">
                          {turn.answer}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        )}
      </div>
  );

  if (embedded) return panel;

  return (
    <section
      id="concierge"
      data-keel-section="concierge"
      className="scroll-mt-28"
    >
      {panel}
    </section>
  );
}
