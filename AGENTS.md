# AGENTS.md: keelacademy

How any session, human or AI, picks this project up without losing context.

## Lessons are written, not assembled

A Keel lesson is a chapter one knowledgeable person wrote for one beginner. It is plain Markdown. There is no template, no required section, no block vocabulary, no reading-grade target, no word ban, and no linter that judges prose. What a chapter must *do* for its reader is in `docs/lesson-design.md` (fifteen rules, each with its evidence); how to write one is `content/WRITING.md`. The single mechanical gate a lesson passes is `content/tools/run-lesson-code.py`: every code block on the page must run and print what the page says it prints.

If you are about to add a rule about the shape of a lesson (a heading count, a block that must appear, a sentence-length cap, a phrase list), stop. That is the system this one replaced, and `docs/lesson-design.md` §1 and §7 record why. Prose written to satisfy shape rules converges on the rules.

## Read first, in order

1. **[build-state.md](build-state.md)**: where we are; the single next action; the most recent decisions (archive in `docs/decisions/`).
2. **[docs/lesson-design.md](docs/lesson-design.md)**: what a lesson is and why, how a unit sits on disk and on the page, how a unit gets written.
3. **[content/WRITING.md](content/WRITING.md)**: the writing guide. Read it before writing or reviewing any student-facing word.
4. **[content/client/brief.md](content/client/brief.md)**: Lantern Home, the one client every unit serves. Every example uses these people and these files.
5. **[build-plan.md](build-plan.md)** and **[school-architecture.md](school-architecture.md)**: how we build and what we are building.
6. **[curriculum.md](curriculum.md)**: the syllabus. Read one unit's slice with `python3 content/tools/curriculum-section.py <unit>`.

## Working rules

- **build-state.md is the source of truth for progress.** At the end of every session: update Status, set exactly one Next action, append dated decisions.
- **Content is data; platform is engine.** Lessons, assignments, checks, rubrics and the client's files live under `content/`; the app and grading services render and grade them. Never bake content into code.
- **Authoring a unit** is `.agents/agents/lesson_author/agent.md` (writes) plus `.agents/agents/first_reader/agent.md` (reads cold, reports where a student would stop). There is no orchestrator. The author runs the loop and pastes the checker output and the reader's report in the handoff.
- **Every code block is real.** Run it, paste what it printed, and let `run-lesson-code.py` prove it. A traceback on the page is a real traceback.
- **The client is fixed.** New facts about Lantern go into `content/client/` first, in the same plain words, then into a lesson. No second company, no parallel entity.
- **Stage gates are real** (build-plan.md §4). Non-goals are in build-plan.md §6.

## Repo layout

```
/curriculum.md            the syllabus (topics and order)
/school-architecture.md   the design (what + why)
/build-plan.md            the build approach (how)
/build-state.md           live progress (compact; archive in docs/decisions)
/AGENTS.md                this file
/docs                     lesson-design.md, research/ (the three evidence briefs), lesson-flow-spec.md, decisions/
/content/WRITING.md       how to write a lesson
/content/client           Lantern Home: brief, rulebook, messages, orders, deliveries
/content/units            phase-<N>/<id>/{unit.yaml, lesson.md, assignment.md, starter/, checks.yaml}
/content/rubrics, prompts, golden   Layer 2 grading for conceptual units
/content/tools            run-lesson-code.py (the gate), tells.py (advisory), validate*.py (schemas)
/.agents/agents           lesson_author, first_reader; the Content Marketing team (content_orchestrator and its four)
/platform                 platform/cli (grading CLI), platform/grading (services), platform/app (learner app)
/scratch                  throwaway drafts and unit plans; never ships
```
