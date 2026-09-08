# Templates for authoring one unit

Copy the skeleton, fill every `<...>` slot, never restructure. Each skeleton is
the shape the app, the validators and the graders expect. A small model given a
skeleton and `content/STYLE.md` produces a shippable file; the same model given a
blank page does not.

| File | Copy to |
|---|---|
| `learn.skeleton.md` | `content/units/phase-<N>/<id>/learn.md` |
| `unit.skeleton.yaml` | `content/units/phase-<N>/<id>/unit.yaml` |
| `worked-example.skeleton.md` | `content/units/phase-<N>/<id>/worked-example/README.md` |
| `completion.skeleton.md` | `content/units/phase-<N>/<id>/completion/README.md` |
| `consistency.skeleton.yaml` | `content/units/phase-<N>/<id>/consistency.yaml` |
| `rubric.skeleton.yaml` | `content/rubrics/<id>/v1.yaml` |
| `judge.skeleton.md` | `content/prompts/judge-<id>.md` |
| `grade.skeleton.yaml` | `content/golden/<id>/<slug>/grade.yaml` |
| `faq.skeleton.md` | `content/faq/<id>.md` |

Prove a filled skeleton with the battery in `.agents/agents/unit_orchestrator/agent.md`, Step 6.
