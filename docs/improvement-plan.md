# Improvement plan (from the 2026-09-06 whole-project review)

Tracked here, one checkbox per sub-milestone. Rule: a box is ticked only after the change is
pushed to branch `improve/review-2026-09` and its proof command is green. Owner-only items are
listed at the end so nothing from the review is lost.

Legend: `[x]` done and pushed, `[~]` in progress, `[ ]` not started, `[-]` deferred with a reason.

## M1. Lesson diagrams render legibly

Problem: labels overflowed their boxes and text shrank. Root causes found in
`platform/app/components/unit/mermaid-runtime.tsx` and `app/globals.css`: fonts and line-height were
restyled with `!important` after Mermaid had measured the labels; `max-width` was removed so wide
diagrams scaled down to fit; plain labels never wrap in Mermaid 11.

- [x] 1.1 Runtime: keep Mermaid's `max-width`, set `fontSize` 16px, enable `markdownAutoWrap` and `wrappingWidth`, stop mutating label styles after render. Proof: `npm run test`.
- [x] 1.2 CSS: remove the `!important` font and line-height overrides on `foreignObject` text; give `.diagram-frame` horizontal scroll so a wide diagram scrolls at 100% instead of shrinking. Proof: `npm run test`.
- [x] 1.3 `check-mermaid.mjs`: also fail on more than 6 nodes, any label line over 5 words or 28 characters, `LR` with more than 3 nodes, and subgraphs. Proof: script exits 1 on a fixture and 0 on the tree.
- [x] 1.4 Rewrite the two Unit 0.1 figures with short wrapped labels that pass 1.3. Proof: `check-mermaid.mjs` 2/2, `lint-lesson.py` clean.
- [x] 1.5 Authoring rule for diagrams added to `pedagogical_author` contract and the Shiffman skill. Proof: grep.
- [-] 1.6 Build-time SVG rendering in CI. Deferred: needs a headless browser in CI; tracked as owner item O1.

## M2. Content pipeline gates (so small models produce good lessons)

- [x] 2.1 `lint-lesson.py --strict`: exit 1 on FK over 8, any sentence over 20 words, prose block over 250 words, missing coda, em or en dash, exclamation mark, technology word in student prose, heading that borrows a seed word. Proof: strict run on 0.1 exits 0; a fixture with each defect exits 1.
- [x] 2.2 `content/tools/check-unit-consistency.py`: numbers, five headings, start and end points, document names and banned-word list must agree across learn.md, completion README, faq, rubric, judge prompt. Proof: exits 0 on 0.1; exits 1 when one file is mutated.
- [x] 2.3 Skeletons in `content/templates/`: `learn.skeleton.md`, `unit.skeleton.yaml`, `completion.skeleton.md`, `worked-example.skeleton.md`, `grade.skeleton.yaml`, `judge.skeleton.md`. Proof: files exist and the author contract points at them.
- [x] 2.4 `content/STYLE.md`: the shared plain-language and copy rules in one place (under 60 lines). Agent contracts reference it instead of repeating it. Proof: each of the six contracts links to it.
- [x] 2.5 Wire 2.1 and 2.2 into `.githooks/pre-push` and `.github/workflows/content-gate.yml`. Proof: files updated; hook runs locally.
- [x] 2.6 `unit_orchestrator` battery lists the new gates and requires pasted script output from every specialist. Proof: grep.

## M3. Repo memory and docs

- [x] 3.1 Split `build-state.md`: keep status, next action, milestone checklists and the last 10 decisions; move the rest of the decisions log to `docs/decisions/2026-08.md` and `docs/decisions/2026-09.md`. Proof: `build-state.md` under 40 KB, no entry lost (line count check).
- [x] 3.2 `content/tools/curriculum-section.py <unit>` prints only that unit's section of `curriculum.md`. Proof: run on 0.1 and 3.2.1.
- [x] 3.3 `AGENTS.md` read-first list points at the compact files. Proof: diff.
- [x] 3.4 `docs/voice.md`: the single definition of lesson voice (Shiffman mechanics plus plain-language rules plus Keel copy bans). Proof: file exists, referenced from STYLE.md.
- [x] 3.5 Root `README.md` (what, prerequisites, how to run each part, where the docs are) and `.env.example`. Proof: files exist.
- [x] 3.6 Remove committed debris: `.final2.sh`, `.fix-leftovers.sh`, `.resume-hygiene.sh`, `.start-docker.sh` (keep the Docker starter under `scripts/` with a clear name). Proof: root listing.

## M4. Platform engineering

- [x] 4.1 First unit tests: `platform/cli/tests/test_judge_parse.py`, `test_rubric_version.py`, `test_gate_thresholds.py`; `platform/app/lib/content.test.mjs` for `parseUnitScript` via a tiny harness. Proof: `pytest -q` green; `node --test` green.
- [x] 4.2 `validate-routing.py`: missing `content/routing/` is a pass with a note, not an error. Proof: run with the dir moved aside.
- [x] 4.3 `platform/models.yaml` (tier to model) with a loader; `llm.py` and `proxy/server.py` read it with the old defaults as fallback. Proof: tests pass, grep shows one source of truth.
- [-] 4.4 Split `practice/server.py` (4,163 lines). Deferred: needs the Docker stack to re-prove the smoke battery; owner item O2.

## M5. Safety and ops

- [x] 5.1 Untrusted-input block added to `retrieval-grade.md`, `concierge-teach.md`, `concierge-guard.md`. Proof: grep.
- [x] 5.2 Adversarial golden submission `s08-injection-attempt` for 0.1 plus README matrix row. Proof: `validate-rubrics.py` green; banned-word scan.
- [x] 5.3 Sandbox runner limits audited (CPU, memory, pids, network, timeout); gaps fixed or documented. Proof: grep of `docker run` flags.
- [x] 5.4 Per-unit LLM budget cap in the proxy, alongside the per-student cap. Proof: unit test.

## M6. Pedagogy and UX quick wins that need no visual check

- [x] 6.1 Live word counter and banned-word warning in the practice workbench textarea. Proof: `npm run test`.
- [x] 6.2 `reading-tracker.tsx`: progress is words scrolled past over words total, paused when the tab is hidden. Proof: `npm run test`.
- [x] 6.3 Sample verdict card in the verify phase (static example of what the grader returns). Proof: `npm run test`.
- [-] 6.4 Rail Read vs Do split, focus and split-view toggle, light palette tuning, distinct worked-example vs completion affordances. Deferred: need a rendered page to judge; owner items O3 to O6.

## Owner items (cannot be finished in this session)

- O1 Build-time Mermaid to SVG in CI (needs headless browser in Actions).
- O2 Split `practice/server.py` and re-prove the smoke battery on the Docker stack.
- O3 Rail: separate Read beats from Do chores; show minutes per beat.
- O4 Focus and split-view toggle on the unit page at `md:` and up.
- O5 Light-mode palette review for lesson prose.
- O6 Distinct affordances for worked example vs completion cards.
- O7 Run judge calibration on `golden/0.1/` with a real key; record 7/7 (8/8 after 5.2).
- O8 Put five real learners through Phase 0 before authoring Phase 2.
- O9 Add transfer-style retrieval seeds once the practice server can grade them.
- O10 Per-unit pre-check questions feeding the diagnostic.

## Log

- 2026-09-07 00:20 Plan created on branch `improve/review-2026-09` (stacked on `author/unit-0.1`, PR #1).
- 2026-09-07 00:23 M1.1, M1.2 pushed: runtime keeps max-width with an 85% shrink floor, fontSize 16px, markdownAutoWrap + wrappingWidth 170; CSS no longer restyles label typography after layout. tsc + eslint green.
- 2026-09-07 00:27 M1.3 to M1.5 pushed: check-mermaid enforces 6 nodes, 5 words / 28 chars per label line, TD above 3 nodes, no dashes; both 0.1 figures rewritten and pass; rule added to author contract and skill. M1 complete except O1.
- 2026-09-07 00:30 M2.1 pushed: --strict gate (FK, 20-word sentences, dashes, exclamation marks, tech words, seed words in headings, coda, pacing). It found one real defect in 0.1 (a heading borrowing the seed word today), fixed. Fixture at content/tools/fixtures/lint.
- 2026-09-07 00:52 M2.2 pushed: check-unit-consistency.py plus content/units/phase-0/0.1/consistency.yaml (canonical numbers and documents). Passes on 0.1; fails when the FAQ teaches an orphan amount or the lesson miscounts the checks.
- 2026-09-07 00:58 M2.3, M2.4 pushed (remote session): content/STYLE.md (one page of shared rules, mirrors the linter word list) and nine skeletons in content/templates/; all six agent contracts now point at both.
- 2026-09-07 01:05 M2.5 and M4.2 pushed (remote session): pre-push hook and content-gate.yml now run lint --strict, check-unit-consistency for every unit, and check-mermaid (CI installs node). validate-routing and validate-guard-evals pass with a note when their directory is absent (both were red on the canonical tree, guard-evals still is on main).
- 2026-09-07 01:08 M2.6 pushed (remote session): orchestrator battery has 8 gates incl. strict lint, consistency and mermaid; pasted proof output is mandatory; ubd_architect now owns consistency.yaml. M2 complete.
- 2026-09-07 11:40 Merge: the local session's M2.3-M2.6 work merged with the parallel remote implementation above. STYLE.md is the union (remote linter-tied rules plus the docs/voice.md pointer and verification section); the orchestrator battery union has 9 gates (adds validate-gates.py) with the full proof rule; specialist contracts deduped to one STYLE.md pointer plus a short step reference.
- 2026-09-07 11:40 M2.3 verified and ticked (skeletons exist, every authoring contract points at them).
- 2026-09-07 11:40 M3.1 to M3.6 pushed: build-state.md split keeping the ten most recent decisions, 128 archived verbatim in docs/decisions/2026-08.md and 2026-09.md (all 138 entries verified present exactly once); content/tools/curriculum-section.py proven on 0.1 and 3.2.1; AGENTS.md read-first list points at the compact files; docs/voice.md referenced from STYLE.md; root README.md and .env.example; debris scripts removed, Docker starter kept as scripts/start-docker.sh.
- 2026-09-07 11:40 M4.1 and M4.3 pushed: platform/cli pytest suite (30 green: judge parse and recompute contract, rubric version resolution, gate thresholds, models loader, proxy unit budget) plus platform/app node tests (12 green: parseUnitScript via a jiti harness, text helpers); platform/models.yaml + models_loader.py give llm.py and the proxy one tier source with the old defaults as fallback.
- 2026-09-07 11:40 M5.1 to M5.4 pushed: untrusted-input blocks hardened in the three prompts (grep proof); golden s08-injection-attempt added with README matrix row (validate-rubrics green, banned-word scan clean, 334 words, expected fail on the vague problem section with embedded grader-directed instructions to ignore); sandbox limits audited in platform/grading/sandbox/AUDIT.md (gaps documented: --ulimit nofile and explicit --ipc private, landing needs a live Docker re-proof); proxy gained a per-unit token cap (X-Keel-Unit-Id header, KEEL_UNIT_TOKENS_CAP) alongside the per-student cap, with unit tests.
- 2026-09-07 11:40 M6.1 to M6.3 pushed: live word counter and banned-word warning in the conceptual workbench textarea (helpers in lib/text.ts with node tests); reading tracker reports words scrolled past over words total and pauses while the tab is hidden; sample verdict card under the rubric card. Proof: npm run test green, node --test green.
- 2026-09-07 19:40 O7 live progress: judge calibration run against the real API on the AWS grading host. Three runs: 8/8 overall every time, 0 errors; the s08 injection fix (approval claims are never evidence) took effect after the first run caught the judge citing the PRE-APPROVED tag as evidence. Criterion agreement stable at 38/40: s04 and s06 problem-stated-plainly fail while quoting compliant text. A live prompt-tightening attempt made it worse (6/8) and was reverted (986ea4c). Formal GATE FAIL is the criterion margin (ceil 96 percent of 40 rows = 39) inherited from the 15-submission set; owner decision needed: margin for small sets, or offline prompt iteration.
