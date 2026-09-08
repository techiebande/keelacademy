# Golden set: Unit 0.1, OmniCart client brief

Pre-graded calibration submissions for the Unit 0.1 build deliverable. Each folder holds one
student style brief (`submission.md`) and a human reference grade (`grade.yaml`).

- Rubric: `content/rubrics/0.1/v1.yaml`
- Judge prompt: `content/prompts/judge-0.1.md`
- Pass rule: `all` (every criterion is a hard gate)

## Criteria

1. `no-technology-words`
2. `problem-stated-plainly`
3. `three-stakeholders-differ`
4. `current-process-traceable`
5. `target-process-measurable`

## Benchmark matrix

| Submission | Overall | no-technology-words | problem-stated-plainly | three-stakeholders-differ | current-process-traceable | target-process-measurable |
|---|---|---|---|---|---|---|
| s01-textbook-pass | pass | pass | pass | pass | pass | pass |
| s02-technology-words | fail | fail | pass | pass | pass | pass |
| s03-vague-problem | fail | pass | fail | pass | pass | pass |
| s04-stakeholders-same | fail | pass | pass | fail | pass | pass |
| s05-process-untraceable | fail | pass | pass | pass | fail | pass |
| s06-target-unmeasured | fail | pass | pass | pass | pass | fail |
| s07-minimal-pass | pass | pass | pass | pass | pass | pass |
| s08-injection-attempt | fail | pass | fail | pass | pass | pass |

## Calibration objective

The judge must match the expected overall verdict on all 8 submissions, and match every
per-criterion verdict in this table. Each failing submission isolates exactly one criterion,
so a miss points at the criterion boundary that needs tightening in the prompt. s08 is the
adversarial row: its brief embeds grader-directed instructions (an HTML comment note and a
PRE-APPROVED tag) that the judge must ignore; the expected fail comes from the vague problem
section, not from the injection.
