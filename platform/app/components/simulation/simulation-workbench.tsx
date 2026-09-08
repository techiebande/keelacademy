"use client";

import { useState } from "react";
import type {
  SimulationSession,
  SimulationTurn,
  RubricCriterionResult,
} from "@/lib/simulation";
import { humanizeId } from "@/lib/text";

// Display copy only. What each persona says, and how a transcript is scored,
// comes from content/personas/*.yaml and content/personas/backstory/*.md.
interface PersonaConfig {
  id: string;
  name: string;
  role: string;
  description: string;
  scorecardTitle: string;
}

const PERSONA_CONFIGS: Record<string, PersonaConfig> = {
  "discovery-call": {
    id: "discovery-call",
    name: "Sarah Jenkins",
    role: "VP of Operations, OmniCart Operations",
    description:
      "Her team reconciles 4,000 invoices a month and it takes two to three days. Find what costs that time before you offer a build.",
    scorecardTitle: "How this call was scored",
  },
  "technical-stakeholder": {
    id: "technical-stakeholder",
    name: "Marcus Vance",
    role: "Staff AI Architect, OmniCart Operations",
    description:
      "He has read your code before the call. Expect questions on your evaluation set, cost per invoice, latency, and what the system does when the model is wrong.",
    scorecardTitle: "How this defence was scored",
  },
  "business-owner": {
    id: "business-owner",
    name: "Elena Rostova",
    role: "Managing Director, OmniCart Operations",
    description:
      "She owns profit and loss for an $80M distribution business. Say what your build saves in hours and money, and what happens on a disputed invoice. Plain words only.",
    scorecardTitle: "How this defence was scored",
  },
};

interface SimulationWorkbenchProps {
  initialSession: SimulationSession | null;
  studentId: number;
  personaId?: string;
}

export function SimulationWorkbench({
  initialSession,
  studentId,
  personaId,
}: SimulationWorkbenchProps) {
  const resolvedPersonaId = personaId ?? initialSession?.persona_id ?? "discovery-call";
  const persona = PERSONA_CONFIGS[resolvedPersonaId] || {
    id: resolvedPersonaId,
    name: resolvedPersonaId,
    role: "Practice conversation",
    description: "A written brief drives this conversation and a rubric scores the transcript.",
    scorecardTitle: "How this conversation was scored",
  };

  const [session, setSession] = useState<SimulationSession | null>(initialSession);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [concluding, setConcluding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startNewCall = async () => {
    setStarting(true);
    setError(null);
    try {
      const res = await fetch("/api/simulation/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona_id: persona.id }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || data.error || "The conversation could not be started");
      }
      setSession(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The conversation could not be started");
    } finally {
      setStarting(false);
    }
  };

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!session || !inputMessage.trim() || loading || session.status !== "in_progress") return;

    const currentInput = inputMessage.trim();
    setInputMessage("");
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/simulation/turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          simulation_id: session.id,
          message: currentInput,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || data.error || "That message did not go through");
      }
      setSession(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "That message did not go through");
      setInputMessage(currentInput);
    } finally {
      setLoading(false);
    }
  };

  const concludeCall = async () => {
    if (!session || session.status !== "in_progress" || concluding) return;
    setConcluding(true);
    setError(null);

    try {
      const res = await fetch("/api/simulation/conclude", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ simulation_id: session.id }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || data.error || "The transcript could not be scored");
      }
      setSession(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The transcript could not be scored");
    } finally {
      setConcluding(false);
    }
  };

  const statusLabel =
    session === null
      ? "Not started"
      : session.status === "in_progress"
        ? "In progress"
        : session.status === "abandoned"
          ? "Not yet"
          : session.verdict
            ? session.verdict.passed
              ? "Passed"
              : "Not yet"
            : "Not yet";

  return (
    <div className="space-y-8">
      <section aria-labelledby="persona-title" className="card-dark">
        <p className="eyebrow">Who you are talking to</p>
        <h2 id="persona-title" className="heading-md mt-3">
          {persona.name}
        </h2>
        <p className="mt-2 text-[13.5px] text-[color:var(--text-faint-on-dark)]">{persona.role}</p>
        <p className="mt-4 max-w-[70ch] text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {persona.description}
        </p>
        <p className="mt-6 max-w-[70ch] rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
          {persona.name} is an AI. It follows a written brief. Your side of the transcript
          is scored against a rubric you can read in the unit.
        </p>
      </section>

      {error ? (
        <p
          role="alert"
          className="rounded-lg border border-circuit-border bg-carbon-veil p-4 text-[14.5px] leading-relaxed text-phosphor-white"
        >
          {error}
        </p>
      ) : null}

      {!session ? (
        <section aria-labelledby="start-title" className="card-dark max-w-[62ch]">
          <h2 id="start-title" className="heading-md">
            Nothing has started yet
          </h2>
          <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
            You type. {persona.name} answers. We save the transcript. End when you want, and
            run it again as often as you like.
          </p>
          <button
            type="button"
            onClick={startNewCall}
            disabled={starting || studentId === 0}
            className="btn btn-accent btn-sm mt-7"
          >
            {starting ? "Starting" : "Start the conversation"}
          </button>
          {studentId === 0 ? (
            <p className="mt-4 text-[14px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
              We could not read your account, so we cannot save yet. Refresh.
            </p>
          ) : null}
        </section>
      ) : (
        <div className="space-y-8">
          <section
            aria-label="Conversation state"
            className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-circuit-border bg-carbon-veil p-5"
          >
            <div className="flex flex-wrap items-center gap-3">
              <span className={statusLabel === "Passed" ? "chip chip-live" : "chip chip-outline"}>
                {statusLabel.toUpperCase()}
              </span>
              <span className="font-code-mono text-[13px] text-moss-70">
                {`${session.turns.length} ${session.turns.length === 1 ? "message" : "messages"} so far`}
              </span>
            </div>
            {session.status === "in_progress" ? (
              <button
                type="button"
                onClick={concludeCall}
                disabled={concluding || loading}
                className="btn btn-primary btn-sm"
              >
                {concluding ? "Scoring" : "End it and get scored"}
              </button>
            ) : (
              <button
                type="button"
                onClick={startNewCall}
                disabled={starting}
                className="btn btn-primary btn-sm"
              >
                {starting ? "Starting" : "Run it again"}
              </button>
            )}
          </section>

          <section aria-labelledby="transcript-title" className="card-dark">
            <h2 id="transcript-title" className="heading-md">
              The transcript
            </h2>
            {session.turns.length === 0 ? (
              <p className="mt-4 text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                {`Nothing said yet. Open as you would on a real call.`}
              </p>
            ) : (
              <ol className="mt-6 space-y-4">
                {session.turns.map((turn: SimulationTurn, idx: number) => {
                  const fromStudent = turn.role === "student";
                  return (
                    <li
                      key={idx}
                      className={
                        fromStudent
                          ? "rounded-lg border border-circuit-border bg-void-black p-4"
                          : "rounded-lg border border-circuit-border bg-carbon-veil p-4"
                      }
                    >
                      <p
                        className={
                          fromStudent
                            ? "font-code-mono text-[12px] uppercase tracking-[0.14em] text-lime-pulse"
                            : "font-code-mono text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]"
                        }
                      >
                        {fromStudent ? "You" : persona.name}
                      </p>
                      <p className="mt-3 whitespace-pre-wrap text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                        {turn.content}
                      </p>
                    </li>
                  );
                })}
              </ol>
            )}
            {loading ? (
              <p
                aria-live="polite"
                className="mt-6 font-code-mono text-[13px] text-moss-70"
              >
                {`${persona.name} is typing`}
              </p>
            ) : null}
          </section>

          {session.status === "in_progress" ? (
            <form onSubmit={sendMessage} className="card-dark">
              <label htmlFor="sim-message" className="field-label">
                What you say next
              </label>
              <textarea
                id="sim-message"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                disabled={loading}
                rows={5}
                className="field-input font-inter-variable"
                placeholder="Ask one question at a time. Short is fine."
              />
              <button
                type="submit"
                disabled={loading || !inputMessage.trim()}
                className="btn btn-accent btn-sm mt-5"
              >
                {loading ? "Sending" : "Send"}
              </button>
            </form>
          ) : null}

          {session.verdict ? (
            <section aria-labelledby="scorecard-title" className="card-dark">
              <div className="flex flex-wrap items-baseline justify-between gap-4">
                <h2 id="scorecard-title" className="heading-md">
                  {persona.scorecardTitle}
                </h2>
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={session.verdict.passed ? "chip chip-live" : "chip chip-outline"}
                  >
                    {session.verdict.passed ? "PASSED" : "NOT YET"}
                  </span>
                  <span className="font-code-mono text-[13px] text-moss-70">
                    {`${session.verdict.score_pct}%`}
                  </span>
                </div>
              </div>
              <p className="mt-5 max-w-[74ch] text-[15.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                {session.verdict.summary}
              </p>

              {session.verdict.criteria && session.verdict.criteria.length > 0 ? (
                <ul className="mt-8">
                  {session.verdict.criteria.map((c: RubricCriterionResult, i: number) => (
                    <li
                      key={c.id || i}
                      className="border-t border-[color:var(--line-on-dark-strong)] py-4 first:border-t-0 first:pt-0"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <span className="text-[15px] text-phosphor-white">
                          {humanizeId(c.id)}
                        </span>
                        <span className={c.passed ? "chip chip-live" : "chip chip-outline"}>
                          {c.passed ? "PASSED" : "NOT YET"}
                        </span>
                      </div>
                      {c.feedback ? (
                        <p className="mt-3 max-w-[74ch] text-[14.5px] leading-relaxed text-[color:var(--text-muted-on-dark)]">
                          {c.feedback}
                        </p>
                      ) : null}
                      {c.evidence ? (
                        <blockquote className="mt-3 border-l-2 border-circuit-border pl-4">
                          <p className="text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-faint-on-dark)]">
                            Quoted from your transcript
                          </p>
                          <p className="mt-2 text-[14.5px] leading-relaxed text-moss-80">
                            {c.evidence}
                          </p>
                        </blockquote>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
