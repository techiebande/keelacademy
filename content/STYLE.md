# Keel content style: the rules every student-facing word follows

One page. Every agent contract links here instead of repeating it. The linter
`content/tools/lint-lesson.py --strict` is the executable form of this page; if
the two ever disagree, fix the linter and this page together. Lesson voice
(how prose sounds) is defined in `docs/voice.md`.

## Plain language (non-native English readers, no software background)

1. Flesch-Kincaid Grade 8 or below for lesson prose.
2. Sentence ceiling 20 words. Most sentences 10 to 15.
3. Explain, then name: say "a record nobody can change" before "audit trail".
4. Prefer short common words. Substitutions live in `.agents/skills/shiffman-style-lessons/references/voice-guide.md`.
5. Define every domain term on first use, inline, in one sentence.
6. Active voice, present tense.
7. One idea per paragraph.

## Copy bans (Keel voice)

- No em dashes, no en dashes. Use commas, colons, periods, or "to" for ranges. Hyphens only inside ids like CLM-20841 and compounds like 120-person.
- No exclamation marks.
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
- Learn phase has exactly three `##` headings; every other phase exactly one.
- Headings never borrow a retrieval-seed keyword (heading hits weigh 5x in the excerpt selector).
- No prose block over 250 words without apparatus (aside, recap, fenced block, figure).
- `::: coda <title>` closes the lesson with an invitation, never a summary.
- Unit 0.1 direction: no `> **Predict, then check.**` or `> **Gotcha:**` blockquotes. Ask before tell happens in prose.

## Diagrams

At most 6 nodes, `flowchart TD`, label lines of 5 words or 28 characters, break with `<br/>`, bold title line, caption in the fence info string. `platform/app/scripts/check-mermaid.mjs` enforces this.

## Verification

`content/tools/check-unit-consistency.py <unit>` is the cross-file agreement
gate. Every authoring handoff pastes the output of the checks it claims to
pass; no pasted output, no acceptance.
