---
name: shiffman-style-lessons
description: Write or rewrite programming lessons, tutorials, lecture scripts, or exercise walkthroughs in the teaching voice of Daniel Shiffman (The Coding Train, NYU ITP) — live-build narration, visibly working through bugs, playful/human examples, and warm curiosity instead of flat textbook exposition. Use this whenever the user asks for lesson or curriculum content "like Daniel Shiffman," "like The Coding Train," in a "fun/playful/energetic/enthusiastic" coding-teacher voice, or is building coding-course material (for platforms like Launch School, Codecademy, boot.dev, or any bootcamp/online-school curriculum) that should feel like a real excited instructor rather than generic AI-written documentation. Also use when asked to punch up, humanize, add personality to, or de-flatten existing dry technical lesson content.
---

# Shiffman-Style Lessons

## What this actually is

Daniel Shiffman teaches by building things live on screen and narrating his thinking as he goes — including the wrong turns. That's the whole engine of the style: nothing is presented as a finished, pre-solved artifact. The learner watches a real (if performed) thought process, gets asked to predict what will happen before finding out, and sees mistakes treated as the interesting part rather than an embarrassment to edit out.

None of that is unique to video. It translates directly into written lessons — it just changes _how_ you deliver it (narrated code-in-progress instead of narrated screen-share). That's what this skill produces.

This is a voice and structure, not an impression. The goal is a lesson that could plausibly have been written by an instructor with this teaching philosophy — not a caricature doing a bit. Skip anything below that starts to feel like parody rather than pedagogy.

## The principles doing the actual work

Everything else in this file is downstream of these five things. If you're ever unsure how to handle a new topic, come back to these rather than the phrase lists.

1. **Build in front of the reader — don't hand them the finished answer.** A flat lesson presents correct code and then explains it. This style writes code incrementally, the way you'd actually arrive at it, thinking out loud between each piece. The reader gets a process, not a monument.

2. **Let the bug happen, and treat it as content.** Instead of skipping straight to the correct solution, show a reasonable first attempt, run into what breaks, and investigate it in the open ("okay, that's not what I expected — let's look at why"). The debugging _is_ the lesson, not an interruption of it. This also does real pedagogical work: it shows learners what going wrong actually looks like, which is what they'll experience on their own.

3. **Ask before you tell.** Before revealing what code does, invite a guess: what do you think this will print? What happens if `i` starts at 1 instead of 0? This works just as well written as spoken — pose the question, leave a beat (a short paragraph or even just a line break), then answer it.

4. **Make the example alive, not sterile.** Reach for domains with some visual or physical intuition, movement, or personality — things that wander, grow, bounce, flock, or misbehave — over inert stand-ins like `foo`, `Employee`, or `widget`. This isn't only for graphics topics: a stack can be "grumpy" and only let you deal with what's on top; an array traversal can be a conga line. The point is that the example should be a little bit fun to think about, independent of the concept it's teaching.

5. **Confusion is the default, and you say so out loud.** Never write as though the concept is obviously easy. Name the confusing part before the reader hits it ("this next bit trips people up, and honestly it tripped me up too"). Warmth here isn't decoration — it's what keeps a stuck reader from concluding they're the problem.

A sixth thing that isn't a "principle" so much as a closing habit: **lessons end with an invitation, not a summary.** Instead of a bullet-point recap, pose an open-ended extension — "now try making the ball bounce off all four walls instead of just the top" — and hand the reader back their curiosity rather than a tidy bow.

## The shape of a lesson

Use this as the default skeleton. Not every lesson needs every beat, and topics that are more conceptual than code-heavy (say, explaining Big O) can compress the middle — but the arc (question → attempt → snag → insight → invitation) holds up almost everywhere.

1. **Open with a concrete question or a small promise**, not a definition. Not "Recursion is when a function calls itself," but something closer to: here's a weird problem (nested folders, a countdown, a fractal shape) — watch what happens when we let a function call itself to solve it.
2. **Sketch the naive plan out loud** before writing code — what are we trying to do, in plain words, before it's syntax.
3. **Build it in small increments**, narrating each addition. Short code chunks (a handful of lines) followed by a sentence or two of reaction/explanation — never one long code block dropped with a paragraph after it.
4. **Hit a snag**, real or deliberately staged — a wrong output, an off-by-one, an infinite loop, an unexpected `undefined`. Notice it the way you'd notice it live: "huh, wait, that's not right." Investigate before fixing.
5. **Fix it, and say what you learned**, not just that it now works. The insight is the point; the passing test is a side effect.
6. **Zoom out briefly** — one short paragraph connecting this small example to the bigger idea it's teaching, so the reader isn't left thinking this only works for the toy case.
7. **Close with a challenge**, phrased as an invitation to mess with it: change this constant, add this feature, break it on purpose and see what happens. See `references/voice-guide.md` for phrasing patterns.

## Voice mechanics

- **Short, declarative sentences while thinking, longer ones while explaining why.** The "in-the-moment" narration reads choppy and immediate; the "here's why that matters" beats can breathe more.
- **First person, present tense, for the build itself:** "I'll make a variable called `speed`" rather than "A variable called `speed` is created." The reader should feel like they're watching something happen, not reading a report of something that already happened.
- **"Let's" and "we" over "you should."** This is a collaborator's voice, not an instructor issuing directives from above.
- **Real reactions to output, sized to the moment.** A small, genuine "okay, nice, that works" after something clicks; a genuine "wait, what?" when something's off. Use sparingly enough that they still mean something — if every line gets an exclamation point, none of them land.
- **One brief, real self-deprecating or human aside per lesson, at most.** A joke about not being a math person, an aside about a pet, a "this took me way too long to figure out the first time I tried it." One is texture; three is shtick. It should feel like an incidental detail from an actual life, not a warmth injection.
- **Rhetorical and genuine questions, spaced out, not stacked.** One or two well-placed "what do you think happens here?" moments per lesson beat much harder than a question in every paragraph.
- Light signature affirmations ("nice," "there we go," "okay, cool") are fine as occasional punctuation after something works — never as filler, and never forced into every section.

See `references/voice-guide.md` for a fuller phrase bank organized by function (predicting, reacting, transitioning, inviting experimentation, closing), plus a do/don't table pulled from common AI-flavored tells this style should specifically avoid.

## What kills the voice

These are the tells that make AI-written "playful" content read as performing enthusiasm rather than having it:

- Presenting only correct, final code — no visible attempt, no visible bug.
- Corporate transition phrases: "Now that we've covered X, let's move on to Y," "In today's lesson, we will explore..."
- A neat bulleted recap at the end of every section. This style is more narrative and meandering; save real bullets for reference material, not for lesson prose.
- Enthusiasm with nothing behind it — exclamation points on sentences that aren't actually surprising or delightful. Reserve the energy for moments that earn it.
- Hedging everything ("it's worth noting that," "generally speaking") instead of taking a position on what to do and why.
- Generic filler examples (`foo`, `bar`, `data1`, `Widget`) where a livelier stand-in would cost nothing.
- Explaining a concept as though it's self-evidently simple. If a concept is genuinely confusing (closures, recursion, pointers, async), say that plainly before diving in.

## Plain-language rules (non-negotiable)

The audience includes people whose first language is not English. Every lesson must be understandable by a reader with intermediate English (B1-B2 CEFR level, roughly a confident high-school student who learned English as a second language).

1. **Target Flesch-Kincaid Grade Level 8 or below** for lesson prose (excluding code blocks, tables, and Mermaid diagrams). Use `content/tools/lint-lesson.py` to check. Grade 8 means a typical 13-14 year old can follow it.

2. **Sentence ceiling: 20 words.** Most sentences should be 10-15 words. Any sentence over 20 words must be split or simplified. Two short sentences always beat one long one.

3. **Explain, then name.** Introduce every concept with plain words first. Give its formal name second, in parentheses or the next sentence. Never lead with the jargon.
   - No:  "The stakeholder trilemma creates friction."
   - Yes: "These three leaders want different things, and their goals pull against each other. This three-way conflict is called a stakeholder trilemma."

4. **Prefer short, common words.** If a simpler word means the same thing, use the simpler word. See `references/voice-guide.md` for a full substitution table. Some quick examples:
   - "use" not "utilize"
   - "speed" not "velocity"
   - "delay" not "latency"
   - "process" or "system" not "pipeline" (unless literally a software pipeline)
   - "check" or "review" not "audit" (unless it literally is a financial audit)
   - "a record nobody can change" not "immutable audit trail" (on first use)
   - "the deadline set by law" not "statutory deadline" (on first use)
   - "being able to prove every step" not "auditability" (on first use)

5. **First use / later use rule.** The first time a domain term appears, give its plain-English definition inline. After that, you may use the short term freely because the reader has the anchor. This applies to terms like HITL, trilemma, integer cents, triage, escalation, routing, SLA, compliance.

6. **Active voice, present tense.** Passive voice makes sentences longer and harder for non-native readers to parse.
   - No:  "The transaction is routed to the specialist queue."
   - Yes: "The system sends the transaction to the specialist queue."

7. **One idea per paragraph.** If a paragraph makes two points, split it. Short paragraphs are easier to read on a phone screen too.

These rules work with the Shiffman voice, not against it. Shiffman's own teaching is already plain-spoken and concrete. These rules make sure the written version stays that way instead of drifting toward academic register.

## Adapting the live-build energy to a written page

Since the actual person teaches on video, the trick is translating "watch me build this in real time" into something that works on a page:

- Break code into small, labeled increments (a few lines at a time) rather than one large final block. Narrate between each piece, the way captions would fall between shots in a screencast.
- When staging a bug on purpose, show the broken snippet clearly, then the output/error it produces, then the narrated investigation, then the fix — as four distinct visible steps, not compressed into "make sure to avoid this mistake."
- Where a video would show something happening live (a shape moving, a value changing), describe the small moment of surprise or motion in a sentence rather than skipping straight to the static end state — give the reader something to picture.
- Predict-then-reveal works well as a short paragraph break: pose the question, then a fresh paragraph (or a "Try guessing before you scroll" aside) with the answer.

## Reference files

- `references/voice-guide.md` — phrase bank by function, plus a do/don't table. Load this when drafting sentence-level prose and you want concrete phrasing options rather than the general principles above.
- `references/worked-examples.md` — two full before/after transformations (a flat AI-style lesson vs. the same topic rewritten in this style) on `for` loops and recursion. Load this when you want a concrete model to calibrate against before writing a new lesson, or when the user wants to see the difference the style makes on their own content.

## Honest limits

This style leans hard on specific, lived detail — a particular bug encountered while prepping the lesson, a specific aside about an actual class or actual dog. An AI generating this voice will reach for plausible-sounding versions of that detail rather than true ones. That's fine for illustrative asides in draft content, but:

- Don't invent specific claims presented as fact (a particular version number, a particular studio or student anecdote) unless the user supplied it or you've verified it.
- Voice consistency drifts over a long course the same way any AI writing does — a lesson-by-lesson pass, or at least periodic re-reading against `references/voice-guide.md`, will catch drift better than trusting one long generation.
- The most human-reading result still comes from a hybrid workflow: draft in this style, then have someone who actually knows the material swap in one or two real specifics (an actual bug they hit, an actual thing a real student asked) in place of the invented ones. That single substitution usually does more for authenticity than any prompt tuning.

## Diagrams in written lessons

A figure earns its place only if a reader can take it in faster than the paragraph it replaces. Keep it small and readable on a phone: at most 6 boxes, `flowchart TD`, label lines of 5 words or fewer broken with `<br/>`, the box title in bold on its own line, no dashes or exclamation marks in labels, and a one line caption in the fence info string. Never draw a process the prose is about to walk through step by step; draw the shape of a tension (three people pulling one way each) or a fork (clean case vs hard case). `platform/app/scripts/check-mermaid.mjs` enforces the size rules.
