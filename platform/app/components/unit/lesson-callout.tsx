"use client";

import type { LessonBlock } from "@/lib/content";

/**
 * A gotcha: the failure a reader is about to walk into. Authored as a
 * `> **Gotcha: <title>**` blockquote, it used to render as a plain quote in the
 * faintest text colour on the page, which made the warning quieter than the
 * prose around it. Here it gets a surface of its own and full-strength text.
 */
export function LessonCallout({ title, html }: { title: string; html: string }) {
  return (
    <aside className="callout callout-gotcha">
      <p className="callout-label">Watch out</p>
      <p className="callout-title">{title}</p>
      <div className="lesson-prose callout-body" dangerouslySetInnerHTML={{ __html: html }} />
    </aside>
  );
}

/**
 * A checkpoint or a practice prompt: answer it, then read an answer.
 *
 * Both beats used to print their answer in the paragraph directly underneath,
 * so "predict, then check" was advice the page itself made impossible to follow.
 * The answer now sits behind a disclosure, with somewhere to write first.
 *
 * Deliberately server-rendered with no client JavaScript: `details` and
 * `textarea` both work on their own, so the beat survives a failed hydration and
 * needs no state to be honest about. The box is scratch space, not a submission,
 * and says so.
 */
export function LessonCheckpoint({
  block,
  inputId,
}: {
  block: Extract<LessonBlock, { type: "checkpoint" } | { type: "exercise" }>;
  inputId: string;
}) {
  const isCheckpoint = block.type === "checkpoint";

  const handleToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    if (e.currentTarget.open) {
      const body = e.currentTarget.querySelector<HTMLElement>(".reveal-body");
      body?.focus();
    }
  };

  return (
    <section className="callout callout-checkpoint" aria-label={isCheckpoint ? "Checkpoint" : "Practice prompt"}>
      <p className="callout-label callout-label-accent">
        {isCheckpoint ? "Checkpoint" : "Try it"}
      </p>

      {isCheckpoint ? (
        <>
          <div
            className="lesson-prose callout-body"
            dangerouslySetInnerHTML={{ __html: block.scenarioHtml }}
          />
          <div
            className="lesson-prose callout-question"
            dangerouslySetInnerHTML={{ __html: block.questionHtml }}
          />
        </>
      ) : (
        <div
          className="lesson-prose callout-question"
          dangerouslySetInnerHTML={{ __html: block.promptHtml }}
        />
      )}

      <div className="callout-scratch">
        <label className="callout-scratch-label" htmlFor={inputId}>
          Your answer
        </label>
        <textarea
          id={inputId}
          name={inputId}
          className="field-input"
          rows={3}
          aria-describedby={`${inputId}-note`}
        />
        <p id={`${inputId}-note`} className="callout-scratch-note">
          Scratch space. Nothing here saves or grades. Commit to an answer before you
          read one.
        </p>
      </div>

      {block.hintsHtml && block.hintsHtml.length > 0 ? (
        <div className="callout-hints my-3 space-y-2">
          {block.hintsHtml.map((hintHtml, idx) => (
            <details key={idx} className="reveal reveal-hint" onToggle={handleToggle}>
              <summary>{`Hint ${idx + 1}`}</summary>
              <div
                tabIndex={-1}
                className="lesson-prose reveal-body focus:outline-none"
                dangerouslySetInnerHTML={{ __html: hintHtml }}
              />
            </details>
          ))}
        </div>
      ) : null}

      <details className="reveal" onToggle={handleToggle}>
        <summary>Show the answer</summary>
        <div
          tabIndex={-1}
          className="lesson-prose reveal-body focus:outline-none"
          dangerouslySetInnerHTML={{ __html: block.answerHtml }}
        />
      </details>
    </section>
  );
}
