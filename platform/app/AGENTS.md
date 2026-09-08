<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# UI/UX direction: DECIDED 2026-08-31

Both directions are now recorded in the repo-root `build-state.md`
decisions log under the 2026-08-31 entries, and they are binding. Read
them before writing any stylesheet or any copy. In short:

- **Visual.** Dark engineering-console language. Surface ladder
  void (`#000`) -> ground (`#0f1211`) -> carbon (`#151918`). Depth from
  1px hairlines and surface-value steps, never shadows. One rationed
  accent (`--color-lime-pulse`) for primary CTAs, active state, and live
  status. Space Grotesk display / Inter UI / Fira Mono code. The named
  component classes in `app/globals.css` (`.btn`, `.card-dark`, `.chip`,
  `.data-table`, `.field-input`, `.lesson-prose`, `.shell`, `.section`)
  are the styling surface; pages compose them plus Tailwind utilities.
  `app/globals.css` is no longer empty and is not to be emptied.
- **Copy.** Marketing and lesson prose follows
  `.agents/skills/shiffman-style-lessons` (live-build narration, visibly
  working through bugs, ask before tell, alive examples, honest confusion,
  warm curiosity, collaborator first-person "we"/"let's", ending with an
  invitation to experiment; zero corporate buzzwords). **Readability target:
  Flesch-Kincaid Grade 8 or below** for lesson prose; the audience includes
  non-native English speakers; prefer short sentences (under 20 words), common
  words, and explain-then-name for domain terms; see the plain-language rules
  in `.agents/skills/shiffman-style-lessons/SKILL.md`. Terse surfaces (dashboard,
  grading states, error copy) stay short, declarative, active, concrete.
  Internal architecture never appears in student-facing copy: no service
  names, no "Layer 1/Layer 2", no model tiers, no cockpit or cryptography
  metaphors, no invented product nouns. The grading layers are "automated
  checks" and "rubric review". Verdicts read "Passed" / "Not yet", never
  "fail". Uppercase is reserved for short data-state chips (PASSED, NOT YET, QUEUED, GRADING, CLEARED,
  LOCKED, EARNED, PAID, PENDING, EXPIRED, PLANNED). Identifier chips (Unit
  3.2.1, Phase 0, Student #5) and content-owned labels (phase badges from
  phases.yaml) keep authored casing; lowercase technical values (exit codes,
  check types) render as code.

**The anchor client is OmniCart Operations**, a multi-brand e-commerce retailer
and marketplace fulfillment hub; the domain is customer return intake, courier
delivery reconciliation, and merchant dispute triage. OmniCart and Meridian Mutual
are retired and must not be reintroduced.

Also binding:

1. Routes, functionality, and data flows are preserved.
2. Content-as-data rendering and the honesty rules hold (honest
   placeholders, no fake states, no fake telemetry, no invented content).
3. The demo harnesses stay green: a session that changes copy or structure
   updates the demo greps to match the new copy (updating them is
   expected, not a violation) and re-runs demo-rebate, demo-gates,
   demo-map, and demo-practice before closing.
4. Every new word of lesson copy is written under the
   shiffman-style-lessons skill (.agents/skills/shiffman-style-lessons).
5. Accessibility is part of the direction: WCAG 2.2 AA contrast on every
   text token, a visible `:focus-visible` ring that no rule removes, and
   reflow at 320px without horizontal scroll.

# Lesson delivery: DECIDED 2026-09-01

A lesson is delivered as one continuous typeset page, not as accordions
and not paged. The full rationale is in the repo-root `build-state.md`
under the 2026-09-01 lesson-delivery entry. What a later session needs to
know before touching `lib/content.ts`, `learn-section.tsx` or a
`learn.md`:

- **`learn.md` is read by two consumers, not one.** `platform/grading/practice/server.py`
  feeds it to the retrieval-drill judge, splitting on any `#`-`######`
  heading and scoring excerpts per seed keyword with heading hits weighted
  5x. So presentation changes are made in the renderer, not by rewriting
  the lesson. If you do change   heading text, re-run
  `smoke-routing-checks.py` and `smoke-recheck-checks.py` and confirm all
  seeds still consistent.
- **The three `##` sections are positional.** `last_verified` in
  `unit.yaml` still keys `concept_core` / `applied_context` /
  `tool_specifics`, and `lib/content.ts` maps those to the three sections
  by index. The keys are the authoring and freshness contract; their names
  are not student-facing and must not be printed on the page.
- **The renderer understands three authored markers**, and treats anything
  else as prose: `> **Gotcha: <title>**`, a
  `> **Predict, then check.**` blockquote whose answer is the paragraph
  after it, and a bold-led prompt whose next paragraph opens
  `One good answer:`. Both answer forms collapse behind a reveal with a
  scratch box above them, so predict-then-check is possible to follow.
  Writing an answer as plain prose under a prompt un-teaches the beat.
- **The reading measure is `--lesson-measure` (35em), not `ch`, and not on
  `.lesson-prose`.** That class is shared with the worked example, whose
  comparison table needs the shell width.
- Checkpoints are server-rendered with no client JavaScript (native
  `details` and `textarea`). The scratch box is not persisted and says so.
  The rail's bar is a scroll position, not progress through the material.

# Unit scripts: DECIDED 2026-09-01

A unit's `learn.md` may be authored as a **unit script**: one continuous
lesson covering all six phases, with markers saying where the app puts its
own apparatus. The boundary is **content owns every word a student reads;
the app owns structure, data and state.** Full rationale in the repo-root
`build-state.md` under the 2026-09-01 unit-script entry.

- **The migration finished: every authored unit is a script.**
  `parseUnitScript` in `lib/content.ts` returns `null` unless the file has a
  `::: phase` line, and the unit page throws when it gets `null` — so the
  old fixed renderer path is unreachable. Currently zero units are authored
  on disk (authoring reset); all 56 curriculum modules are planned. When
  authored, every unit is a script carrying six `::: phase` sections each.
  `learn-section.tsx`, `SectionHeading`'s `stepNumber`, `section-nav.tsx`, and
  `SECTION_ANCHORS` are deleted; do not reintroduce them. New units are scripts from birth.
- **The marker vocabulary.** A line starting `::: ` is a marker; everything
  else is markdown and keeps every convention above.
  - `::: phase learn|practice|build|verify|unstuck|ask` opens a landmark
    section and closes the previous one. It emits the same
    `<section id data-keel-section class="scroll-mt-28">` the fixed layout
    emits, because `SECTION_ANCHORS`, every `#learn` style anchor and the
    demo greps key off those ids. `ask` maps to the `concierge` id.
  - `::: <slot>` injects apparatus. The slot names are `route`,
    `worked-example`, `workbench`, `retrieval`, `deliverable`,
    `submission`, `prove-it`, `grading-modes`, `checks`, `rubric`,
    `unstuck`, `ask`. The list lives in `SCRIPT_SLOTS`; the React for each
    one lives in the `slots` record in `app/units/[unitId]/page.tsx`, so
    every data prop stays where the page already fetched it. An unknown
    name warns at parse time and renders nothing, never text.
  - `::: aside <title>` up to a closing `:::` is a collapsible digression
    (`LessonAside`). One job per aside, and the title says what the job is.
  - `::: recap <title>` closes a long beat with its one-line version;
    `::: coda <title>` closes the lesson with a design note. Both render as
    labelled callouts (`Recap` / `Closing`).
- **A script's headings are not shifted.** `##` renders as `h2` under the
  page `h1` and `###` as `h3`, and the apparatus cards bring their own
  `h3`/`h4`. Generated ids are deduped against `SCRIPT_RESERVED_IDS`, so a
  heading called "Practice" becomes `practice-2` rather than colliding with
  the section anchor.
- **Keep three `##` sections in the learn phase.** `last_verified` in
  `unit.yaml` still keys `concept_core` / `applied_context` /
  `tool_specifics`, and `lib/content.ts` maps those to the three sections by
  index. `Checked for accuracy` is emitted automatically at the end of the
  first phase, so an author cannot forget it.
- **Give every other phase exactly one `##` too.** The contents rail lists a
  script's `##` headings across the whole page and nothing else, so a phase
  without one cannot be reached from the rail. Those headings are the only
  navigation the page has, which means they are read far more often than the
  prose under them: write them as beats a student would look for, and keep
  them clear of the unit's `retrieval_seeds` vocabulary. A heading hit counts
  5x in `select_lesson_excerpt`, so a bridge heading that borrows seed words
  will beat the teaching section that actually answers the seed. Re-run the
  selector for all five seeds after adding or renaming one.
- **`:::` lines never reach a judge.** `strip_script_markers` in
  `platform/grading/practice/server.py` filters them inside
  `get_unit_learn_text`, which is the single entry point for retrieval
  grading, recheck and the concierge. Marker lines are page structure, not
  teaching.

# Unit page layout: DECIDED 2026-09-01

A script page is one text column with one contents rail, not a dashboard of
stacked panels. Rationale in the repo-root `build-state.md` under the
2026-09-01 unit-page-layout entry.

- **One grid wraps the whole script**, not one per phase. `UnitScript` emits a
  single `.lesson-layout.unit-script-layout` holding the rail plus
  `#unit-script-body`, and the six phase `<section>`s live inside that body.
  An earlier version gave the rail to the teaching phase alone, which moved the
  reading column 264px sideways at the first phase boundary.
- **The rail is the only in-page navigation on a script page.** Every authored
  unit is a script with `##` headings of its own, so the rail always has
  something to list.
- **`--rail-top` carries the sticky offset.** `.unit-script-layout` sets it to
  88px, which clears the 64px site header on a page with no second bar.
  `.lesson-contents` and `.unit-script h2, h3` both read
  `var(--rail-top, 136px)`, so the fixed layout keeps today's 136px with no
  second rule. `LessonContents` takes a matching `readLine` prop, defaulting to
  150. The `scroll-mt-28` on the phase sections stays as documented above.
- **A phase boundary is a hairline plus 56px**
  (`.unit-script-phase + .unit-script-phase`), against 32px inside a phase.
  The page wrapper adds no `space-y` for a script; the phases own their rhythm.
- **Apparatus fills the grid's content track**, which is 968px rather than the
  1232px shell. Prose and callouts keep their 35em measure, so both start at
  the same left edge. The practice-steps grid and the layer grid are
  `sm:grid-cols-2`; do not widen them past two columns at this measure —
  four-across cards get ~233px each and squeeze real content.
- **Rail labels are decoded, not raw HTML.** `headingText` in `lib/content.ts`
  strips tags and undoes marked's entity escaping for both renderers. Without
  it a heading with an apostrophe prints `&#39;` in the rail.

