# Build Plan — keelacademy platform
### How we build to the publish-only state, in dependency order

---

## 0. The one rule

**Content is data; the platform is an engine.** "Done" means: publishing a lesson is a content-repo PR (schema-validated, CI-checked, merge → live) and never a code change. Every build decision below serves that rule. The full design rationale lives in [school-architecture.md](school-architecture.md); this document is only about *how we build it*.

---

## 1. Build the content schema before the platform

The schema is the contract between platform and content. If it's wrong, we either hack special cases into code per unit, or re-author content. Four schemas, versioned from day one, stored as JSON Schema:

**Unit** (`content/units/phase-<N>/<id>/unit.yaml` + `learn.md`):
```yaml
id: "3.2.1"
phase: 3
est_hours: 6
prereq_units: ["2.4.1", "1.5.1"]
last_verified: { concept_core: 2026-08-01, applied_context: 2026-08-01, tool_specifics: 2026-08-01 }
learn: learn.md                       # sections: concept_core / applied_context / tool_specifics
practice:
  worked_example: units/phase-3/3.2.1/worked-example/   # annotated parallel task
  completion_problem: { base: units/phase-3/3.2.1/completion/, checks: checks/3.2.1.completion.yaml }
  retrieval_seeds: [ "why schema-constrained output beats prompt-promise JSON", "..." ]
build:
  deliverable: "<verbatim from curriculum.md>"
  submission: repo                    # repo | file | recording
  data_variant: omnicart@v3
verify:
  layers: [1, 2, 3]                   # which verification layers apply
  deterministic_checks: checks/3.2.1.build.yaml
  rubric: rubrics/3.2.1/v1.yaml
gate: { unlocks: ["3.2.2"] }
unstuck:
  - { symptom: "Pydantic nested-model validation fails", fix_ref: faq/3.2.1.md#nested-validation }
```

**Rubric** (`content/rubrics/<id>/vN.yaml`, e.g. `content/rubrics/3.2.1/v1.yaml`):
```yaml
id: rubric-3.2.1
version: 4
pass_rule: all                        # all criteria must pass
judge: { prompt: prompts/judge-3.2.1.md, model_tier: mid }
golden_set: golden/3.2.1/             # 15–30 pre-graded submissions; private, rotated
criteria:
  - id: valid-schema
    description: "All 20 outputs parse as valid DisputeExtraction; failures logged, not dropped"
    evidence: "quote the log line or code path"
```

**Data variant** (`data_variant: omnicart@v3`, a versioned string; schema at `content/schemas/variant.schema.json`): generator script + parameter ranges; per-student seed = `hash(student_id, unit_id)`, so every student's corpus differs but is reproducible.

**Persona** (`content/personas/*.yaml`): grounding refs, rubric ref, scoring config for the §6 simulation engine.

Everything above is validated in CI on every content PR. Rubrics are content: they change via PR, and the golden-set regression gate runs on rubric PRs.

---

## 2. Architecture decisions — make once, expensive to change

1. **Event-driven core.** Everything meaningful is an event (`unit.started`, `submission.created`, `verdict.issued`, `gate.passed`, `drill.completed`). Gates, digests, rebate triggers, and analytics are subscribers. Adding a feature later = adding a subscriber, not a refactor.
2. **The sandbox is a security boundary.** Untrusted student code runs in isolated containers: no outbound network except an allowlist, hard CPU/memory/time caps, ephemeral filesystems. Student code's LLM access goes through the platform's proxy with per-student budgets — solves the security and the cost problem in one mechanism.
3. **All AI behind one abstraction.** Judges, concierge, simulations, question generation call a provider-agnostic LLM layer with versioned, fully-traced prompts (prompt, response, tokens, cost, latency — the platform dogfoods curriculum 2.4.2 and Phase 7 on itself).
4. **Grading is an idempotent pipeline.** LLM calls fail mid-run; jobs are queued, retryable, with exactly-once verdict semantics. A crashed worker never produces a double verdict or a lost submission.
5. **Server-side trust boundaries.** The concierge teach/guard mode switch is derived from page context on the server — never a client-side hint a student can strip.

---

## 3. Stack & buy-vs-build

**Build (the moat):** grading engine · practice engine · sandbox runner · gate engine · simulation service · unit-page renderer.

**Buy/configure (commodity):** auth (Clerk or Supabase Auth) · billing (Stripe; rebate = state machine on gate events) · analytics (PostHog) · community (Discord for the pilot — §9 says community *integration*, not community platform).

**Recommended stack:** Next.js + TypeScript (learner app) · Python/FastAPI (grading, practice, simulation services — same language as student code and the AI ecosystem) · Postgres (system of record, incl. event log — sufficient at this scale) · a simple queue (pg-boss / RQ / SQS). Content store: git repo, MDX + YAML, schema-validated in CI. No CMS build.

---

## 4. Build stages

Milestones (S0.1, S0.2, …) are tracked in [build-state.md](build-state.md). Exit criteria here are the stage gates; do not start a stage before the previous one's exit criteria hold.

### Stage 0 — Schema + walking skeleton (no UI)
Validate the hardest, no-precedented part first: the grading loop. One golden-path unit (3.2.1 — exercises deterministic *and* judged layers), driven end-to-end by CLI scripts.
**Exit:** submit a real, messy repo → tests run sandboxed → rubric verdict with evidence quotes → defend-your-work questions generated — all unattended. Judge agrees with human grades on ≥90% of the golden set. Adversarial submissions (AI-written, copied, rushed) are caught ≥4 of 5.

### Stage 1 — Grading core service
Postgres schema, GitHub OAuth + webhook intake, queue + idempotent workers, sandbox runner, LLM proxy with budgets, rubric versioning with CI golden-set regression gate, full trace logging.
**Exit:** a git push produces a verdict with zero human involvement; a rubric change that degrades golden-set accuracy blocks its own merge.

### Stage 2 — Content pipeline + learner UI MVP
Content repo + schema-validation CI + per-unit dry-run on content PRs; unit-page renderer (Learn/Practice/Build/Verify/Unstuck); submission flow and verdict display; auth; Stripe + rebate state machine; gate engine consuming verdict events; progress dashboard v1 (the growing OmniCart map).
**Exit:** a test student can sign up, pay, and complete unit 3.2.1 end to end.

### Stage 3 — Practice engine + concierge
Completion-problem grading (reuses Layer 1), retrieval-question generation + grading, spaced re-check scheduler, adaptive routing, dual-mode concierge (server-side mode switch).
**Exit:** a failed drill routes through worked example → completion problem → retry; concierge teach/guard behavior verified by test prompts in CI.

### Stage 4 — Community, simulations, retention, analytics
Pod tooling + weekly digest, gallery v1, simulation service (discovery-call + two skeptical-reviewer personas, scored transcripts feeding gates), per-unit drop-off dashboard, commitment screen + placement diagnostic live.
**Exit:** pilot-ready for the Phases 0–3 cohort (matches §13 of the architecture).

### Content production track (parallel after Stage 2)
Lessons are authored in batches against the same schema and CI — pilot batch = Phases 0–3, then 4–5, 6–7, 8–10, then 11 simulation content. This track is the *only* work remaining once the platform-done checklist below holds.

---

## 5. Platform-done checklist (the publish-only state)

1. Adding a unit = a content-repo PR only — schema-validated, unit checks dry-run in CI.
2. A real submission flows through all applicable layers to a verdict with zero human touch.
3. A rubric edit triggers golden-set regression in CI and blocks merge on degradation.
4. Untrusted code runs sandboxed, capped, with proxied budget-limited LLM access.
5. Gate events drive unlocks, digests, and rebates with no manual work.
6. Per-unit drop-off analytics visible without an engineer writing queries.

---

## 6. Non-goals (for the build phase)

No video infrastructure. No custom CMS. No mobile app. No real-time sync or live-class tooling. No marketplace of any kind. If a feature idea isn't on the path to the checklist above, it goes to the backlog, not the plan.

---

## 7. Surviving session switches

- [build-state.md](build-state.md) is the single source of truth for progress: current milestone, exactly one next action, decisions log, blockers. Read it first; update it last.
- [AGENTS.md](AGENTS.md) holds the resume protocol and doc-ownership rules for any session — human or AI.
- Design changes → `school-architecture.md` (+ a decisions-log entry). Build-approach changes → this file. Progress → `build-state.md`. Never let the three drift.
