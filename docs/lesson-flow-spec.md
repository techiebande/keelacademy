# Lesson flow spec: exit cards and resume persistence (U1–U3)

Status: design contract, ratified 2026-09-02. Owners: the U1, U2 and U3 workers.

The invariant this spec implements, from the 2026-09-02 research synthesis:

> The product always knows and surfaces exactly one next action, and every
> exit is a designed stopping point, never a dead end.

Three surfaces follow from it: the end of a unit is a designed exit (U1),
every phase boundary inside a unit is a legitimate stopping point (U2), and
returning to a unit you left mid-read resumes you where you stopped (U3).

Evidence anchors: Duolingo's exit-deck and Netflix's 10-second post-play
(lesson exits are designed surfaces); Crafting Interpreters' chapter codas
(ritualized endings); Kindle's position sync and Goodreads' pinned
"currently reading" (resume owns the most valuable pixel); the Zeigarnik
effect (stopping mid-unit is a hook, not a failure).

## Ground rules for all three

- Content owns every word a student reads; the app owns structure, data and
  state. U1 and U2 copy is app-owned because it is structural (names, times,
  counts pulled from real data), not teaching. If a line needs teaching
  voice, it belongs in `learn.md`, not here.
- Copy discipline (binding, from platform/app/AGENTS.md): Shiffman style per
  `.agents/skills/shiffman-style-lessons` on anything the student reads as prose; terse
  surfaces (exit cards, boundary markers, error copy) stay short,
  declarative, active, concrete. No internal architecture names. "Not
  yet", never "fail". Uppercase only for short data-state chips.
- Honest states only: no fake progress, no invented counts, no placeholder
  telemetry. If a data source is unreachable, the surface renders nothing
  rather than something untrue.
- Accessibility: WCAG 2.2 AA, visible focus ring, real links for navigation,
  320px reflow, and the surfaces work with JavaScript off unless the spec
  says the surface is an enhancement that legitimately needs it.
- The demo harnesses stay green. If copy or structure changes break a demo
  grep, update the grep (expected, not a violation) and re-run the four
  demos if the environment allows; report honestly if it does not.

## U1 — End-of-unit exit card

Placement: after the last phase section of the unit script (after the
`ask`/concierge slot for 3.2.1), inside the lesson canvas, full content-track
width like other apparatus.

Anatomy, top to bottom:

1. A label chip: `UNIT COMPLETE` (data-state chip, uppercase allowed).
2. One recap line, data-driven, honest: what the student actually did in
   this unit. For 3.2.1 the source is real data already on the page
   (practice attempts, retrieval state, submission/verdict state where
   fetchable). If the student has no recorded activity, the line states
   what the unit covers, not what the student did.
3. The single next action: one primary button linking to the next unit,
   from `yaml.gate.unlocks[0]` when the unit passed its gate, else the
   unit's own verify/build surface (keep working this unit). Exactly one
   primary action; everything else is quiet.
4. A wrap-up option, equally legitimate: a quiet secondary link ("Wrap up") pointing at the dashboard, with one line saying the student's
   place is saved and reviews will be waiting (only if the re-check
   schedule actually has items; else omit the claim).

States to handle (all from data already loadable by the unit page):

- Gate passed, next unit unlocked: primary button "Start <next unit id>".
- Not passed yet: primary button stays on-unit ("Open the build brief" or
  the completion problem anchor); a quiet line names the next unit as
  locked, without architecture vocabulary.
- No unlocks (phase-final unit): next action is the phase's remaining
   units or the curriculum page; never invent a next unit.
- Signed out: the card still renders (the lesson page is public); next
  action becomes the sign-in/checkout path wording already used on the
  page. No personalization claims for anonymous readers.

Done when: the card renders for 3.2.1 in all four states (forced by data
variations), lint and build are clean, and no demo grep broke.

## U2 — Phase-boundary exit markers

Placement: in `UnitScript`, rendered at the end of each phase section
except the last (the last phase's exit is the U1 card). The marker sits
inside the existing phase boundary rhythm (the hairline plus spacing stays
the boundary; the marker is quiet, inside the measure, not a panel).

Anatomy: one mono line, data-assembled:

`END OF LEARN · NEXT: PRACTICE, ABOUT 4 MIN · STOP HERE IF YOU LIKE`

- Phase names uppercase as data-state chips; read time from the script's
  own word-count estimates (already computed for the rail), summed over
  the next phase's prose. Omit the time when it cannot be computed rather
  than guessing.
- One line, no border, no card. The boundary hairline already says
  "section break"; the marker adds "this is a clean stopping point."
- It is an anchor target too (stable id per boundary) so U3 can resume to
  a boundary directly.

Constraint: no client JavaScript. The marker is server-rendered text.

Done when: markers render between every phase of 3.2.1's script, times are
computed from real data, and the page still reads as one piece of writing
(no visual regression at the boundary).

## U3 — Resume persistence

Model: per-device, localStorage, keyed by unit id. This is deliberately
not a progress claim: the store is `keel-reading-position`, an object
`{ unitId, phaseId, headingId, scrollRatio, savedAt }` updated at most
every few seconds while the student reads. Nothing is written for
anonymous scroll-and-leave of the marketing surfaces; only unit pages
write it.

Two restore surfaces:

1. Unit-page resume banner (enhancement, client component): when the store
   holds THIS unit with `savedAt` from a previous session (not this one)
   and `scrollRatio` above ~0.03, render a quiet banner under the chapter
   opener: "You stopped at <beat name> in <phase>. Resume there." linking
   to the stored anchor. Dismissable for the session. Renders nothing
   without JavaScript; that is acceptable and must be the documented
   fallback.
2. Dashboard continue card on `/me` (enhancement, client component):
   reads the same store, shows the most recent position as a "Continue"
   card with unit, beat, and a one-line next action. If the student is
   signed in, the card defers to any stronger server-known next action
   already on the dashboard (due reviews, pending verdict); the local card
   never contradicts server state, it fills the gap when the server has
   nothing (a student mid-read with no graded work).

Saving rules: IntersectionObserver or scroll math on the script body;
store the current rail heading and phase (the rail's own active-id logic
is the reference implementation); ratio is scroll position over total
document height; `savedAt` is epoch millis. Storage failures are silent
(the feature is an enhancement).

Explicitly out of scope (recorded for later, not built now): server-side
position sync across devices, which needs a practice-service endpoint and
a schema decision; and using reading position as gate or progress
evidence, which it must never be.

Done when: a reader who stops mid-3.2.1 and returns sees the banner with
the correct beat, the `/me` card links back to the same anchor, both
disappear when the store is empty, and neither surface renders server-side
claims (view-source shows no fake state).

## Verification sketch (all three milestones)

`npm run lint` and `npm run build` clean in platform/app; dev-server fetch
of /units/3.2.1 shows the new surfaces; forced-state checks for U1's four
states; storage-matrix check for U3 (empty store, this-session store,
stale store); demo greps re-run if copy they assert on changed.
