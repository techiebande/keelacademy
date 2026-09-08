# Keel Academy

A self-contained online school that takes learners from zero experience to
shipping and selling production-grade AI systems. Lessons, rubrics, and
fixtures are data (MDX + YAML, schema-validated); the platform is the engine
that grades, gates, and serves them.

## What is here

- `curriculum.md` — the source curriculum (reference; never edited by agents)
- `school-architecture.md` — the design: what we are building and why
- `build-plan.md` — the build approach: stages and exit criteria
- `build-state.md` — live progress: status, next action, recent decisions
  (full decision archive in `docs/decisions/`)
- `content/` — units, rubrics, prompts, golden sets, FAQs, personas, gates
- `platform/` — the code:
  - `platform/cli` — Python grading CLI (Layer 1 runner, judge, calibrate)
  - `platform/grading` — FastAPI/Python grading core: Postgres schema, worker,
    sandbox runner, LLM proxy, practice engine, enroll, reader, analytics
  - `platform/app` — Next.js/TypeScript learner app
- `docs/` — specs (`lesson-flow-spec.md`, `voice.md`) and the decisions archive
- `.agents/` — the Backward Design subagent team and authoring skills

Authoring standards: `content/STYLE.md` (plain language and copy rules),
`docs/voice.md` (lesson voice). Authoring templates: `content/templates/`.

## Prerequisites

- Python 3.12+ with `pyyaml` and `jsonschema`
- Node.js 20+ (for `platform/app`)
- Docker (for the sandbox runner and the dev Postgres stack)
- API keys live in `~/.keelacademy.env` (chmod 600), never in the repo. See
  `.env.example` for the variable names. Source it per shell:
  `set -a; source ~/.keelacademy.env; set +a`

## How to run each part

Content validation (also runs as a pre-push gate and in CI):

```bash
python3 content/tools/validate.py          # units, examples, variants, personas
bash .githooks/pre-push                    # the full gate (activate once:
git config core.hooksPath .githooks        #   then it runs on every push)
```

Grading CLI (Layer 1 in Docker + LLM judge):

```bash
python3 platform/cli/runner/run_checks.py --repo <submission-repo> --checks <checks.yaml>
python3 platform/cli/grader/judge.py --rubric <v1.yaml> --submission <dir>
```

Full dev stack (Postgres, fake Stripe, fake LLM upstream, proxy, enroll,
reader, practice, seeded app wiring), then the learner app:

```bash
bash platform/dev-up.sh                    # starts everything, logs in /tmp/keel-dev-logs
cd platform/app && npm install && npm run dev
bash platform/dev-down.sh                  # teardown
```

Learner app checks:

```bash
cd platform/app && npm run test            # typecheck + eslint
npm run build                              # production build
```

Grading CLI unit tests:

```bash
cd platform/cli && python3 -m pytest tests -q
```

Production hosting (the grading host: Docker, Postgres, the seven services as
systemd units, Caddy TLS, backups):

```bash
# on a fresh Ubuntu 24.04 VM — see scripts/provision/README.md
cd scripts/provision && sudo bash 10-docker.sh   # then 20..60 in order
```

## Where the docs are

Start with `AGENTS.md` (how to pick the project up), then `build-state.md`
(where we are), `build-plan.md` (how we build), `school-architecture.md`
(what we build). The lesson design contract is `docs/lesson-flow-spec.md`.
Every decision ever logged is in `build-state.md` (recent) and
`docs/decisions/` (archive).
