# AGENTS.md — keelacademy

How any session — human or AI — picks this project up without losing context.

## Structure is earned, not scheduled

No lesson is required to have a diagram, a recap, a worked-example block, or any other structural element by default. Every block that appears in a lesson must be there because this specific concept needed it — not because the skeleton lists it, not because the last unit had one, and not because a section "usually" goes there. If you can't state in one sentence why a specific block belongs in *this* lesson, cut it. A lesson with three blocks and one without any are both correct outcomes if that's what the material called for. Prose should read like one person explaining something to another person: sections flow into each other, they don't hand off with a label. Meta-scaffolding (navigation footers, accuracy stamps, "show source" toggles) does not belong in lesson prose at all; if the product needs that information, it belongs in `unit.yaml` metadata that the app renders as UI chrome, never as text the student reads as part of the lesson.

When two instructions conflict, this precedence order decides:

1. **Pedagogical soundness** — does the student actually learn the target competency? Always wins.
2. **The lesson voice** — `.agents/skills/shiffman-style-lessons/SKILL.md` and its `references/` (with `docs/voice.md` as its Keel-specific summary). On any voice or structure question, these beat everything below.
3. **Accessibility constraints in `content/STYLE.md`** (reading level, jargon) — real and worth keeping, but satisfied as an *aggregate* property of the whole lesson, never as a mechanical per-sentence rule that overrides voice.
4. **`content/templates/learn.skeleton.md` structure** — a menu of options, never a mandate. Lowest precedence of anything listed here.
5. **Prior-unit cadence** — not an authority at all. Consult prior units for scenario continuity (entity names, currency values, running characters) only, never for structure, block count, or recap placement.

## Read first, in order

1. **[build-state.md](build-state.md)** — where we are; the single next action; the ten most recent decisions (compact by design; full archive in [docs/decisions/](docs/decisions/))
2. **[build-plan.md](build-plan.md)** — how we're building (stages, architecture decisions)
3. **[school-architecture.md](school-architecture.md)** — what we're building (the full design)
4. **[curriculum.md](curriculum.md)** — the source curriculum (reference; do not edit without explicit instruction). Read one unit's slice with `python3 content/tools/curriculum-section.py <unit>` instead of the whole file.
5. **[content/STYLE.md](content/STYLE.md)** and **[docs/voice.md](docs/voice.md)** — the authoring standard and the lesson voice; every contract points at them

## Working rules

- **build-state.md is the source of truth for progress.** At the end of every work session: check off finished milestones, update Status, set exactly one "Next action," append decisions/blockers (dated).
- **Milestones are tiny by design** (hours, not weeks). If one can't finish in a sitting, split it and record the split in build-state.md.
- **Doc ownership:** design changes → `school-architecture.md`; build-approach changes → `build-plan.md`; progress → `build-state.md`. Log any design/approach change in the decisions log. Don't let the docs drift.
- **Content is data; platform is engine.** Lessons, rubrics, fixtures, personas live in the content repo (MDX + YAML, schema-validated). Never bake content into code.
- **Stage gates are real:** don't start a stage before the previous stage's exit criteria (build-plan.md §4) hold. In particular: prove the grading loop (Stage 0) before building UI.
- **Non-goals** are listed in build-plan.md §6. New feature ideas go to the backlog, not the plan.

## Repo layout

```
/curriculum.md            source curriculum (reference)
/school-architecture.md   the design (what + why)
/build-plan.md            the build approach (how)
/build-state.md           live progress (where we are; compact, archive in docs/decisions)
/AGENTS.md                this file
/docs                     specs: lesson-flow-spec, voice; decisions archive (2026-08, 2026-09)
/scripts                  helper scripts (start-docker.sh; provision/ = grading-host provisioning kit)
/.agents/skills           repo skills: shiffman-style-lessons (voice & lesson authoring)
/.agents/agents           Backward Design subagent team: unit_orchestrator (entry point; sequences the five below), ubd_architect, assessment_engineer, rubric_evaluator, pedagogical_author, blind_playtester
/.agents/agents           Content Marketing subagent team: content_orchestrator (entry point; sequences the four below), content_strategist, content_writer, platform_adapter, content_reviewer
/platform                 the code: platform/cli (grading CLI, created at S0.3), platform/grading (grading-core service + Postgres schema, created at S1.1), platform/app (learner app, created at S2.3)
/content                  units, checks, rubrics, prompts, golden sets, faq, personas, curriculum map & ledger, gates, authoring templates, STYLE.md (created at Stage 0)
/content/marketing        brand guide, ideas backlog, and published post batches (articles + platform adaptations)
/scratch                  throwaway trial drafts; never ships, never validated
```
