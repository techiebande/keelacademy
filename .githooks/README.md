# .githooks — keelacademy local gates

## Activation (one-time, per clone)

Git does not run hooks from `.githooks/` until you point it there:

```bash
git config core.hooksPath .githooks
```

This is a human setup act — do it once after cloning. Deactivate with
`git config --unset core.hooksPath`.

## pre-push — content schema gate (S2.1)

Runs on every push:

```bash
python3 content/tools/validate.py        # units (discovered), examples, variants, personas
python3 content/tools/validate-rubrics.py  # rubrics + filename/version layout
python3 content/tools/validate-gates.py    # gate rules + filename/gate-id layout
python3 content/tools/validate-map.py      # curriculum map (phases.yaml)
python3 content/tools/validate-routing.py  # adaptive routing rules
python3 content/tools/validate-guard-evals.py # concierge guard evals
python3 content/tools/validate-diagnostics.py # diagnostic assessments & commitment declarations
python3 platform/grading/scripts/check-concierge-structural.py # concierge structural contract
```

Any validator failing blocks the push; the validator output names the
offending file(s). GitHub CI runs the same validation checks on content PRs
(`.github/workflows/content-gate.yml`).

## Bypass (scripted tooling only)

```bash
KEEL_SKIP_CONTENT_GATE=1 git push
```

Skips all validators with a loud one-line notice. For scripts that push
non-content commits in bulk; never use it to push content you would not
submit to CI.
