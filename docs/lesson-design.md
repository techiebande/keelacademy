# How Keel lessons are made

Ratified 2026-09-12. This replaces the previous lesson system in full: the six-phase unit script, the apparatus block vocabulary, the skeleton templates, the voice skill, STYLE.md and voice.md, the strict linter, the structural fingerprint, the consistency checker, and the six-agent authoring team. None of those are referenced anywhere any more. The reasoning is below; the evidence is in `docs/research/`.

## 1. What went wrong, in one paragraph

Every layer of the old system was a rule about the *shape* of a lesson: six phases in fixed order, a menu of named blocks, a Flesch-Kincaid ceiling, a technology-word ban, a 300-word prose ceiling, a fingerprint check against the last few units, a borrowed teaching persona, and a battery of gates that had to go green before anyone read the result. Prose written to satisfy shape rules converges on the rules and sheds everything the rules cannot measure (`docs/research/03-machine-written-tells.md` §3, Redish, AHRQ, Goodhart). The one unit that survived shows exactly that: one clipped sentence per line, "First ... Second ... Third ... Finally", a question answered in the next breath, a recap of the previous paragraph, retrieval seeds pasted verbatim into the story, and a closing card telling the student the exercise "does not change your score." Nobody writes like that to a person. The fix is not better rules about shape. It is to stop legislating shape, state what a lesson must *do* for a reader, and check the result the way a reader would.

## 2. What a lesson must do (the only rules)

These come straight from the three research briefs. Each rule cites its evidence; anything without evidence did not make the list.

1. **Teach by building the thing in front of the reader, in small explained steps.** A complete, step-by-step explained example is the strongest single intervention for novices (worked-example effect: brief 1 §1; every exemplar writer does it: brief 2 Part B). Show two to twelve lines, say what they do and why, then the next piece. The full listing appears once, at the end, for reference, after every line in it has already been explained.
2. **Put the explanation next to the code it explains.** Never a long listing followed by a distant walkthrough (split-attention, d about 1.1: brief 1 §2).
3. **Show the thing before naming it.** Concrete first, then the term, in the same or the next sentence, and then use that exact word for it forever (pre-training and cohesion: brief 1 §3, §11; "none of the exemplars introduce a term before the reader has seen the thing": brief 2).
4. **Say what the computer actually does when a line runs.** What `=` does, what order things happen in, where a value goes when a function is called (notional machine: brief 1 §5). Never assume the runtime model.
5. **Ask before you show.** Before output appears, ask the reader what they expect. Give them a real pause: a fold they have to open, or at least a paragraph break (prediction: brief 1 §6, §7). Then show it, and if the guess is likely to be wrong, say why it is wrong.
6. **Let a real mistake happen and read the error message together.** The naive version first, the actual error text pasted in, the diagnosis (brief 1 §9; brief 2 "bad version first", "errors quoted verbatim").
7. **One new idea per section. Cut everything that is not load-bearing.** No fun facts, no history unless it explains a design, no decorative diagrams, no second way of doing the same thing in a first lesson (coherence, d about 0.86: brief 1 §3).
8. **Write to one person, as one person.** "You" for the reader, "we" when doing the work together, "I" when it is the author's judgment or experience (personalization: brief 1 §3; brief 2 exemplar counts). Name the confusing part before the reader hits it. No performed reactions, no mascot, no borrowed persona. The author writes as themselves.
9. **Open with the tension, and a promise.** The first hundred words say what is wrong or missing and what the reader will be able to do at the end (McEnerney, Zinsser's lead: brief 2 Part A; "a contract in the first 150 words": brief 2 common patterns).
10. **Connect the sentences, don't chop them.** Old information first, new information last; repeat the plain noun instead of finding synonyms; keep "because", "so", "which means", "but" in (Gopen & Swan, Williams, McNamara & Kintsch: brief 1 §11, brief 2 Part A). Low-knowledge readers learn *more* from highly connected text. Sentence length is a symptom, never a target, and no readability score is ever computed as a gate.
11. **Let the structure follow the material.** Headings state the point of the section. Sections end by naming the thread the next one picks up. There is no fixed count of anything (brief 2 "transitions name an unresolved thread"; brief 3 List 1 #15-16).
12. **End by handing the reader work.** Test it, change it, build the assignment. Never a summary of what was just said, never a moral (brief 2 "endings assign action"; brief 3 #28-29).
13. **Recall is a question, asked later.** Spaced retrieval is the highest-utility review technique (Dunlosky: brief 1 §7). The unit carries recall *questions*; the platform asks them after the lesson and again days later. Facts are never planted in the prose so that a drill can find them.
14. **The assignment is the example, faded.** The student finishes what the chapter built, on the client's data, with the last steps missing first and more missing in later units (backward fading: brief 1 §1). Checks tell the student *which step* is missing, in plain words.
15. **One running client, everyday words.** A story with a goal and obstacles is remembered better than unrelated toy snippets (Willingham: brief 1 §8), but only if the thinking is about the concept, not the theme. The client and every example must be understood by a beginner anywhere in the world with no business or software background. See `content/client/`.

Three things the research explicitly does *not* support, so they are gone: a reading-grade target, summary or recap boxes, and "structural variety" as a goal in itself. Variety is what happens when the material decides the shape.

## 3. The unit, on disk

```
content/units/phase-<N>/<id>/
  unit.yaml          who this is for, hours, what unlocks, recall questions, assignment wiring
  lesson.md          the chapter: plain Markdown, prose and fenced code
  assignment.md      the hand-off: the task, how it is checked, where people get stuck
  starter/           code units only: the faded starting files the student completes
  checks.yaml        code units only: the deterministic checks and their plain-words messages
```

`lesson.md` is plain CommonMark. There are no markers, no phases, no slots, no named blocks. The only construct beyond Markdown is the standard HTML fold, used for exactly two things: a prediction the reader should commit to before looking, and the answer to a self-explanation question:

```html
<details><summary>What do you think it prints?</summary>

It prints `3`, because ...

</details>
```

Fenced code blocks name their language. A block that shows program output uses the `text` fence. A Python block whose output is shown in the following `text` block is *runnable and verified*: `content/tools/run-lesson-code.py` executes every Python block in a lesson in order and compares real output with the shown output. That is the one mechanical gate a lesson passes, because it checks a fact (the code does what the text says it does), not a shape.

`assignment.md` is the same plain Markdown. It is rendered after the chapter under the heading the author gives it. It says what to build, what the checks look for and why, and lists the places people get stuck with the fix for each (its `##` anchors are what `unit.yaml`'s `unstuck` entries point at).

`unit.yaml` is platform wiring; a student never reads it. The keys the grading services already consume keep their names; only their meaning is corrected:

```yaml
kind: code | conceptual
id: "1.1.1"
phase: 1
est_hours: 15
prereq_units: ["0.3"]
learn: lesson.md
assignment: assignment.md
practice:
  retrieval_seeds:            # QUESTIONS the platform asks from memory, later.
    - "What does the = sign do in Python, and why is 'equals' the wrong word for it?"
  completion_problem:         # the faded assignment
    base: starter/            #   code units
    checks: checks.yaml
    # conceptual units instead carry: prompt, instructions, rubric
build:
  deliverable: "..."
  submission: repo | file
  data_variant: lantern@v1
verify:
  layers: [1]
  deterministic_checks: checks.yaml
gate:
  unlocks: ["1.1.2"]
unstuck:
  - symptom: "..."
    fix_ref: assignment.md#<anchor>
```

`practice.worked_example` is gone. The chapter *is* the worked example. There is no parallel entity and no second company.

## 4. How a unit is written

Two roles, in `.agents/agents/`: `lesson_author` and `first_reader`. No orchestrator; the author runs the loop.

1. **Plan (half a page).** From the curriculum slice: what the student can do at the end that they could not do before; the two or three ideas that get them there, in order; which of the client's artifacts the examples use; where the naive attempt breaks and what the error says; what the assignment leaves for the student to finish; four to eight recall questions with reference answers. The plan is a scratch file, not a deliverable.
2. **Write the chapter** against `content/WRITING.md`. Run every code block while writing it; paste real output.
3. **Run `content/tools/run-lesson-code.py`** until every Python block reproduces its shown output. Run `content/tools/validate.py` for the yaml.
4. **First reader.** A second agent (or a person) reads the chapter *as the student described in the plan*, without the plan, and reports: every sentence they had to read twice, every term used before it was shown, every code line they could not say the purpose of, every prediction they got wrong that the text did not address, every place the text talks about the lesson instead of the subject, every passage that sounds assembled rather than written. Findings are quotes with line numbers, never scores.
5. **Revise, re-run step 3, re-read the changed passages.** Ship when the first reader has nothing left that a student would trip on.

`content/tools/tells.py` exists for the first reader's benefit: it prints clustered markers of assembled prose (the watch-list vocabulary, "In this lesson" signposting, one-sentence-per-line formatting, tricolon density, and the like from brief 3) with line numbers. It is advisory and is never a gate, because a gate would be written to.

## 5. What the platform renders

The unit page is: title and hours; the chapter, rendered from `lesson.md` with a contents rail built from its `##` headings; the assignment, rendered from `assignment.md`; then the platform's own apparatus, in this order, each as a card with a one-word label and no bridging copy: the starter and submission for code units (or the writing prompt for conceptual units), the automated checks with their plain-words messages, the rubric where one applies, the recall questions, and the tutor chat. The exit card and resume banner stay; they are product chrome, not lesson prose.

`platform/app/lib/content.ts` parses a lesson as Markdown plus headings. The script grammar (`::: phase`, slots, aside, recap, coda, `> **Gotcha`, `### Checkpoint`) is deleted, not deprecated.

## 6. The client

`content/client/` holds the one fictional business every unit serves, written so that a first-time programmer anywhere can picture every noun in it: an online shop that sells everyday household things, the people who run it, the messages its customers send, its orders and deliveries, and the short rulebook its support team applies. The curriculum's anchor problem is unchanged in substance (customer problems about orders have to be read, checked against records and rules, decided, and answered, fast and auditably), but the vocabulary is now a kettle, a parcel, a photo, and a refund, not a merchant payout dispute and a bill of lading.

## 7. What was removed and why (the record)

| Removed | Why |
|---|---|
| `::: phase` six-phase script, slots, aside/recap/coda, callouts, checkpoints | Shape rules produce shaped prose; exemplars shape each chapter to its material (brief 2). Recap boxes are low-utility review (brief 1 §7). |
| `content/templates/*` skeletons | "Copy the skeleton, fill every slot" is the definition of templated writing (brief 3 §3). |
| `content/STYLE.md`, `docs/voice.md`, `.agents/skills/shiffman-style-lessons`, `.agents/rules/keel-voice.md` | A borrowed persona is a costume; the FK ceiling and sentence rules cut the connectives novices need (brief 1 §11, brief 2 Part A). Replaced by `content/WRITING.md`. |
| `lint-lesson.py --strict`, `structural-fingerprint.py`, `check-unit-consistency.py`, `check-mermaid.mjs` rules for lessons | Every one is a shape gate; each one was written to. The only mechanical check now is that code runs and prints what the text says. |
| Technology-word ban | Hiding the words "software" and "computer" from a person learning to program is theatre. Terms are introduced when the thing is shown, then used plainly. |
| Worked example directory, parallel entity (Apex Freight), completion "README" | The chapter is the worked example; a second company doubled the vocabulary a beginner had to learn for no pedagogical return. |
| Six-agent Backward Design team and its battery | Six contracts, each adding constraints, with no step where anyone read the lesson as a student. Replaced by author + first reader. |
| Retrieval seeds as declarative sentences | They were planted into prose. Seeds are now questions with reference answers. |
| OmniCart Operations, Apex Freight Logistics, their titles and jargon | Not relatable outside one business culture. Replaced by `content/client/`. |
