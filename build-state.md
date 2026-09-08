# Build State — keelacademy platform

**Last updated:** 2026-09-07
**Stage:** Content Production Track
**Status:** Unit 0.2 ('How the curriculum and grading loop work') authored and green under the plain-language standard (FK lint 0 advisories, strict lint PASS, consistency gate PASS, all 9 battery items green). Ledger now has units [0.1, 0.2]. Judge calibration for Unit 0.1 still not run live (needs OPENAI_API_KEY).

> ## Resume protocol — read this first
> 1. Read this file, then skim build-plan.md §4 for the current stage's exit criteria.
> 2. Work the single **Next action** below. Nothing else.
> 3. At session end: check off finished milestones, update Status/Next action, append any decisions or blockers (dated). Milestones are tiny by design — if one can't finish in a sitting, split it and record the split here.

## Next action
Verify Unit 0.1 live: run the judge calibration on `content/golden/0.1/` (8 submissions after M5.2, needs OPENAI_API_KEY; expect 8/8 overall and 40/40 criteria) and open the rendered unit page; fix anything found. Then author Unit 0.3 via `unit_orchestrator`.

---

## Stage 0 — Schema + walking skeleton (no UI)
*Exit: grading loop works end-to-end via CLI on real messy submissions; judge ≥90% agreement with human grades on golden set; adversarial submissions caught ≥4/5.*

- [x] S0.1 Four content schemas written as JSON Schema (unit, rubric, data-variant, persona) — accepted on review 2026-08-21; validator output confirms 4 valid + 1 expected-invalid
- [x] S0.2 Golden-path unit 3.2.1 authored in full: lesson (3 layers), worked example, completion problem + checks, retrieval seeds, rubric v1, 15 pre-graded golden submissions — accepted on execution-verified review 2026-08-21
- [x] S0.3 CLI: point at a repo → run its pytest in Docker → parse per-test results. *Done when: a fixture repo with one failing test prints which test failed* — accepted on execution-verified review 2026-08-21 (fixture names the failing nodeid; completion base fails naming the 5 gap tests; filled copy passes 3/3 after the no-gap-markers scoping fix; faq/3.2.1.md stub added)
- [x] S0.4 CLI: rubric judge → structured verdict (pass/fail per criterion + quoted evidence). *Done when: verdict JSON validates against its schema and quotes submission text* — accepted on execution-verified review 2026-08-21 (s01 pass / s07 fail / s12 fail, matching human grades; reviewer's independent judge runs agreed criterion-for-criterion)
- [x] S0.5 CLI: defend-your-work — generate 2–3 follow-up questions from a submission's actual code. *Done when: questions reference specifics of the submitted code, not generics* — accepted on execution-verified review 2026-08-21 (s01 vs s12 question sets differ on their distinctive design choices; all 13+13 anchors grep-verified present and referenced; reviewer's independent runs reproduced equivalent question sets; judge refactor regression-tested PASS exit 0)
- [x] S0.6 Judge calibration: run judge over the 15 golden submissions, compare to human grades, record agreement % — accepted on execution-verified review 2026-08-21 (worker and reviewer runs identical: 14/15 overall = 93.3%; criterion agreement 72/75 = 96.0% after the reviewer corrected two reference bugs (s09 conservation, s10 failures-logged); borderline semantics ratified: compare against the resolved binary overall)
- [x] S0.7 Adversarial pass: 5 gamed submissions (AI-written, copied, rushed) — record how many the pipeline catches. Includes the judge-blind-spot fix package calibration exposed — accepted on execution-verified review 2026-08-22 (calibration after fixes: 15/15 overall and 75/75 criterion in both worker and reviewer runs; all 5 attacks caught — prompt injection, rubric parroting, test gaming, dead-code decoy all failed at L2, verbatim copy correctly passed L2 and caught by L3 defend questions). **STAGE 0 EXIT GATE MET.**

## Stage 1 — Grading core service
*Exit: git push → verdict, zero human involvement; rubric change that degrades golden-set accuracy blocks merge.*

- [x] S1.1 Postgres schema: events, submissions, verdicts, students, progress — accepted on execution-verified review 2026-08-22 (reviewer's own smoke run: schema applied to scratch postgres:16-alpine, all 6 checks PASS including both expected constraint violations quoted verbatim; container auto-removed; no leftover containers)
- [x] S1.2 GitHub OAuth + webhook intake (push → submission.created event) — accepted on execution-verified review 2026-08-22 (OAuth half formally deferred to S2.5 managed auth; reviewer's own smoke-intake run: 5/5 checks PASS, exit 0, tampered payload rejected 401 with zero DB writes, no leftover containers/processes)
- [x] S1.3 Job queue + worker; idempotent, exactly-once verdict writes. *Done when: killing the worker mid-grade and retrying produces exactly one verdict* — accepted on execution-verified review 2026-08-22 (reviewer's own run: 4/4 checks PASS incl. SIGKILL mid-grade intermediate state grading/0 verdicts and recovery; both regression suites green after shared-db.py refactor)
- [x] S1.4 Sandbox runner: Docker, network allowlist only, CPU/mem/time caps, ephemeral FS. *Done when: a fixture submission that tries to phone home / fork-bomb is contained and reported* — built + self-proven 2026-08-22 (smoke-sandbox.sh 7/7 PASS exit 0: phone-home denied [Errno 101] with status ok, fork bomb contained by pids-limit→wall-cap timeout at 63 spawns, sleep-forever timeout at the cap, fs-escape blocked EROFS with host dir untouched, mem-hog OOMKilled=true, zero leftover containers) — ACCEPTED on execution-verified review 2026-08-22 (reviewer's own smoke-sandbox run: 7/7 PASS — phone-home denied [Errno 101] with status ok, fork bomb held at 63 spawns by pids-limit then wall-cap timeout, sleep-forever timeout at the cap, fs-escape EROFS with host dir byte-identical before/after, mem-hog OOMKilled=true, zero leftover containers; infra path exit 2 with no JSON on stdout; worker regression 4/4 green; reviewer removed stale __pycache__ dirs from the fixture submission dirs)
- [x] S1.5 LLM proxy with per-student budgets. *Done when: student code exceeding budget is cut off and flagged* — ACCEPTED on execution-verified review 2026-08-22 (reviewer's own runs: deterministic 5/5 PASS with /__count proving zero forwarding on cut-off, and gated LIVE check (f) PASS — one real gpt-4o-mini call through the proxy, used 300→315; worker/sandbox/intake regressions all green; worker touched no protected docs)
- [x] S1.6 Rubric versioning + CI golden-set regression gate on rubric PRs — ACCEPTED on execution-verified review 2026-08-22 (reviewer's own runs: validator green; positive gate 15/15 + 75/75 exit 0; calibrate regression 15/15 + 75/75 exit 0 with the new rate-limit transient marker retrying 3 live 429s; negative probe A (S0.7 rollback across rubric + judge prompt) 12/15 + 69/75 -> gate FAIL exit 1; negative probe B (rubric-only pass-everything criteria) 6/15 + 51/75 -> gate FAIL exit 1; resolver proven incl. numeric ordering and error paths after a reviewer-fixed REPO_ROOT off-by-one; temp degraded rubric deleted, prompt restored byte-identical)
- [x] S1.7 Trace logging on every grading call (prompt, response, tokens, cost, latency) — ACCEPTED on execution-verified review 2026-08-22 (reviewer's own runs: judge s01 record carried every required field incl. full prompt + raw response (tokens 2527/303, cost $0.007478, verdict pass); retry numbering proven as a cumulative ordinal advanced by BOTH the JSON-nudge and transient-retry loops — offline urlopen proof attempts [1,2,3], reset per logical call via begin_trace_call; KEEL_TRACE_LOG env-configurable with ~/.keelacademy-traces.jsonl default and 'off' kill-switch; unwritable trace path printed one [trace] warning and the judge still exited 0 with OVERALL: PASS; key-leak sweep over all trace files and the repo diff: 0 occurrences; calibrate/gate single-submission smokes green with caller tags preserved; reviewer hygiene sweep removed the stale S0-era review/temp scripts left at the repo root)
- [x] S1.8 Wiring milestone: proxy + sandbox + judge produce real verdicts in worker.py (kill-safe, budget-enforced, resolver-driven, trace-linked). *Done when: an intake submission reaches a real VERDICT row via Layer-1 sandbox checks + Layer-2 judge through the proxy* — built + proven 2026-08-22 (reviewer-verified: deterministic 4/4 PASS incl. SIGKILL-mid-judge recovery and 429 no-forward path; LIVE one real gpt-4.1 judge call through the real proxy PASS; S1.3/S1.4/S1.5 regressions green) — REJECTED on the layer1 staging-debris leak; fix ACCEPTED 2026-08-22 (reviewer-reproduced the exact root-owned failure mode: host rm Permission denied, cleanup_staging's container fallback removed it, stubbed-docker path printed the loud warning; direct-grade debris count 0=0; wiring 4/4 + worker/sandbox/proxy regressions green) — S1.8 COMPLETE
- [x] S1.9 Stage 1 exit gate: git push produces a verdict with zero human involvement; rubric regression blocks its merge. — ACCEPTED 2026-08-22 on reviewer-executed proof (reviewer performed the only git push: verdict in ~15s with rubric v1, layer-1 8p/0f, real gpt-4.1 judge via proxy, worker-tagged trace, budget charged; idempotent re-pushes kept 1/1/1; probe-B degraded rubric made the exact workflow gate command exit 1 at 6/15 + 51/75, restore byte-identical). STAGE 1 EXIT CRITERIA MET.

## Stage 2 — Content pipeline + learner UI MVP — EXIT MET ON OFFLINE RAILS 2026-08-24 (real rails pending founder creds)
*Exit: a test student can sign up, pay, and complete unit 3.2.1 end to end.*

- [x] S2.1 Content repo layout + schema-validation CI (invalid unit YAML fails the build) — ACCEPTED 2026-08-22 on reviewer-executed proof (harness 13/13 rerun by reviewer; reviewer's independent probe — schema-valid unit planted under wrong id-dir AND wrong phase dir — blocked, named, remote unmoved; validators green on current content; HEAD/hooksPath/protected-docs untouched)
- [x] S2.2 Content PR CI: dry-run the unit's deterministic checks against a reference solution — ACCEPTED 2026-08-23 on reviewer-executed proof (harness 11/11 rerun; direct dry-run shape OK 8p/0f exit 0; reviewer probe — check DELETION in a scratch content copy — caught via [missing], exit 1; smoke-wiring rerun 4/4 after one transient docker port-bind flake; hygiene clean)
- [x] S2.3 Unit-page renderer: Learn / Practice / Build / Verify / Unstuck from content repo — ACCEPTED 2026-08-23 on reviewer-executed proof (real-browser session: both pages, all five sections, 404 correct; content-as-data verified in rendered HTML: 8 check ids, 5 rubric criteria, contract table exact, CLI exact; lint + build clean; humanizer read: zero em/en-dashes, zero hype words; hygiene clean; note: no visual design style has been decided)
- [x] S2.4 Submission flow + verdict display (criteria, evidence quotes, retry path) — ACCEPTED 2026-08-23 on reviewer-executed proof (reviewer's own push graded live in ~39s and browsed in a real browser; all four states rendered incl. reviewer-fabricated queued + grading rows; error page does not fake a verdict; read-only verified: reader is SELECT-only in BEGIN/ROLLBACK, app has zero SQL; smoke-wiring 4/4 after grading-core addition; teardown script verified)
- [x] S2.5 Auth (managed) + Stripe one-time payment — ACCEPTED 2026-08-23 on reviewer-executed proof (smoke-enroll 43/43 + demo-enroll prove 32/32 rerun green; reviewer's OWN webhook replay probe: 3 signed deliveries of one session → enrollments=1 exactly; auth gates verified signed-out (307) AND cross-account (true 404) in a real browser; full sign-up→checkout→pay→enrolled flow walked in-browser 6/6; smoke-wiring 4/4, validators green, teardown verified)
- [x] S2.6 Rebate state machine wired to gate events — ACCEPTED 2026-08-23 on reviewer-executed proof (smoke-rebate 43/43 + demo-rebate prove 26/26 rerun green; reviewer's OWN probes: earning-event replay on a paid rebate → zero state change, cursor reset to 0 → full reprocess into pure no-ops, fabricated capstone pledge with 5-day window → out_of_window rejection + timed expiry + late-passage not_pending rejection, wrong-unit → wrong_unit rejection; real-browser /me pass: paid $1.85 + two expired rebates incl. capstone, copy plain with zero em-dashes; smoke-wiring 4/4, smoke-enroll 43/43, validators green, build OK, teardown verified)
- [x] S2.7 Gate engine: verdict events unlock units per gate rules — ACCEPTED 2026-08-24 (see decisions; browser-backend caveat noted)
- [x] S2.8 Progress dashboard v1 — the growing Meridian map — ACCEPTED 2026-08-24 on execution-verified review (see decisions)

## Stage 3 — Practice engine + concierge — COMPLETED 2026-08-29
*Exit: failed drill → worked example → completion problem → retry works; teach/guard modes verified in CI.*

- [x] S3.1 Completion-problem grading via Layer 1 checks — ACCEPTED 2026-08-24 on execution-verified review (see decisions)
- [x] S3.2 Retrieval-question generation + grading per lesson — ACCEPTED 2026-08-26 on execution-verified review incl. a LIVE injection probe (see decisions)
- [x] S3.3 Spaced re-check scheduler (day +3, +7 surfaces) — ACCEPTED 2026-08-27 on execution-verified review incl. the four-answer LIVE re-proof (see decisions)
- [x] S3.4 Adaptive routing rules (fast pass skips worked example; fail routes through scaffold) — ACCEPTED 2026-08-27 on execution-verified review (see decisions)
- [x] S3.5 Concierge v1 with server-side teach/guard mode switch — ACCEPTED 2026-08-27 on execution-verified review incl. the live teach/guard pair (see decisions)
- [x] S3.6 CI test prompts proving guard mode never writes deliverables — ACCEPTED 2026-08-29 on execution-verified review incl. the 19-item LIVE battery (see decisions)

## Stage 4 — Community, simulations, retention, analytics
*Exit: pilot-ready for the Phases 0–3 cohort.*

- [x] S4.1 Commitment screen + placement diagnostic live at signup — ACCEPTED 2026-08-29 on execution-verified review (see decisions)
- [x] S4.2 Pod tooling (Discord integration) + required weekly post flow — ACCEPTED 2026-08-29 on execution-verified review (see decisions)
- [x] S4.3 Weekly personalized digest (sent whether or not the student logged in) — ACCEPTED 2026-08-29 on execution-verified review (see decisions)
- [x] S4.4 Public build gallery v1 — ACCEPTED 2026-08-29 on execution-verified review (see decisions)
- [x] S4.5 Simulation service: discovery-call persona, scored — ACCEPTED 2026-08-29 on execution-verified review (see decisions)
- [x] S4.6 Simulation service: two skeptical-reviewer personas, scored, feeding gates — ACCEPTED 2026-08-29 on execution-verified review (see decisions)
- [x] S4.7 Per-unit drop-off dashboard — ACCEPTED 2026-08-29 on execution-verified review (see decisions) — STAGE 4 COMPLETE

## Content production track (after Stage 2)
- [ ] C1 Pilot batch: Phases 0–3 lessons + rubrics + fixtures authored and passing CI
- [ ] C2 Phases 4–5
- [ ] C3 Phases 6–7
- [ ] C4 Phases 8–10
- [ ] C5 Phase 11 simulation content + personas

## Lesson UX revamp track (U) — opened 2026-09-02
*Evidence base: four-front online research synthesized 2026-09-02 (best-in-class lesson platform teardowns; learning-science-to-page-design rules; long-form reading typography; flow/session mechanics). Verdict: the current skeleton is already evidence-aligned; the gaps are flow-between-lessons, the practice engine's review model, and a handful of in-page corrections. Full rationale in the 2026-09-02 decision entry. Design contract for U1–U3: docs/lesson-flow-spec.md.*

**Revamp 1 — Flow (exits and resume)**
- [x] U1 End-of-unit exit card: after the last script phase, one card with what the unit just earned (from real data), the single next unit (from gate unlocks), and a wrap-up-here option. Never a dead end.
- [x] U2 Phase-boundary exit markers: at each phase boundary in a unit script, a quiet app-owned line naming the phase just finished and the next one with its read time, making every boundary a legitimate stopping point.
- [x] U3 Resume persistence: store reading position per unit (localStorage, per-device, honest about that), restore it as a resume banner on the unit page and a continue card on the dashboard.

**Revamp 2 — Delivery (practice engine)**
- [x] U4 Checkpoint hint ladders: 1–3 authored hints per checkpoint, sequential disclosures below the scratch box, before the answer; hints show shape, never solutions; reveal gets focus management.
- [x] U5 Mastery states + cross-unit interleaved review queue (practice service): derive per-seed mastery (attempted → familiar → proficient → mastered, decay on missed re-check) from retrieval_attempts at read time; new endpoint returning due review items across ALL units, interleaved, unlabeled by unit.
- [x] U6 Review-queue surface in the app: due reviews from prior units mix into the drill flow (unlabeled), each graded through the existing retrieval attempt path; a due-reviews count surfaces on the dashboard.
- [x] U7 Explain-it-back step: after a passed completion problem, the student writes a 2–3 sentence explanation judged against a rubric (evaluation only, guard-compatible); new prompt + endpoint + card.

**Revamp 3 — In-page structure**
- [x] U8 Code-figure polish: line numbers on line-highlighted code figures (only where a range is authored), so prose references resolve without counting.
- [x] U9 Lesson coda + advisory lesson lint: `::: coda <title>` marker renders a distinct closing design-note card; content/tools/lint-lesson.py advises on the 250-words-between-apparatus rule, coda presence, and heading cadence (advisory, not a gate).

**Revamp 4 — Typography numbers**
- [x] U10 Numbers pass: lesson prose 17px / line-height 1.6 (mobile 1.45), code 0.85em with a 13px floor, h2 rhythm (~3 body lines of air), WCAG 1.4.12 override resilience re-checked, contrast battery still green.

---

## Decisions log

Older decisions live in the archive, split by month, in original log order:
`docs/decisions/2026-08.md` (110 entries) and `docs/decisions/2026-09.md` (23 entries).
This file keeps the most recent decisions (ten at the 2026-09-07 split). New entries
are prepended here at the top; when this file grows past its compact budget, the
oldest entries move to the archive verbatim.

- **2026-09-07 — Grading host LIVE on AWS (new free-tier experience, account 571846855555):**
  - Instance keel-grading (m7i-flex.large, 2 vCPU / 7.6 GB, Ubuntu 24.04, encrypted 30 GB gp3, IMDSv2 required) at 13.223.201.44 (Elastic IP), SSH locked to the operator IP, 80/443 open. The FREE plan blocks non-free-tier types (t4g.medium rejected); m7i-flex.large is free-tier eligible and has NOT drawn down the $100 credits.
  - Full provisioning kit executed over SSH: Docker + keel-runner, keel-pg with all 23 tables, seven keel-* systemd units, Caddy TLS at https://grading.keelacademy.com (Let's Encrypt cert issued), nightly pg_dump cron. Two kit bugs found and fixed in-repo: unquoted KEEL_DB_CMD broke sourcing scripts; Caddyfile env placeholder expanded empty in the caddy unit (now substituted at deploy time).
  - OPENAI_API_KEY installed (validated 200 via /v1/models) and judge calibration run live from the host: 8/8 overall across three runs, 0 errors. First run caught the judge citing s08's PRE-APPROVED tag as evidence; judge prompt hardened (approval claims are prose, never evidence) and re-proven. Criterion agreement stable 38/40 (s04/s06 problem-stated-plainly wobble; a live tightening attempt regressed to 6/8 and was reverted). Formal GATE FAIL is the small-set criterion margin; owner decision pending.
  - Operator notes: operator egress IP is dynamic (SSH SG rule updated once already; consider SSM Session Manager). Payments and auth substitutions (Paddle, no Clerk) are the next build task; Stripe/Clerk values remain placeholders.

- **2026-09-07 — Unit 0.2 ('How the curriculum and grading loop work') authored and verified via Backward Design process:**
  - **UbD Architect:** Design brief with learner baseline (student has client-brief.md, understands OmniCart problem), `forbidden_assumptions` listing all technology words, two spiraled concepts (plain-words-first from 0.1; time-boxing as new concept), zero-jargon competency ("Read how this curriculum is organized; build a progress tracker covering every unit"), five retrieval seeds (13 phases/56 modules, tracker shape, Phase 0 no code, Phase 11 from day one, each module ends with a deliverable), `project_delta` = `omnicart-system/docs/progress-tracker.md`, and Apex Freight parallel task (Marcus Bell builds a 56-row tracker for carrier audit steps). `content/units/phase-0/0.2/consistency.yaml` written with numbers `["13 phases", "56 modules"]` and documents `["progress-tracker.md"]`.
  - **Assessment Engineer:** `worked-example/README.md` (Apex Freight 56-row tracker, Marcus Bell, 6 annotation blocks explaining why the header, Phase 0 rows, and path pass) and `completion/README.md` (all 56 module IDs listed explicitly including 3.2.1, four-column template, 9-item self-check, folder instructions). Key decision: added the full 56-module ID list to completion/README so students need not guess IDs from phase counts alone.
  - **Rubric Evaluator:** `content/rubrics/0.2/v1.yaml` (4 criteria: `all-modules-present`, `required-columns-present`, `phase-0-done`, `tracker-path-correct`), `content/prompts/judge-0.2.md` (criteria-ARRAY contract, quoted-evidence mandate, injection defense, column-name case-sensitive rule), `content/golden/0.2/` with README matrix and 5 pre-graded submissions (s01 textbook pass, s02-s05 each isolating exactly one failing criterion). `validate-rubrics.py` exits 0.
  - **Pedagogical Author:** `learn.md` unit script (six `::: phase` blocks, three `##` headings in learn, one Mermaid figure, no seed words in headings after two rounds of renaming, FK lint 0 advisories in strict mode), `unit.yaml` (conceptual, 5 seeds, 3 unstuck refs, unlocks 0.3), `content/faq/0.2.md` (3 before/after notes). Heading fixes required: em dashes in fenced block replaced with colons, two long sentences split, two headings renamed to avoid seed keywords ('ends', 'tracker', 'turn'). Strict lint PASS after fixes.
  - **Blind Playtester (cold review):** One continuity violation found: the lesson text block showed only phase counts (not individual module IDs), and the completion README said "See the module list in the lesson" — but the lesson had no per-module ID list. Students would not have known about 3.2.1. Fixed: added full 56-module ID list (including 3.2.1 noted explicitly) to completion/README, updated self-check Q8 to ask about 3.2.1, removed "See the module list in the lesson" pointer. Also fixed: "Plan for about 30 minutes of your half-hour" (awkward) reworded to "Plan for about 30 minutes". Round 2: zero Continuity Violations, zero Readability Issues.
  - **Validation Battery:** `validate.py` PASS (unit.yaml schema, phases.yaml map, ledger.yaml all green), `validate-rubrics.py` PASS (both 0.1 and 0.2), `validate-gates.py` PASS (capstone, phase-5-integration, unit-0-2 all valid), `validate-map.py` PASS (13 phases, 56 modules), `validate-routing.py` PASS (0.1 and 0.2 routing valid), `lint-lesson.py --strict` PASS (0 advisories, FK grade below 8), `check-unit-consistency.py 0.2` PASS, `npm run test` (tsc + eslint) exit 0, `check-mermaid.mjs` 3/3 (2 from 0.1, 1 from 0.2).
  - **Gate:** `content/gates/unit-0-2.yaml` written (unit_id 0.2, unlocks 0.3, rebate false).
  - **Ledger:** Unit 0.2 appended to `content/curriculum/ledger.yaml` (7 concepts unlocked, 4 contracts established, project delta progress-tracker.md, 5 retrieval seeds, narrative anchor).
  - **Not done:** live judge calibration (no API key in this session); full-stack rendered playthrough in the app.

- **2026-09-07 — Grading-host provisioning kit added at scripts/provision/ (Oracle Always Free A1 target, any Ubuntu 24.04 host works):**
  - Ordered, idempotent scripts: 10-docker.sh (Docker for arm64, cgroup v2 check that hard-fails otherwise, keel-runner:0.1 build), 20-postgres.sh (keel-pg container on a volume + schema 0001..0014 with ON_ERROR_STOP), 30-services.sh (systemd units for the seven long-runners: intake, reader, enroll, practice, proxy, worker, rebate; env from /etc/keelacademy/env), 40-caddy.sh + Caddyfile (TLS, path routing to reader/enroll/practice plus the Stripe webhook; proxy and loops never exposed), 50-backup.sh (nightly pg_dump, 7-day retention), 60-smoke.sh (liveness: units active, ports open, DB answers, sandbox image present).
  - env.grading-host.example is the full host-env template (DB, ports, LLM proxy incl. the per-unit cap, worker routing through the local proxy, Stripe test-mode, intake secret, rebate knobs); real values from FOUNDER-WIRING.md; the filled file is chmod 600 and never committed. Vercel-side (Clerk, app URLs) stays on Vercel per that runbook.
  - Constraints encoded, not just documented: one keel-proxy process (in-process budget locks), services bind 127.0.0.1 only, worker gets SupplementaryGroups=docker, cgroup v2 is a hard prerequisite.
  - Ops doc: hosting decision recorded earlier stays (app on Vercel, grading on one VM); at ~100 paying students the guidance is 4 OCPU / 16 GB PAYG or Hetzner, multiple worker processes (SKIP LOCKED makes this safe), Vercel Pro for commercial ToS; LLM spend stays bounded by the per-student and per-unit caps.

- **2026-09-07 — Unit 0.2 deleted at owner direction (authored then removed in the same session):**
  - Removed all authored content, rubrics, golden calibration sets, prompts, routing rules, and FAQ assets for Unit 0.2 (`content/units/phase-0/0.2/`, `content/rubrics/0.2/`, `content/golden/0.2/`, `content/prompts/judge-0.2.md`, `content/routing/0.2.yaml`, `content/faq/0.2.md`).
  - Reset `content/curriculum/ledger.yaml` units to `[0.1]` (the 0.2 ledger entry is removed).
  - Retained Unit 0.2 in the curriculum map (`content/curriculum/phases.yaml`) and in 0.1's gate unlocks, where continuity requires it (renders honestly as planned/content-arriving in the dashboard).
  - Stale historical references intentionally left as written: the `.doc-audit/` inventory (already stale for the 0.3 and 3.2.1 deletions) and the `docs/decisions/` archive.
  - All content validators re-run green after removal (exit 0).

- **2026-09-07 — Improvement plan M2.3 to M6.3 completed in one session (branch improve/review-2026-09; all proofs green; per-item detail in docs/improvement-plan.md log):**
  - **Pipeline gates:** strict lint + cross-file consistency wired into the pre-push hook and content-gate.yml; `content/STYLE.md` (44 lines) is the single plain-language standard, linked from all six agent contracts; unit_orchestrator battery runs the new gates and requires pasted script output from every specialist.
  - **Repo memory:** build-state split (137.4 KB archived verbatim to `docs/decisions/2026-08.md` + `2026-09.md`, all 138 entries verified); `curriculum-section.py <unit>` prints one unit's curriculum slice; `docs/voice.md` defines lesson voice; root `README.md` + `.env.example`; debris scripts removed, Docker starter kept at `scripts/start-docker.sh`.
  - **Platform:** first unit tests (pytest 30: judge contract, rubric resolution, gate ceilings, models loader, proxy budget; node --test 12: parseUnitScript via jiti, text helpers); `validate-routing.py` passes with a note when `content/routing/` is absent; `platform/models.yaml` + loader give llm.py and the proxy one tier source with old defaults as fallback.
  - **Safety:** untrusted-input blocks hardened in the three live prompts; golden `s08-injection-attempt` added (matrix row, objective now 8/8, banned scan clean); sandbox limits audited in `platform/grading/sandbox/AUDIT.md` (two gaps documented pending a live Docker re-proof); proxy per-unit token cap (`X-Keel-Unit-Id`, `KEEL_UNIT_TOKENS_CAP`, in-process like the per-student lock) with llm.py forwarding `KEEL_LLM_UNIT_ID`.
  - **UX:** workbench word counter + banned-word warning; reading tracker word-based progress, paused on hidden tabs; sample verdict card under the rubric card.
  - **Battery:** content gate, pytest 30/30, node --test 12/12, `npm run test`, check-mermaid 2/2 all green.

- **2026-09-06 — Unit 0.1 re-authored & verified via Backward Design subagent team (first `unit_orchestrator` run):**
  - **Orchestrator:** Step 0 resume protocol run (Next action confirmed, `content/units/` absent, ledger `units: []`, baseline battery green). Work staged on branch `author/unit-0.1` so each specialist could clone the accepted upstream outputs; design brief kept at `scratch/design-brief-0.1.md` (throwaway per AGENTS.md). Two orchestrator decisions recorded: (a) the completion problem asks for the full five-heading brief, not one section, because conceptual grading runs the unit rubric with `pass_rule: all`; (b) the banned-words gate is its own rubric criterion `no-technology-words` since conceptual units have no Layer 1; (c) after the playtest the word floor dropped from 300 to 250 because the floor forced padding.
  - **UbD Architect:** Design brief with learner baseline (`forbidden_assumptions` lists every technology word and tool), zero-jargon target competency, essential question, five-heading deliverable spec, four proposed criteria, five retrieval seeds, `project_delta` = `omnicart-system/docs/client-brief.md`, and the Apex Freight parallel task with three named stakeholders (Marcus Bell, Priya Nair, Dana Okafor).
  - **Assessment Engineer:** `worked-example/README.md` (Apex model brief, 336 words, 7+7 steps, four annotation blocks) and `completion/README.md` (fact sheet, 9 rules, `The five checks`, template, 14-question self-check, folder instructions). Proof: model brief passes every rule by script; empty template fails word count and step checks.
  - **Rubric Evaluator:** `content/rubrics/0.1/v1.yaml` (5 criteria: `no-technology-words`, `problem-stated-plainly`, `three-stakeholders-differ`, `current-process-traceable`, `target-process-measurable`), `content/prompts/judge-0.1.md` (868 words, `RUBRIC_INSERT` marker, criteria-array JSON contract, quoted-evidence mandate, injection defense), `content/golden/0.1/` with README matrix and 7 pre-graded submissions (s01 textbook pass, s02-s06 each isolating exactly one failing criterion, s07 minimal pass; 309 to 453 words; banned words only in s02).
  - **Pedagogical Author:** `learn.md` unit script (1,639 prose words, six `::: phase` blocks, 3/1/1/1/1/1 `##` headings, two Mermaid figures, no seed words in headings), `unit.yaml` (conceptual, 5 seeds, 4 unstuck refs), `content/faq/0.1.md` (4 before/after notes). Owner direction honoured: no `Predict, then check` or `Gotcha` blockquotes; pacing by asides, recaps and text blocks.
  - **Blind Playtester:** Round 1 cold write finished in 58 minutes and surfaced 25 findings (lesson said five checks while the README listed nine rules; README rules omitted the two numbers, the four papers and the under 1 hour target that the rubric grades; FAQ leaked an untaught 50000 cents threshold; `#` marks, folder path, `ticket`, `delivery slip`, `unboxing photo`, `VP` never explained; idioms; an unsourced 400 cases figure; 300-word floor forced padding). All routed to owning agents and fixed. Round 2 confirmed 24/25 closed and found 7 wording alignments (old start point in four places, four parts vs five headings, wait stated for all cases, how to count words); applied verbatim. Second cold write: 313 body words with no padding, 14/14 self-checks yes.
  - **Validation Battery:** `validate.py` PASS (incl. new ledger entry), `validate-rubrics.py` PASS, `validate-map.py` PASS, `validate-routing.py` PASS (`content/routing/0.1.yaml` re-added), `lint-lesson.py` 0 advisories (FK Grade 3.4, Flesch RE 87.0), `npm run test` (tsc + eslint) exit 0, `check-mermaid.mjs` 2/2. Repo-wide scan of all 23 unit files: 0 em dashes, 0 en dashes, 0 exclamation marks (excluding the mandatory `<!-- RUBRIC_INSERT -->` marker), 0 technology words in student-facing prose.
  - **Not done:** live judge calibration (no API key in this session); full-stack rendered playthrough in the app.
  - Ledger: Unit 0.1 appended to `content/curriculum/ledger.yaml` (concepts unlocked, anti-prerequisites, project working tree, seeds, narrative anchor).

- **2026-09-06 — Unit 0.1 deleted for plain-language re-authoring:**
  - Removed all authored content, rubrics, golden calibration sets, prompts, routing rules, FAQ assets, and gate for Unit 0.1 (`content/units/phase-0/0.1/`, `content/rubrics/0.1/`, `content/golden/0.1/`, `content/prompts/judge-0.1.md`, `content/routing/0.1.yaml`, `content/faq/0.1.md`, and `content/gates/unit-0-1.yaml`).
  - Reset `content/curriculum/ledger.yaml` units to `[]` (clean zero-authored-units state).
  - Retained Unit 0.1 in the curriculum map (`content/curriculum/phases.yaml`), diagnostic baseline, and database schema where curriculum architectural continuity requires it (renders honestly as planned/content-arriving in the dashboard).
  - All 8 content validation gates, linters, and Next.js TypeScript compilation verified clean (green exit 0).

- **2026-09-06 — Plain-language standard instituted for lesson authoring (non-native English accessibility):**
  - Audited authoring sub-agent contracts: identified that absence of readability constraints caused lesson content to drift to collegiate reading levels (Flesch-Kincaid Grade 11-16) with heavy domain vocabulary that presents barriers for non-native English speakers.
  - Added 7 non-negotiable Plain-Language Rules to `.agents/skills/shiffman-style-lessons/SKILL.md`: target FK Grade Level <= 8 for lesson prose, sentence ceiling of 20 words, explain-then-name principle, prefer common words, inline first-use definitions for domain terms, active voice, and single-idea paragraphs.
  - Added vocabulary substitutions table to `.agents/skills/shiffman-style-lessons/references/voice-guide.md`: explicit mappings from formal/academic words (velocity -> speed, latency -> delay, statutory -> required by law, auditability -> being able to check and prove every step, etc.) to plain English alternatives on first use.
  - Updated copy rules in `platform/app/AGENTS.md` mandating the Flesch-Kincaid Grade 8 target for lesson prose.
  - Extended advisory lesson linter `content/tools/lint-lesson.py` with automated Flesch-Kincaid Grade Level and long-sentence (>25 words) checks.

