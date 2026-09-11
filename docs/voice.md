# Lesson voice — the single definition

Lesson voice = Shiffman mechanics + the plain-language standard + the Keel copy
bans. Any contract, skill, or prompt that says "the lesson voice" means exactly
this file. The plain-language and copy rules themselves live in
`content/STYLE.md` and are not repeated here.

Precedence (full order in `AGENTS.md`): on voice and structure questions, the
skill at `.agents/skills/shiffman-style-lessons/SKILL.md` and its
`references/` are the authority, and this file is their Keel-specific summary.
Where this file and the skill differ, the skill governs. STYLE.md's
accessibility targets bind in aggregate, never as a per-sentence override of
voice.

Full style guide with worked examples:
`.agents/skills/shiffman-style-lessons/SKILL.md` and its `references/`.

## Shiffman mechanics

1. **Build in front of the reader.** Write models and code incrementally,
   thinking out loud between pieces. Never drop a finished block and explain
   it after.
2. **Visible bugs as content.** Show a reasonable first attempt, let it break,
   investigate in the open (okay, that is not what I expected, let us look at
   why).
3. **Ask before you tell.** Invite a guess before revealing output or
   behavior. Paragraph breaks do the pausing.
4. **Alive, concrete entities.** Real OmniCart entities (ORD-8821, CLM-20841,
   unboxing photos, courier delivery slips), never sterile placeholders.
5. **Honest confusion.** Normalize difficulty (this part trips people up, and
   honestly it tripped me up too).
6. **Collaborative energy.** We and let us over you should. Sparse, earned
   reactions (okay, nice, wait, what?).
7. **Open invitation closing.** End with an invitation to experiment, never a
   bullet-point summary.

## Plain-language layer

Lesson prose obeys `content/STYLE.md` in aggregate: Flesch-Kincaid Grade 8 or
below across the whole lesson, explain-then-name, short common words
(first-use substitution table in the skill's voice guide), inline definitions,
active voice, one idea per paragraph. Sentence rhythm is a voice tool, not a
rule: short beats while narrating, longer ones while explaining why.

## Keel copy bans

Zero em dashes, zero en dashes, zero corporate buzzwords anywhere in lesson
prose, diagram labels, headings, and codas. Exclamation marks: none as generic
enthusiasm, at most two per lesson, and only on a genuine reaction to
something surprising. The strict gate (`content/tools/lint-lesson.py <learn.md> --strict`) exits 1 on
any breach.

## What the voice is not

- No lecture-formality, no academic hedging, no corporate polish.
- No unearned enthusiasm; energy is spent only where something surprising
  happens.
- No "Predict, then check" blockquotes or "Gotcha" beats (owner direction,
  2026-09-06). Pacing comes from asides, recaps, and text blocks.

## Structural variety

A consistent voice does not mean a repetitive structure. Each lesson finds
its own shape based on what it teaches. Two consecutive lessons should not
share the same heading count, the same block sequence, or the same post-learn
phrasing. The voice stays the same. The form moves. A section also leads into
the next the way continuous writing does: it picks up something the previous
section left open, rather than announcing a hand-off.

Apparatus blocks (aside, recap, diagram, text fence) are tools, not
obligations. Use a recap after a genuine topic shift. Use a diagram when
spatial relationships are hard to say in words. Use an aside when a side point
would break the main flow. If the lesson flows without any of these, leave
them out.

## No housekeeping text

Do not write "Show diagram source." Do not write accuracy timestamps like
"Checked for accuracy 2026-09-07." Do not write navigation markers like
"END OF LEARN" or "NEXT: PRACTICE." Transitions between phases should feel
like a natural next step, not a signpost.
