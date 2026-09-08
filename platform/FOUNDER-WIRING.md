# Founder wiring runbook — managed auth + Stripe (S2.5)

Everything in S2.5 runs credential-free against deterministic offline fakes.
This runbook is the exact set of accounts, environment variables, and webhook
registrations that turn the same code paths into production wiring. Nothing
here is optional guesswork: each fake mirrors one real call, listed below.

## Rebate payout runbook (S2.6) — MANUAL STEP, no automatic money movement

The rebate machine (`platform/grading/rebate/machine.py`) keeps a ledger
only. When a rebate reaches status `earned`, the platform records money it
owes the student; it never moves money. Paying out is this two-step manual
process:

1. **Issue the actual refund in Stripe.** Dashboard: Payments -> select the
   original enrollment payment -> Refund, amount = the rebate's
   `amount_cents` (or the equivalent transfer if the payment method no
   longer supports refunds). Copy the refund id (`re_...` or `pi_...`).
2. **Mark the ledger paid**, so the student's /me and the audit trail agree:

   ```bash
   KEEL_DB_CMD="... psql ..." python3 platform/grading/rebate/machine.py \
       --mark-paid <rebate_id> \
       # KEEL_REBATE_REASON="stripe refund re_123"   (env, recorded on the transition)
       # KEEL_REBATE_ACTOR="founder"                 (env, who did it)
   ```

   The command refuses anything that is not a forward `earned -> paid`
   transition, and prints a LEDGER ONLY banner. `--mark-forfeited` works the
   same way for the rare case where a credit is given up (for example a full
   refund was issued outside the rebate system).

Run this check on a cadence (weekly is plenty at pilot size):

```bash
KEEL_DB_CMD="... psql ..." python3 platform/grading/rebate/machine.py --ledger
```

Every `earned` row in that output is money owed; every transition line
carries who, what, and when. Students see the same status on /me, including
the note that a person issues the refund, which is why an earned credit can
show up before the money arrives.

Rebate machine production env (grading host, alongside the enroll service):

    KEEL_DB_CMD="docker exec -i <postgres-container> psql -U <user> -d grading"
    KEEL_REBATE_PCT=15                     # architecture band is 15-20
    KEEL_REBATE_GATES=phase-5-integration,capstone
    KEEL_REBATE_WINDOW_DAYS=365            # default; per-gate override:
                                           # KEEL_REBATE_WINDOW_DAYS_CAPSTONE=...
    KEEL_PRICE_CENTS_DEFAULT=4900          # same knobs the enroll service reads
    KEEL_REBATE_POLL_S=2                   # event-poll + expiry-sweep interval

`KEEL_REBATE_NOW` (an ISO timestamp) overrides the machine clock everywhere
and exists for deterministic proofs and backdated audits; leave it unset in
production. The gate events the machine consumes (`gate.pledged`,
`gate.passed`) are emitted by the S2.7 gate engine onto the same events
spine the verdict pipeline writes; until S2.7 lands, nothing emits them in
production, so the machine simply idles.

## What the fakes stand in for

| Offline fake | Real call it mirrors |
|---|---|
| `platform/grading/enroll/fake_stripe.py`, `POST /v1/checkout/sessions` | `POST https://api.stripe.com/v1/checkout/sessions` (form-encoded body, bearer key, `{id, url}` response) |
| The fake's hosted page `GET/POST /pay/<id>` | Stripe's hosted checkout page at `checkout.stripe.com/c/pay/...`, including the `302` to `success_url` with `{CHECKOUT_SESSION_ID}` substituted |
| The fake's signed event delivery | Stripe's `checkout.session.completed` webhook: `POST <your webhook URL>` with header `Stripe-Signature: t=<ts>,v1=<hex HMAC-SHA256(whsec, "<t>." + body)>` |
| The app's offline auth (`lib/auth.ts`, mode `"offline"`) | Clerk: sign-up, sign-in, sign-out, and session via `@clerk/nextjs` (already installed and wired behind `authMode()`) |

## Accounts to create

1. **Clerk** (dashboard.clerk.com) — one application. Free tier is enough for
   the pilot. From its API keys page you need:
   - Publishable key (`pk_live_...` or `pk_test_...`)
   - Secret key (`sk_...` — treat as a server secret)
2. **Stripe** (dashboard.stripe.com) — one account, **test mode first**:
   - Secret key (`sk_test_...`, later `sk_live_...`)
   - A webhook endpoint (below) whose signing secret starts `whsec_...`

## Environment variables

Nothing below is ever committed. `NEXT_PUBLIC_*` is exactly the one public
value (Clerk publishable key — public by design, identifies the instance
only); every other value stays server-side.

### Learner app (`platform/app`, e.g. Vercel project settings)

    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...   # public by design
    CLERK_SECRET_KEY=sk_...                    # server secret
    KEEL_READER_URL=https://<grading-host>/reader     # S2.4, unchanged
    KEEL_ENROLL_URL=https://<grading-host>/enroll
    KEEL_ENROLL_SECRET=<long random string>    # shared with the enroll service

**Build-time note:** `NEXT_PUBLIC_*` values are inlined at build time. Set the
Clerk keys BEFORE `next build` / the Vercel deploy, or the app builds in
offline mode (the runbook's dev fake) — you would see the "Offline
development sign-in" note on /sign-in, which is the tell.

### Enroll service (`platform/grading/enroll/server.py`, grading host)

    KEEL_ENROLL_PORT=8791
    KEEL_DB_CMD="docker exec -i <postgres-container> psql -U <user> -d grading"
    KEEL_ENROLL_SECRET=<same long random string as the app>
    STRIPE_SECRET_KEY=sk_test_...              # test mode first
    KEEL_STRIPE_API_URL=https://api.stripe.com/v1
    KEEL_STRIPE_WEBHOOK_SECRET=whsec_...       # from the webhook endpoint below
    KEEL_PRICE_CENTS_3_2_1=4900                # unit prices in cents
    KEEL_DEFAULT_BUDGET_TOKENS=100000          # grading budget per enrollment

    # Optional: webhook timestamp tolerance (seconds). Default 300, which
    # matches Stripe's SDK. Set 0 only for delayed-replay proofs.
    KEEL_STRIPE_TOLERANCE_S=300

## Webhook URL to register

In Stripe: Developers → Webhooks → Add endpoint.

    URL:      https://<grading-host>/webhook/stripe
              (route this path to the enroll service's own /webhook/stripe;
               a reverse proxy may prefix it — what matters is that the POST
               reaches enroll/server.py unchanged, raw body included)
    Event:    checkout.session.completed
    Signing secret: copy the whsec_... into KEEL_STRIPE_WEBHOOK_SECRET

Notes:
- The endpoint verifies the signature over the raw body before any parsing,
  and a replayed event cannot double-enroll (`enrollments` has
  `UNIQUE (student_id, unit_id)`; the completion event is appended only when
  the enrollment row was newly inserted — proven in
  `scripts/smoke-enroll.sh`).
- The service binds 127.0.0.1 by default. Production needs a TLS-terminating
  reverse proxy in front (same pilot-infra step as the intake webhook).
- Test it end to end with Stripe's CLI:
  `stripe trigger checkout.session.completed` (needs a session you created,
  or the unknown-session diagnostic event appears — by design).

## Auth provider choice (recorded rationale)

**Clerk**, over Auth0 and Supabase Auth:
- First-class App Router support (provider, hosted `<SignIn>`/`<SignUp>`,
  `auth()` in server components) — least bespoke auth surface to own.
- Hosted sign-in/up pages mean the auth-critical UI is not hand-rolled here,
  matching the buy-don't-build decision in build-plan.md §3.
- JWKS-verified sessions; the secret key never leaves the server
  environment.
- Auth0's SDK and config surface aim at enterprise B2B scenarios we do not
  have; Supabase Auth would drag in Supabase's datastore when the grading
  Postgres is already the system of record.

## How identity links to grading records

Managed identity → `students` row happens in the enroll service's
`POST /auth/bridge` (called by the app on sign-in): match by
`external_auth_id`; else claim an existing row with the same email and a
NULL `external_auth_id` (so a student who pushed before signing up keeps
their submission history); else insert. An email already linked to a
different auth account is a 409, never a silent merge. Use the same email
for Clerk sign-up and git pushes and the two stay linked.

## Verifying the real wiring

1. App with Clerk keys set: /sign-in and /sign-up render Clerk's hosted UI
   (no "Offline development sign-in" note).
2. Sign up, then `/me` — it should show the Clerk email and a grading record
   number.
3. Enroll in unit 3.2.1 → the button redirects to a real
   `checkout.stripe.com` page (test mode) → pay with Stripe's test card
   `4242 4242 4242 4242` → back to `/checkout/return?...` showing the
   enrollment active, driven by the real webhook.
4. Replay safety: `stripe trigger` the same event twice; the grading store
   still holds exactly one enrollment row and one `enrollment.activated`
   event.

The offline proof harnesses (`scripts/smoke-enroll.sh`, `scripts/demo-enroll.sh`)
run the identical code paths against the fakes and should stay green before
and after the swap.
