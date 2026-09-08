# platform/grading — grading core service

Stage 1: Postgres datastore (S1.1), webhook intake (S1.2), exactly-once queue
worker (S1.3), sandboxed execution of untrusted student code (S1.4), LLM
proxy with per-student budgets (S1.5), end-to-end wiring (S1.8).
Stage 2: read-only reader for the learner app (S2.4), identity bridge +
Stripe Checkout enrollment (S2.5), rebate state machine (S2.6).

## Layout

- `schema/0001_init.sql` — forward-only migrations; fresh-apply per number,
  idempotency not required.
- `enroll/` — S2.5 enrollment service + the offline fake Stripe.
- `scripts/smoke-schema.sh` — spins up a scratch `postgres:16-alpine` on a
  random free port, applies the schema, runs `scripts/smoke.sql` proof checks,
  always removes the container.

## Table shapes

| table | purpose | key constraints |
|---|---|---|
| `students` | learner identity | `email` UNIQUE NOT NULL; `external_auth_id` UNIQUE NULL (for S2.5 managed auth) |
| `events` | append-only spine of the event-driven design | `seq bigserial UNIQUE` = total order; `type` + `payload jsonb` |
| `submissions` | one push of one commit for one unit | `UNIQUE (student_id, unit_id, commit_sha)` — same commit + unit is one submission; `status` CHECK `queued\|grading\|graded\|error` |
| `verdicts` | the graded outcome | `submission_id BIGINT UNIQUE NOT NULL` — **one verdict per submission, ever** |
| `progress` | per-unit gate state | `UNIQUE (student_id, unit_id)`; `state` CHECK `locked\|unlocked\|passed`; upsert-friendly |

`timestamptz` everywhere. Deletion policy: deleting a student cascades to
their submissions and progress; `verdicts.submission_id` is `ON DELETE
RESTRICT` — verdicts are audit-grade history and cannot be orphaned. Events
have no FK by design (they reference the world loosely, via `payload`).

Indexes: `events (type, occurred_at)` for per-type replay/catch-up,
`submissions (student_id)`, `progress (student_id)`.

## Exactly-once design intent

S1.3's worker may crash mid-grade, retry, or run duplicate jobs — the schema
doesn't care. `verdicts.submission_id UNIQUE` means the *database*, not
application memory, prevents a second verdict: whichever transaction inserts
first wins; every other attempt fails with a unique violation the worker
treats as "already graded, ack and move on." The smoke test proves this by
inserting a second verdict and asserting the constraint fires. Likewise
`submissions UNIQUE (student_id, unit_id, commit_sha)` makes webhook delivery
retries naturally idempotent at intake.

## How S1.2 webhook intake will map push events

The GitHub webhook receiver will validate a push payload, resolve the pusher
to a `students` row (via email or `external_auth_id`), and — inside one
transaction — insert a `submissions` row keyed by
`(student_id, unit_id, commit_sha)` with status `queued` (using
`INSERT ... ON CONFLICT DO NOTHING` so redelivered webhooks and force-pushes
of the same commit are absorbed), then append a `submission.created` event
whose payload carries the submission id. The queue worker in S1.3 consumes
`submission.created`, flips status `queued → grading → graded`, writes the
single `verdicts` row, and emits `verdict.issued`; the gate engine later
consumes `verdict.issued` to upsert `progress` and emit `gate.unlocked`.

## Intake (S1.2)

`intake/server.py` is a stdlib HTTP server exposing `POST /webhook/github`
for GitHub-style push payloads.

**Signature scheme.** Byte-for-byte GitHub's: the `X-Hub-Signature-256`
header must equal `sha256=` + hex HMAC-SHA256 of the **raw request body**
with the secret from env `KEEL_WEBHOOK_SECRET` (env only — never disk, never
hardcoded, never logged). Verification uses `hmac.compare_digest` and runs
**before any JSON parsing**; a bad or missing signature returns 401 with no
database writes.

**Mapping.** The repo name must match `keel-<unit-id>-<anything>` (e.g.
`keel-3.2.1-smith` → unit `3.2.1`, unit id must match `^\d+\.\d+\.\d+$`, else
422). The pusher is resolved by push-commit email against `students.email`.
Unknown email → 200 (so GitHub doesn't retry), no submission, but an
`intake.unknown_pusher` event carrying email/repo/sha.

**Idempotency contract.** Known pusher → one transaction inserts the
submission `(student_id, unit_id, commit_sha, repo_url, pusher_email, status
'queued')` with `ON CONFLICT DO NOTHING` on the UNIQUE triple and appends a
`submission.created` event (payload carries the submission id) **only when
the row was newly inserted**. Redelivered webhooks for the same commit return
the same submission id, produce no second event, and stay 2xx. Two students
pushing the same unit + commit are two submissions — the key is the triple,
not the pair.

**S1.3 handoff.** The queue worker consumes `submission.created` events,
flips `queued → grading → graded`, and writes the single per-submission
verdict. Real GitHub wiring (public tunnel, managed OAuth identity) is pilot
infrastructure / S2.5, not Stage-1 code; local payloads signed with a test
secret exercise the identical HMAC path.

**Database access.** stdlib-only, so the server shells out to a
psql-compatible command from env `KEEL_DB_CMD` (e.g.
`docker exec -i <container> psql -U smoke -d grading`); each request is one
`BEGIN`/`COMMIT` session. The secret and DB command never leave env.

```bash
KEEL_WEBHOOK_SECRET=... KEEL_DB_CMD="... psql ..." python3 intake/server.py
```

## Queue worker (S1.3)

`worker.py` is the stdlib queue worker that consumes queued submissions and writes exactly-once verdicts, surviving crashes, restarts, and concurrent duplicates.

### State machine: Claim → Grade → Write → Finish

1. **CLAIM (atomic, race-free):** Single transaction using `SELECT FOR UPDATE SKIP LOCKED` on `submissions WHERE status = 'queued' ORDER BY id ASC LIMIT 1`, transitioning `status` from `'queued'` to `'grading'` and returning the claimed row. Two workers never claim the same row; if another worker is evaluating a row, `SKIP LOCKED` skips past it.
2. **GRADE (deterministic stub):** Computes verdict deterministically: `pass` if `sha256(commit_sha)` is even, else `fail`. Sleeps for `KEEL_GRADE_SLEEP_S` (default 1.0s) to simulate grading and provide testable kill/crash windows. Output is structured verdict JSON: `{"overall": ..., "criteria": [], "stub": true}`.
3. **WRITE (database-enforced exactly-once):** Executes `INSERT INTO verdicts (submission_id, ...) VALUES (...) ON CONFLICT (submission_id) DO NOTHING RETURNING ...`. If a row is returned, this worker won the insert. If an `ON CONFLICT` occurs (due to a redelivery, duplicate job, or retry after crash), the worker reads back the existing verdict row and reconciles. The database's `verdicts.submission_id UNIQUE` constraint arbitrates exactly-once writes; memory state is never trusted.
4. **FINISH (idempotent wrap-up):** Single transaction that updates `submissions SET status = 'graded' WHERE id = ...` and appends a `verdict.issued` event to `events` **only if** no event with this `submission_id` exists yet (`WHERE NOT EXISTS (SELECT 1 FROM events WHERE type = 'verdict.issued' AND payload->>'submission_id' = ...)`).

### Crash recovery and reaper semantics

- **Reaper on each loop:** Prior to claiming, the worker runs a reaper sweep:
  - **Grading with verdict:** Submissions stuck in `status = 'grading'` that already have a row in `verdicts` (e.g. worker was SIGKILLed between WRITE and FINISH) are advanced to `'graded'` and emitted to `verdict.issued` via the idempotent finish path.
  - **Stale grading without verdict:** Submissions stuck in `status = 'grading'` older than `KEEL_STALE_AFTER_S` seconds without any verdict row (e.g. worker died mid-grade) are atomically reset to `status = 'queued'`.
- **Poison redelivery:** If an already-graded submission is forced back to `'queued'`, the worker claims it, attempts to write the verdict (which hits `ON CONFLICT DO NOTHING`), reads back the existing verdict, updates status back to `'graded'`, and emits no duplicate event.
- **Modes:** Continuous polling loop or one-shot mode (`KEEL_WORKER_ONCE=1`), which drains the queue and exits 0 cleanly. Errors on a single submission log to stderr and set `status = 'error'` without crashing the worker process.

### S1.4 handoff

In S1.4, `grade_stub(commit_sha)` will be replaced by the sandboxed runner (`platform/grading/sandbox/` or runner integration) executing untrusted student code in isolated containers with CPU/memory/time caps and network restrictions.

## Sandbox runner (S1.4)

`sandbox/runner.py` executes **untrusted** student code in a capped,
networkless, ephemeral container. Containment is the product: the run's job
is to report what happened while guaranteeing the host is untouched. Stdlib
Python only; image is `python:3.12-alpine` (pulled, never built).

```bash
python3 runner.py <submission_dir> [--cmd "python3 /submission/<file>"]
```

With no `--cmd`, the submission dir must contain exactly one top-level `.py`.

### Hardening flags (every run, no exceptions)

| flag | reason |
|---|---|
| `--network none` | v1 allowlist is **empty** — student code gets zero egress; the S1.5 proxy becomes its only sanctioned external touch point |
| `--read-only` | immutable rootfs — writes anywhere outside tmpfs fail closed (`EROFS`) |
| `--tmpfs /tmp:size=64m,noexec,nosuid` | scratch space that vanishes with the container; can't hold executables or setuid tricks |
| `--tmpfs /work:size=64m,noexec,nosuid` | size-capped writable cwd so programs can work without touching `/submission` |
| `--cap-drop ALL` | no kernel capabilities whatsoever |
| `--security-opt no-new-privileges` | setuid/setcap privilege escalation impossible |
| `--pids-limit 64` | fork bombs exhaust the cgroup's pid slots long before the host feels anything |
| `--memory 256m --memory-swap 256m` | hard 256m with swap disabled → over-allocation ends in a clean kernel OOM kill, never host thrash |
| `--cpus 0.5` | half a core — busy loops cannot starve co-tenants |
| `--user 1000:1000` | non-root uid/gid inside the container |
| `-w /work` | cwd is the writable tmpfs, never the read-only submission mount |
| `-v <dir>:/submission:ro` | submission mounted READ-ONLY — code can read itself, never write itself or the host directory |
| *(no `--rm`)* | container must survive exit for the `OOMKilled` post-mortem inspect; removal is guaranteed by a `finally` block instead |

Ephemeral lifecycle: each run creates a uniquely named container
(`keel-sbx-<hex>`), runs, inspects `State.OOMKilled`, then removes it on
**every** path — success, timeout, and error alike (`rm -f` in `finally`;
the smoke harness additionally sweeps any `keel-sbx-*` stragglers in an
EXIT trap).

Wall-clock cap: enforced runner-side via subprocess timeout —
`KEEL_SANDBOX_TIMEOUT_S`, default 10s. On expiry the container is killed and
status is `timeout`. The post-kill wait is bounded too, so the cap holds
absolute even if the docker daemon stalls.

### Result contract

One JSON line on stdout:

```json
{"status": "ok", "exit_code": 0, "wall_s": 1.283, "oom_killed": false,
 "output_tail": "hello from the keel sandbox\n"}
```

| field | meaning |
|---|---|
| `status` | `ok` = process finished within caps (exit 0 **or** a clean non-zero program exit — a contained crash like a denied network call means caps held); `timeout` = runner wall cap fired; `oom` = cgroup memory kill per docker inspect; `killed` = died by signal (container exit ≥128); `error` = container never ran / post-mortem failed |
| `exit_code` | container exit code, or `null` when it was killed before exiting |
| `wall_s` | measured wall time of the run |
| `oom_killed` | verbatim from `docker inspect .State.OOMKilled` |
| `output_tail` | stdout+stderr captured separately, each tailed to ≤4000 chars, joined (stderr after a marker), re-tailed to ≤4000 |

Runner process exit codes: `0` = the run itself completed (any containment
outcome counts); `2` = runner infrastructure failure (no usable docker CLI,
pull failure, bad args) with **no** JSON line.

Smoke proof: `scripts/smoke-sandbox.sh` runs six adversarial fixtures
(benign control / phone-home / fork bomb / sleep-forever / fs escape /
mem-hog) through the runner and asserts each containment outcome, including
that f5 leaves the host submission dir untouched — PASS/FAIL lines, non-zero
exit on any failure, trap cleanup of every container.

### S1.5 handoff

Today the allowlist is empty: student code touches nothing external. At
S1.5 the LLM proxy with per-student budgets becomes the **only** permitted
external touch point for graded runs — reachable only through platform
credentials injected at proxy time, never baked into submissions. Wiring
this runner into `worker.py`'s GRADE step happens after S1.5 defines what a
graded run may touch; until then the runner stands alone, proven by its own
fixtures.

## LLM proxy (S1.5)

`proxy/server.py` is the **only** external touch point student code will
ever get: an OpenAI-compatible chat-completions endpoint
(`POST /v1/chat/completions`, messages in / `choices` + `usage` out) that
enforces per-student token budgets backed by the `budgets` table
(`schema/0003_budgets.sql`: `tokens_cap` / `tokens_used` per student,
cascading with the student row). Stdlib only; upstream is reached via
urllib with the platform key from env `OPENAI_API_KEY` (env only — never
logged, never echoed in a response).

```bash
KEEL_PROXY_PORT=8788 \
KEEL_PROXY_UPSTREAM_URL=https://api.openai.com/v1 \
KEEL_DB_CMD="... psql ..." python3 proxy/server.py
```

**Endpoint contract.** Requests carry `X-Keel-Student-Id` (a numeric
`students.id`) and an OpenAI-shaped JSON body. Disallowed model (`gpt-4o-mini`,
`gpt-4.1`, `o3` only) → 400. Unknown student / missing budget row → 404.
Budget exhausted → 429 with `error.code = "budget_exceeded"`. Upstream
failure → 502, nothing charged. Success → the upstream body returned
unchanged. **Placeholder:** the header carries a caller-supplied student id
until per-run token binding lands at sandbox-wiring time — then it becomes
a short-lived per-run token resolved server-side, so student code never
names its own identity.

**Budget accounting.** The pre-check (`tokens_used >= tokens_cap` → 429 +
append a `proxy.budget_exceeded` event with payload `student_id`, `model`,
`tokens_used`, `tokens_cap` — and the call is **never forwarded**) and the
charge (atomic SQL increment of `tokens_used` by the response's
`prompt_tokens + completion_tokens`, only after a 200 from upstream) are
both SQL. A per-student in-process lock serializes read → forward → charge,
so the documented **overshoot bound** holds exactly: `tokens_used` may
exceed `tokens_cap` by at most the usage of the last accepted call — never
`(N-1) × usage` under a concurrent burst. The database remains the
enforcement authority; the lock only prevents interleaving.

**Cut-off flagging path.** A cut-off call leaves three traces: the 429 with
`budget_exceeded` to the caller, the append-only `proxy.budget_exceeded`
event on the spine (consumable by future analytics/retention), and an
unchanged `/__count`-style upstream footprint of zero — proven in the smoke
harness by asserting the fake upstream's request counter did not move.

**Fake upstream.** `proxy/fake_upstream.py` is the project's
offline-determinism convention applied to the proxy: a stdlib fake OpenAI
that echoes a canned assistant message with usage from env
(`KEEL_FAKE_PROMPT_TOKENS` default 50, `KEEL_FAKE_COMPLETION_TOKENS`
default 250) and exposes `GET /__count` so proofs can show exactly which
calls were forwarded. Every deterministic check runs against it, zero cost.

**S1.6 handoff.** The proxy stands alone this milestone; wiring it into the
sandbox/worker GRADE step comes next. When that lands, the sandbox's empty
network allowlist gains exactly one destination (the proxy), the
`X-Keel-Student-Id` placeholder is replaced by per-run token binding, and
rubric-version bookkeeping (S1.6) starts tagging the judge calls that flow
through this same proxy.

## End-to-end wiring (S1.8)

`worker.py`'s GRADE step now produces real verdicts: an intake submission
flows through Layer 1 (deterministic checks in the S1.4 sandbox) and Layer 2
(the rubric judge calling the model **through the S1.5 proxy**, so
per-student budgets apply) into a verdict row tagged with the rubric version
the resolver picked and the S1.7 trace records for the judge calls.

### The GRADE step

1. **Resolve the rubric.** `resolve_active_rubric(unit_id)` (subprocess into
   `grader.rubric_version`; the worker itself stays stdlib-only) picks the
   highest `content/rubrics/<unit>/vN.yaml`. Rubric edits flow into verdicts
   with zero code changes.
2. **Layer 1 — `platform/grading/layer1.py`.** Loads the unit's checks file
   (via `unit.yaml` → `verify.deterministic_checks`), stages a copy of the
   submission with an injected offline `proxy`/`CONFIG`/`SYSTEM_PROMPT`
   mock (see below), and runs every check through the hardened
   `sandbox/runner.py` — one ephemeral networkless container per check, per
   check wall cap (`timeout_s` on a check, else `--timeout`, default 60s).
   `KEEL_SANDBOX_IMAGE` swaps the image (default `python:3.12-alpine`; use
   `keel-runner:0.1` when checks import pytest/pydantic) with all hardening
   flags unchanged. Results land in `verdict_json.layer1`.
3. **Layer 2 — the judge via the proxy.** `python -m grader.judge` runs with
   `KEEL_LLM_BASE_URL=<KEEL_PROXY_URL>/v1` and
   `KEEL_LLM_STUDENT_ID=<submission's student id>`, so the judge's HTTP call
   carries `X-Keel-Student-Id` and the proxy's pre-check/charge budget
   semantics apply to grading calls unchanged. `grader/llm.py` gained exactly
   this: a base-URL override, the identity header, and no key requirement
   when routed (the proxy holds the platform key). No judge logic forked.
4. **Verdict row.** `overall` from the judge (recomputed by the judge, never
   the model's own arithmetic); `rubric_id`/`rubric_version` from the
   resolver; `verdict_json` carries `layer1` (per-check results),
   `judge` (the full judge verdict), and `trace` (the S1.7 trace-log path,
   this grading call's `call_id`, and the matching records' bookkeeping
   fields). Write path unchanged: `ON CONFLICT (submission_id) DO NOTHING`.

**Budget-blocked outcome (documented choice).** When the proxy answers 429
`budget_exceeded`, the judge exits 3, and the worker records
`submissions.status = 'error'` plus a `grade.budget_blocked` event — and
writes **no verdict row**: budget exhaustion is not a grading outcome, and
leaving the verdict slot free means a regrade after a budget top-up still
resolves to exactly one verdict via the unchanged conflict path. The worker
loop never crashes on it. The proxy simultaneously appends its own
`proxy.budget_exceeded` event.

**Submission files.** `KEEL_SUBMISSIONS_DIR` names a directory laid out
`<dir>/<submission_id>/` with the checked-out submission (the intake/
checkout stage places it there; real repo checkout is pilot infrastructure).
When unset, the worker falls back to the S1.3 sha-parity stub so the S1.3
proof harness runs without docker/LLM plumbing.

**Layer-1 mock injection.** Golden-set submissions reference `proxy`,
`CONFIG`, and `SYSTEM_PROMPT` as platform-injected names. `layer1.py` stages
the submission into the container's writable tmpfs plus a `sitecustomize.py`
that installs a deterministic offline mock into `builtins` (even-numbered
notes → schema-valid JSON, odd-numbered → garbage, exercising the fallback
path). `PYTHONPATH=/work` is what makes `sitecustomize` load — the
interpreter sets `sys.path[0]` only after site init, so a cwd-local
`sitecustomize` is never auto-imported.

**S1.3 properties preserved.** Claim/finish/reap/reaper logic is untouched:
kill-mid-grade still resolves to exactly one verdict via recovery, the
`ON CONFLICT` write path is unchanged, and the worker remains single-writer
per queue. `KEEL_GRADE_SLEEP_S` survives as a crash-window knob, now placed
immediately before the judge call (kill-mid-judge proofs).

### Wiring smoke

```bash
./scripts/smoke-wiring.sh                      # deterministic (a)-(d), offline
KEEL_WIRING_LIVE=1 ./scripts/smoke-wiring.sh   # + one real judge call
```

Scratch postgres (0001+0002+0003) + fake OpenAI upstream (canned rubric-3.2.1
verdict, 5s hold so kill-mid-judge is testable) + proxy + a real golden
submission (`s01-textbook` + the variant corpus) graded with the real rubric
v1 through the real Layer-1 sandbox (image `keel-runner:0.1`). Checks:
(a) real verdict — rubric v1, 8 layer-1 results (the fixture's deterministic
5 pass / 3 fail; the three e2e flag-style checks don't match the golden
extractors' positional CLI — a known content inconsistency, recorded not
papered over), judge verdict via the proxy, worker-tagged trace records,
budget charged exactly the call's usage; (b) kill the worker while the judge
call is in flight → `grading`/0 verdicts, restart → exactly one verdict;
(c) exhausted-budget student → 429 path: `status='error'` +
`grade.budget_blocked` event, no verdict-as-pass, nothing charged or
forwarded, worker exits 0; (d) drop a temp v2 rubric → fresh grade resolves
v2, delete it → v1 again. Always kills servers, sweeps sandbox containers,
removes the temp rubric, scratch dirs and the database container.

## Read-only reader (S2.4)

`reader/server.py` is the learner app's only window into the grading store:
a stdlib HTTP server exposing `GET /submissions/<id>` (one JSON document:
submission row + verdict + the submission's events) and `GET /healthz`.
The app renders the verdict page from it read-only.

```bash
KEEL_READER_PORT=8790 \
KEEL_DB_CMD="... psql ..." python3 reader/server.py
```

**Why an endpoint and not a Postgres driver in the app.** The house DB
convention is `KEEL_DB_CMD` — a shlex-split, psql-compatible *command*
(usually `docker exec -i <container> psql ...`), not a connection URL. A
driver in `platform/app` cannot honor it without inventing a second
convention (a `KEEL_DB_URL` connection string) and shipping DB credentials
into the app's environment — the opposite of "no secret in app code". The
deployment split (app on Vercel, grading core on its own host) makes HTTP
the natural boundary anyway: the app holds only `KEEL_READER_URL`, a plain
base URL with no credential, and every secret stays in the grading core's
env. Read-only is enforced by construction: the module issues SELECT
statements only, wrapped in `BEGIN`/`ROLLBACK`.

**Capability-URL model (S2.4 interim, closed at S2.5).** The endpoint never
lists submissions and answers only about rows the caller names. Since S2.5
the app additionally requires a signed-in session linked to the submission's
student before rendering a verdict page, so the sequential id alone is no
longer the access token; the reader stays deliberately dumb (it cannot
authenticate) and the gate lives in the app + enroll bridge.

## Enrollment service (S2.5)

`enroll/server.py` is the write-side boundary between the learner app and
the grading store: managed-auth identities are linked to `students` rows
(the enrollment bridge), Stripe Checkout sessions are created for unit
enrollment, and the `checkout.session.completed` webhook activates the
enrollment idempotently. Stdlib only, same conventions as intake/reader.

```bash
KEEL_ENROLL_PORT=8791 \
KEEL_DB_CMD="... psql ..." \
KEEL_ENROLL_SECRET="<app token>" \
STRIPE_SECRET_KEY=sk_test_... \
KEEL_STRIPE_API_URL=https://api.stripe.com/v1 \
KEEL_STRIPE_WEBHOOK_SECRET=whsec_... \
python3 enroll/server.py
```

**Routes.** App-facing routes authenticate with the `X-Keel-App-Token`
header (the shared `KEEL_ENROLL_SECRET`, held in the app's server env only):

| route | purpose |
|---|---|
| `GET /healthz` | liveness, no token |
| `POST /auth/bridge` | auth identity → students row (see below) |
| `GET /students/<id>/profile` | row + enrollments + budget |
| `GET /students/<id>/submissions` | the student's own submissions (auth-gated list for /me) |
| `GET /price?unit=<id>` | configured price in cents (`KEEL_PRICE_CENTS_<id>` / default) |
| `POST /checkout/session` | create a Stripe Checkout session (inline `price_data`) |
| `GET /checkout/status?stripe_session_id=` | pending/completed + enrolled |
| `POST /webhook/stripe` | Stripe webhook, signature-verified |

**Identity bridge.** Match by `external_auth_id`; else claim the existing
row with the same email and a NULL `external_auth_id` (a student who pushed
submissions before signing up keeps their history); else insert a new row.
An email already linked to a different auth account is a 409, never a silent
merge.

**Stripe calls.** Session creation POSTs the same form-encoded fields the
real API expects (`line_items[0][price_data][...]`, metadata with
student/unit, `client_reference_id`) to `KEEL_STRIPE_API_URL` with the
bearer key from env. Point the URL at `enroll/fake_stripe.py` and the
identical code path runs offline, no credentials, no network.

**Webhook verification + idempotency.** The `Stripe-Signature` header
(`t=<ts>,v1=<hex>`) is verified with `hmac.compare_digest` over
`"<t>." + raw_body` BEFORE any JSON parsing (the intake rule), with a
configurable timestamp tolerance (`KEEL_STRIPE_TOLERANCE_S`, default 300;
0 disables for delayed-replay proofs). A replayed
`checkout.session.completed` cannot double-enroll: `enrollments UNIQUE
(student_id, unit_id)` with `ON CONFLICT DO NOTHING` decides, and the
`enrollment.activated` event is appended only when the enrollment row was
newly inserted. First enrollment also provisions the student's budget row
(cap from `KEEL_DEFAULT_BUDGET_TOKENS`), because the grading proxy 404s
students without one.

**Schema 0004** (additive): `checkout_sessions` (one row per created
session, `stripe_session_id` UNIQUE, status pending → completed via a
guarded update) and `enrollments` (one per student+unit, ever).

**Fake Stripe** (`enroll/fake_stripe.py`): mirrors the checkout-session
create call, serves a hosted pay page at `/pay/<id>`, and on payment
delivers the signed webhook then 302s to `success_url` with
`{CHECKOUT_SESSION_ID}` substituted — exactly the real sequence, offline.
`GET /__count` exposes the session count for proofs.

The learner-app side (offline auth fake, Clerk wiring, /me, checkout pages)
and the production wiring steps live in `platform/FOUNDER-WIRING.md`.

## Rebate state machine (S2.6)

`rebate/machine.py` consumes gate events from the append-only `events` spine
(the same spine the verdict pipeline writes; no new grading logic) and drives
the rebate ledger: `pending -> earned -> (paid | forfeited)` plus the timed
`pending -> expired`. Policy from school-architecture.md §8: a configurable
portion (default 15, band 15–20 via `KEEL_REBATE_PCT`) of the one-time price
(the same `KEEL_PRICE_CENTS_*` knobs the enroll service reads), earned only
on **verified gate passage** inside the configured window — never on
self-reported completion.

**Published event contract** (S2.7's gate engine emits these onto the spine;
harnesses fake them deterministically by inserting identical rows):

| event | payload | effect |
|---|---|---|
| `gate.pledged` | `student_id, gate_id, unit_id, window_days?` | creates the pending ledger row (amount frozen at pledge time) |
| `gate.passed` | `student_id, gate_id, unit_id, passed_at?` | pending -> earned when the unit matches and the passage is inside the window |

The machine emits its own spine events for every transition
(`rebate.pledged`, `rebate.earned`, `rebate.expired`, `rebate.paid`,
`rebate.forfeited`) plus `rebate.rejected` diagnostics (wrong unit, no
pledge, unknown gate/student, out-of-window passage, terminal state) so
attempts that changed nothing are still auditable. Gate registry comes from
`KEEL_REBATE_GATES` (default `phase-5-integration,capstone`); window from
the event or `KEEL_REBATE_WINDOW_DAYS[_<GATE>]` (default 365).

**Invariants.** `rebates UNIQUE (student_id, gate_id)` is the earn-once seed
(a rebate cannot be earned twice for the same gate); every UPDATE is guarded
on its from-state (no backwards moves — the `rebate_transitions` pair CHECK
is the state-machine graph enforced at the database level); expiry is a
deterministic timed sweep (`now() > window_ends_at`) run each poll pass. The
cursor (`rebate_cursor`) only moves forward; a crash replays at most one
pass of idempotent no-ops — a replayed `gate.passed` that already earned is
recognized by `earned_event_seq` and absorbed silently whatever the current
terminal status. `KEEL_REBATE_NOW` (ISO timestamp) overrides the machine
clock for deterministic proofs; leave unset in production.

**Schema 0005** (additive): `rebates` (one row per student+gate, ever;
`amount_cents` frozen at pledge), `rebate_transitions` (who/what/when for
every transition: actor, reason, source event seq, occurred_at),
`rebate_cursor`.

**No money moves.** `--mark-paid` / `--mark-forfeited` are runbook marks
that print a LEDGER ONLY banner; the actual refund is a manual / Stripe step
documented in `platform/FOUNDER-WIRING.md`. `--ledger [student_id]` dumps
the audit trail as JSON lines. The enroll service's
`GET /students/<id>/profile` gained a `rebates` array (additive), which the
learner app renders as the Rebate section on /me.

```bash
KEEL_DB_CMD="... psql ..." python3 rebate/machine.py   # poll loop
KEEL_REBATE_ONCE=1 ... python3 rebate/machine.py       # one pass (harnesses)
./scripts/smoke-rebate.sh                              # 43 deterministic checks
./scripts/demo-rebate.sh prove                         # full-stack /me demo
```

`smoke-rebate.sh` covers earn-once, cursor-reset replay, duplicate passage
events, out-of-window rejection + timed expiry (with and without a passage),
retroactive-earn refusal after expiry, wrong-unit rejection, unknown
gate/student/no-pledge diagnostics, runbook marks refusing backwards moves,
full-replay state stability, and ledger auditability. `demo-rebate.sh`
stands up the app stack (postgres 0001..0005, fake Stripe, enroll, Next dev)
and walks two students through sign-up, payment, pledge, verified passage,
replayed event, expiry, and the payout mark — ending with /me showing
pending/earned/expired/paid states.

## Running the smoke tests

```bash
./scripts/smoke-schema.sh
```

Requires only Docker; no host Postgres client, no Python dependencies beyond
stdlib (used to grab a free port). No secrets, no network beyond the
`postgres:16-alpine` pull.

```bash
./scripts/smoke-intake.sh
```

Same scratch-container pattern plus: applies 0001 + 0002, seeds a student,
starts `intake/server.py` with a test secret that exists only in the
harness's process env, and runs five checks (a)–(e) — signed push, exact
redelivery, tampered body, unknown pusher, second student same unit+sha.
Always kills the server and removes the container.

```bash
./scripts/smoke-worker.sh
```

Spins up a scratch `postgres:16-alpine` container, applies schema 0001 + 0002,
seeds a student, and runs four checks (a)–(d) proving happy path, SIGKILL
mid-grade crash recovery, concurrent worker race (with zero error noise from
the losing worker), and poison redelivery idempotency. Always cleans up containers
and processes.

```bash
./scripts/smoke-sandbox.sh
```

Builds no database: pulls (or finds) `python:3.12-alpine` and proves the six
sandbox containment outcomes — seven PASS lines including the leftover-
container sweep, non-zero exit on any failure, every `keel-sbx-*` container
removed on every exit path including timeouts.

```bash
./scripts/smoke-proxy.sh                # deterministic (a)-(e), offline
KEEL_PROXY_LIVE=1 ./scripts/smoke-proxy.sh   # + live (f): one real
                                          # gpt-4o-mini call, cost < $0.01
```

Same scratch-container pattern plus: applies 0001 + 0002 + 0003, seeds
alice (cap 5000) / bob (cap 300) / carol (cap 400), starts the fake
upstream + proxy on random free ports with the upstream pointed at the
fake, and runs checks (a)–(e) — accepted call charged exactly its usage,
second-call cutoff with no forwarding and one `proxy.budget_exceeded`
event, unknown student 404, disallowed model 400, and a 5-call concurrency
burst satisfying the overshoot bound with `/__count` reconciling 200s
forwarded / 429s never forwarded. The LIVE check (f) runs only when
`KEEL_PROXY_LIVE=1` (source `~/.keelacademy.env` first); always kills both
servers and removes the container.

```bash
./scripts/smoke-enroll.sh
```

S2.5 enrollment proof, fully offline: scratch postgres (0001..0004), the
fake Stripe, and the enroll service pointed at it. 43 checks cover the app
token gate, the identity bridge (new identity / claim-by-email / 409 on
conflict), checkout session creation through the fake (plus the explicit
stripe_not_wired error when no key is configured), the full pay -> signed
webhook -> enrollment loop with budget provisioning, webhook replay
idempotency (exactly one enrollment and one event, completed_at untouched),
tampered + stale signature rejection with zero writes, unknown sessions
logged not enrolled, second-checkout absorption, and the student-scoped
reads. Always kills servers and removes the container.

```bash
./scripts/demo-enroll.sh setup|prove|teardown
```

Full-stack S2.5 demo: the scratch stack above plus the S2.4 reader and the
learner app dev server (setsid daemons, persists until teardown). prove
drives the real app over HTTP: sign-up through the actual no-JS form posts
(the rendered $ACTION_ID fields), the /me and verdict-page gates,
cross-account 404, the enroll button through the app's server action into
the fake hosted pay page, the signed webhook, and the replay (32 checks).
Test placeholders only; production wiring lives in
platform/FOUNDER-WIRING.md.
