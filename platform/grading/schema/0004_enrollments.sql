-- 0004_enrollments.sql — checkout + enrollment state (S2.5)
-- Additive only: two new tables, no change to any existing table.
-- Existing smoke harnesses apply 0001..0003 explicitly and are unaffected.

BEGIN;

-- One row per Stripe Checkout session the enroll service created.
-- stripe_session_id UNIQUE absorbs duplicate session creations; status moves
-- pending -> completed exactly once via the webhook's guarded UPDATE.
CREATE TABLE checkout_sessions (
    id                bigserial PRIMARY KEY,
    stripe_session_id text        NOT NULL UNIQUE,
    student_id        bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id           text        NOT NULL,
    amount_cents      integer     NOT NULL CHECK (amount_cents > 0),
    currency          text        NOT NULL DEFAULT 'usd',
    status            text        NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'completed', 'expired')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    completed_at      timestamptz
);

CREATE INDEX checkout_sessions_student_idx ON checkout_sessions (student_id);

-- One enrollment per (student, unit), ever. The UNIQUE constraint is the
-- webhook-replay idempotency seed (same pattern as verdicts.submission_id):
-- the database, not handler memory, decides that a replayed
-- checkout.session.completed cannot double-enroll.
-- status is 'active' only for now; S2.6 rebate logic adds its own state and
-- can widen this CHECK when it needs more values.
CREATE TABLE enrollments (
    id                  bigserial PRIMARY KEY,
    student_id          bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id             text        NOT NULL,
    status              text        NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active')),
    checkout_session_id bigint      REFERENCES checkout_sessions (id),
    enrolled_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (student_id, unit_id)
);

CREATE INDEX enrollments_student_idx ON enrollments (student_id);

COMMIT;
