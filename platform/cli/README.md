# keelacademy grading CLI

Three layers:

- **Layer 1** (`python -m grader.l1`): runs a submission's checks in a sandboxed
  Docker container (no network) and parses per-test results. See `grader/l1.py`.
- **Layer 2** (`python -m grader.judge`): reads the submission **as text only**
  (never executes student code), injects the rubric verbatim + the submission's
  files into the rubric's judge prompt, calls an LLM, and emits a structured
  verdict validated against `grader/verdict.schema.json`. Requires network.
- **Layer 3** (`python -m grader.defend`): reads the submission **as text only**
  and generates 2–3 defend-your-work follow-up questions targeting concrete
  code from THIS submission (functions, constants, branches), validated against
  `grader/defend.schema.json`. Requires network. See `grader/defend.py`.

## Layer-3 usage

```
python -m grader.defend <submission_dir> [--tier mid] [--json out.json]
```

- Same file exclusions as the judge (`grade.yaml`, `claims_messy.jsonl`,
  `__pycache__/` never reach the model); default tier `mid` (gpt-4.1).
- Each question carries `anchors`: identifiers / paths / code fragments the
  question targets. The CLI verifies every anchor **literally appears** in the
  submission's text — a missing anchor triggers one retry with a nudge naming
  the missing anchors, then a hard error (exit 2). Model output is never
  trusted on its own.
- Output: `{submission_ref, tier, questions[{id, question, anchors}], meta}`.
- Exit codes: 0 = success, 2 = error.

## Layer-2 usage

```
python -m grader.judge <submission_dir> --rubric content/rubrics/3.2.1/v1.yaml [--json out.json]
```

- The rubric's `judge.prompt` path is resolved relative to the content/ root
  (the rubric's ancestors are searched for the prompt path, so any rubric
  layout under content/ works).
- Submission files injected: everything except `grade.yaml` (grader answers),
  `claims_messy.jsonl` (data fixture), and `__pycache__/` — per the submission
  layout contract declared in the checks file's header.
- `overall` is **recomputed in the CLI** (pass iff every criterion passes). If
  the model's own `overall` disagrees, the verdict is rejected (exit 2) — the
  model's arithmetic is never trusted.
- Malformed model JSON → one retry with a "valid JSON only" nudge; a second
  failure is an error, never a guessed verdict.
- Exit codes: 0 = overall pass, 1 = overall fail, 2 = error.
- Every call is traced to stderr: model, tokens in/out, latency, estimated cost
  (seed of S1.7 trace logging).

## Calibration

```
python -m grader.calibrate --golden content/golden/3.2.1 \
    --rubric content/rubrics/3.2.1/v1.yaml [--json report.json]
```

- Judges every submission dir under `--golden` in sorted order via the same
  `grader.judge.judge` code path as the CLI (no duplicated LLM logic), then
  compares overall and criterion-for-criterion against each `grade.yaml`.
- A reference `expected` of pass/fail must match exactly; `expected:
  borderline` counts as a match when the judge lands on the same side as the
  human's resolved binary `overall` in the same grade.yaml (a binary judge can
  never literally match the string "borderline").
- Transient network failures (DNS blips, connection resets, read timeouts) are
  retried up to 3 times per submission; a hard judge error becomes an ERROR row
  (the run continues) and errors count separately from mismatches.
- Exit code: **0 iff overall agreement ≥ 90% AND zero errors; else 1** — these
  are the semantics the S1.6 golden-set regression gate inherits.
- This harness is the seed of the S1.6 CI gate on rubric PRs.

## Rubric versioning

Rubrics live at `content/rubrics/<unit_id>/v<N>.yaml` (was
`content/rubrics/<unit_id>.yaml` before S1.6). Each file's top-level
`version:` must equal the `v<N>` in its filename. The **highest version
number is the ACTIVE rubric** for the unit; `grader.rubric_version.
resolve_active_rubric(unit_id)` implements that rule. Tools that need an
exact historical version (judge/calibrate/gate) take an explicit path.

`content/tools/validate-rubrics.py` (stdlib + PyYAML only) validates every
`content/rubrics/*/v*.yaml` against `content/schemas/rubric.schema.json` and
checks filename/version-field consistency; exit 0 all-valid, 1 otherwise.
Since S2.1 it also fails on any other `.yaml` shape under `content/rubrics/`
(top-level, nested deeper, or not named `v<N>.yaml`) — such a file would be
skipped by both the validator and `resolve_active_rubric`.

## Regression gate (S1.6)

```
python -m grader.gate --golden content/golden/3.2.1 \
    --rubric content/rubrics/3.2.1/v1.yaml [--json gate-report.json]
```

- Runs the **same** calibration code path as `grader.calibrate` (shared
  `run_calibration` — no fork), then applies gate thresholds.
- **PASS iff zero judge errors AND overall agreement ≥ 14/15 AND criterion
  agreement ≥ 72/75** (ratios, so they scale if the golden set grows).
  Rationale: the S0.7 baseline is 15/15 overall + 75/75 criterion; a dated
  ruling in build-state.md established that the judge's per-criterion failure
  set can vary between runs at temperature 0 while overall stays stable, so
  the gate is primarily on OVERALL agreement with criterion as a secondary
  signal. The one-submission / three-criterion margins absorb observed judge
  variance, while any real rubric degradation flips multiple submissions and
  fails hard.
- Exit 0 = PASS, 1 = FAIL.
- CI: `.github/workflows/rubric-gate.yml` runs the validator + this gate
  (against the ACTIVE rubric via the resolver) on PRs touching
  `content/rubrics/**`, `content/golden/**`, or `platform/cli/grader/**`.
  This is the merge-blocking gate from the Stage 1 exit criteria.

## API key convention

The judge reads `OPENAI_API_KEY` from the environment only. In non-interactive
shells (~/.bashrc is NOT sourced), source the secrets file in the same command:

```
set -a; source ~/.keelacademy.env; set +a
```

Keys are never hardcoded, written to disk, or committed.

## Model tier mapping

`rubric.judge.model_tier` maps to a concrete model via the `MODEL_TIERS` dict in
`grader/judge.py`, which also carries a price table (USD per 1M tokens,
approximate list prices) used only for the stderr cost trace:

| tier | model      | $/1M in | $/1M out |
|------|------------|---------|----------|
| low  | gpt-4o-mini| 0.15    | 0.60     |
| mid  | gpt-4.1    | 2.00    | 8.00     |
| high | o3         | 2.00    | 8.00     |

## Verdict schema

`grader/verdict.schema.json` (JSON Schema draft 2020-12, `additionalProperties:
false`): `{rubric_id, rubric_version, submission_ref, criteria[{id, verdict,
evidence}], overall, meta?}` where `meta = {model, prompt_tokens,
completion_tokens, latency_s}`.
