import type { ReactNode } from "react";
import { LessonAside } from "@/components/unit/lesson-aside";
import { LessonCallout, LessonCheckpoint } from "@/components/unit/lesson-callout";
import { LessonContents } from "@/components/unit/lesson-contents";
import { UnitBoundary } from "@/components/unit/unit-boundary";
import type { ScriptItem, ScriptPhase } from "@/lib/content";

/**
 * A unit lesson authored as one script, rendered in the order it was written.
 *
 * The boundary this component draws: content owns every word a student reads, and
 * the app owns structure, data and state. So there is no heading, no lead
 * sentence and no bridge copy in here. The script says "now that you have seen
 * what breaks, watch this run on something smaller" in the author's own words,
 * then marks where the workbench goes; this walks the items and puts the
 * workbench there.
 *
 * The six phase sections it emits carry the same ids and `data-keel-section`
 * values the fixed layout emits, because every `#learn` style anchor and the demo
 * greps key off them.
 *
 * One grid wraps the whole script, not one per phase. An earlier version gave the
 * rail to the teaching phase alone, which moved the reading column 264px sideways
 * at the first phase boundary. A lesson that reads as one piece of writing has to
 * hold one left edge from the title to the last line.
 *
 * The grid is `.flow`, and it is repeated on every level that holds content: the
 * canvas, each phase, and each prose blob. That repetition is what lets a `<pre>`
 * inside a `dangerouslySetInnerHTML` string break out of the reading column
 * without subgrid: a nested `.flow` claims the full canvas width, so its tracks
 * resolve to the same pixels as its parent's.
 */
export function UnitScript({
  phases,
  preamble,
  slots,
  checked,
}: {
  phases: ScriptPhase[];
  preamble: ScriptItem[];
  slots: Record<string, ReactNode>;
  /** The oldest `last_verified` date in the unit, or null if none is recorded. */
  checked: string | null;
}) {
  // The rail is the page's only in-page navigation, so it lists the script's own
  // `##` headings across every phase, in the order they were written. Subheadings
  // are dropped rather than nested: eight authored beats fit without the rail
  // scrolling inside itself, and their anchors are still in the document for
  // anyone who links one. Each entry carries its estimated read time, word-count
  // based, so a scanner can see that a beat is 2 min or 6 min before starting it.
  const contents = phases
    .flatMap((phase) => phase.contents)
    .map((entry) => ({ ...entry, headings: [] }));

  return (
    <div className="lesson-canvas flow unit-script-layout">
      <LessonContents entries={contents} readLine={SCRIPT_READ_LINE} />

      <div id={SCRIPT_BODY_ID} className="flow unit-script-body">
        {preamble.length > 0 ? (
          <div className="flow unit-script-phase">
            <ScriptItems items={preamble} slots={slots} keyPrefix="preamble" />
          </div>
        ) : null}

        {phases.map((phase, index) => {
          const nextPhase = phases[index + 1] ?? null;
          return (
            <section
              key={phase.id}
              id={phase.id}
              data-keel-section={phase.id}
              className="scroll-mt-28 flow unit-script-phase"
            >
              <ScriptItems items={phase.items} slots={slots} keyPrefix={phase.id} />
              {index === 0 && checked ? (
                <p className="lesson-checked">Checked for accuracy {checked}.</p>
              ) : null}
              {/*
                The boundary marker (spec U2) closes every phase but the last;
                the last phase's exit is the unit's own exit card, rendered by
                the page after this component. It is the final line of the
                phase that just ended, so the spacing that follows a phase is
                still what carries the section break.
              */}
              {nextPhase ? (
                <UnitBoundary
                  phaseId={phase.id}
                  nextPhaseId={nextPhase.id}
                  nextEstMinutes={phaseEstMinutes(nextPhase)}
                />
              ) : null}
            </section>
          );
        })}
      </div>
    </div>
  );
}

/** The element the rail measures its scroll position against. */
const SCRIPT_BODY_ID = "unit-script-body";

/** A script page has no second sticky bar, so the read line clears the 64px header. */
const SCRIPT_READ_LINE = 88;

/**
 * A phase's honest read time: the sum of the same per-beat estimates the rail
 * lists. Null when it cannot be computed, which is a phase with no beats of
 * its own or with any beat unmeasured: summing only the measured beats would
 * print a number that understates the phase, and the boundary marker drops its
 * time segment entirely rather than guess.
 */
function phaseEstMinutes(phase: ScriptPhase): number | null {
  if (phase.contents.length === 0) return null;
  let total = 0;
  for (const entry of phase.contents) {
    if (entry.estMinutes === undefined) return null;
    total += entry.estMinutes;
  }
  return total;
}

function ScriptItems({
  items,
  slots,
  keyPrefix,
}: {
  items: ScriptItem[];
  slots: Record<string, ReactNode>;
  keyPrefix: string;
}) {
  return (
    <>
      {items.map((item, index) => {
        const key = `${keyPrefix}-${index}`;

        if (item.type === "slot") {
          // A slot the page did not supply renders nothing. That is the honest
          // outcome: the apparatus is missing, not broken, and inventing a
          // placeholder for it would be a fake state.
          const node = slots[item.name];
          return node ? (
            <div key={key} className="flow-apparatus">
              {node}
            </div>
          ) : null;
        }

        if (item.type === "aside") {
          return (
            <LessonAside key={key} id={item.id} title={item.title} html={item.html} />
          );
        }

        if (item.type === "recap") {
          return (
            <aside key={key} className="callout callout-recap" aria-label={item.title}>
              <p className="callout-label">Recap</p>
              <p className="callout-title">{item.title}</p>
              <div className="lesson-prose callout-body" dangerouslySetInnerHTML={{ __html: item.html }} />
            </aside>
          );
        }

        if (item.type === "coda") {
          return (
            <aside key={key} className="callout callout-coda" aria-label={item.title}>
              <p className="callout-label">Closing</p>
              <p className="callout-title">{item.title}</p>
              <div className="lesson-prose callout-body" dangerouslySetInnerHTML={{ __html: item.html }} />
            </aside>
          );
        }

        if (item.type === "prose") {
          return (
            <div
              key={key}
              className="lesson-prose flow"
              dangerouslySetInnerHTML={{ __html: item.html }}
            />
          );
        }

        if (item.type === "callout") {
          return <LessonCallout key={key} title={item.title} html={item.html} />;
        }

        return <LessonCheckpoint key={key} block={item} inputId={`answer-${key}`} />;
      })}
    </>
  );
}
