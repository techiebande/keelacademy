# Lesson voice — the single definition

Lesson voice = Shiffman mechanics + the plain-language standard + the Keel copy
bans. Any contract, skill, or prompt that says "the lesson voice" means exactly
this file. The plain-language and copy rules themselves live in
`content/STYLE.md` and are not repeated here.

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

Every sentence of lesson prose obeys `content/STYLE.md`: Flesch-Kincaid Grade
8 or below, 20-word sentence ceiling, explain-then-name, short common words
(first-use substitution table in the skill's voice guide), inline definitions,
active voice, one idea per paragraph.

## Keel copy bans

Zero em dashes, zero en dashes, zero exclamation marks, zero corporate
buzzwords anywhere in lesson prose, diagram labels, headings, and codas. The
strict gate (`content/tools/lint-lesson.py <learn.md> --strict`) exits 1 on
any breach.

## What the voice is not

- No lecture-formality, no academic hedging, no corporate polish.
- No unearned enthusiasm; energy is spent only where something surprising
  happens.
- No "Predict, then check" blockquotes or "Gotcha" beats (owner direction,
  2026-09-06). Pacing comes from asides, recaps, and text blocks.
