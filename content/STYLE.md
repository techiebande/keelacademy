# Keel content style: the rules every student-facing word follows

One page. Every agent contract links here instead of repeating it. The linter
`content/tools/lint-lesson.py --strict` is the executable form of this page; if
the two ever disagree, fix the linter and this page together. Lesson voice
(how prose sounds) is defined in `docs/voice.md` and governed by the skill at
`.agents/skills/shiffman-style-lessons/`; where a mechanical rule here would
flatten the voice (sentence rhythm, earned reactions), the skill wins and the
targets below bind in aggregate, per the precedence order in `AGENTS.md`.

## Plain language (non-native English readers, no software background)

1. Flesch-Kincaid Grade 8 or below for lesson prose, measured across the whole lesson. This aggregate score is the binding readability rule.
2. Sentence rhythm varies on purpose: short beats (roughly 10 words or fewer) while narrating action, longer ones (up to about 30) while explaining why. There is no per-sentence cap; the aggregate grade above is what the gate enforces.
3. Explain, then name: say "a record nobody can change" before "audit trail".
4. Prefer short common words. Substitutions live in `.agents/skills/shiffman-style-lessons/references/voice-guide.md`.
5. Define every domain term on first use, inline, in one sentence.
6. Active voice, present tense.
7. One idea per paragraph.

## Copy bans (Keel voice)

- No em dashes, no en dashes. Use commas, colons, periods, or "to" for ranges. Hyphens only inside ids like CLM-20841 and compounds like 120-person.
- No exclamation marks as generic enthusiasm. At most two per lesson, and only on a genuine reaction to something surprising (wait, what!). The strict linter enforces the cap. Diagram labels keep a total ban.
- No corporate buzzwords: leverage, synergy, streamline, unlock, empower, robust, seamless, cutting-edge, revolutionise, supercharge.
- No internal architecture in student copy: no service names, no "Layer 1", no model tiers, no golden set, no calibration.

## Technology words (never in student prose for Phase 0 units; later phases lift them one by one as the ledger unlocks them)

ai, agent(s), llm(s), model(s), prompt(s), automation, automate(d), software, algorithm(s), python, docker, api(s), database(s), json, schema, pipeline, embedding(s), token(s), chatbot, machine learning.

The linter carries this list in `TECH_WORDS`. Change both together.

## Numbers and identifiers

- Money is integer cents: 4520, never 45.20 or $45.20.
- Ids: CLM-#####, ORD-#####, INV-#####, MCH-####, DEL-#####.
- Ranges read "2 to 3 days", never "2-3 days".
- Write "14 day", not "14-day".
- Anchor client is OmniCart Operations. Parallel entity is Apex Freight Logistics.

## Lesson structure (unit scripts)

- Six `::: phase` blocks in order: learn, practice, build, verify, unstuck, ask.
- Learn phase has at least two `##` headings. No maximum. Let the topic decide the count.
- Other phases have one or two `##` headings as the content needs.
- Headings never borrow a retrieval-seed keyword (heading hits weigh 5x in the excerpt selector).
- No prose block over ~300 words without apparatus (aside, recap, fenced block, figure). This is a ceiling, not a slot machine. Do not insert blocks just to reset the counter.
- Apparatus blocks (aside, recap, mermaid, text fence) are optional tools. Use them when they earn their place. A recap earns its place after a genuine topic shift, not after every beat. Never place a recap in the first third of the learn phase.
- Sections lead into each other like continuous writing: each picks up something the previous one left open. No labeled hand-offs between modules.
- No housekeeping text: no diagram-source reveals, no accuracy stamps, no END OF or NEXT phase markers, no stop-here lines. Strict lint errors on all of these. The app renders none of them either (owner direction, 2026-09-10).
- `::: coda <title>` closes the lesson with an invitation, never a summary.
- No `> **Predict, then check.**` or `> **Gotcha:**` blockquotes. Ask before tell happens in prose.
- Post-learn phases (practice, build, verify, unstuck, ask) must be written fresh per unit. Do not reuse sentence structures from other units.

## Diagrams

Include a figure only when a spatial relationship or flow is genuinely hard to say in words; most lessons teach better in prose. When a figure does earn its place: at most 6 nodes, `flowchart TD`, label lines of 5 words or 28 characters, break with `<br/>`, bold title line, caption in the fence info string. `platform/app/scripts/check-mermaid.mjs` enforces this.

## Verification

`content/tools/check-unit-consistency.py <unit>` is the cross-file agreement
gate. Every authoring handoff pastes the output of the checks it claims to
pass; no pasted output, no acceptance.
