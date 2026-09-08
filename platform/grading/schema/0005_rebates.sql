-- 0005_rebates.sql — rebate ledger + transitions + consumer cursor (S2.6)
-- Additive only: three new tables, no change to any existing table.
-- Existing smoke harnesses apply 0001..0004 explicitly and are unaffected.

BEGIN;

-- One rebate per (student, gate), ever. The UNIQUE constraint is the
-- earn-once seed (same pattern as verdicts.submission_id and enrollments
-- UNIQUE (student_id, unit_id)): the database, not machine memory, decides
-- that a replayed gate.pledged or gate.passed cannot create or earn twice.
-- amount_cents is frozen at pledge time (price x pct as of that moment) so
-- later price changes never mutate an outstanding promise. These are ledger
-- numbers only — no money ever moves through this table.
CREATE TABLE rebates (
    id                 bigserial PRIMARY KEY,
    student_id         bigint       NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    gate_id            text         NOT NULL,
    unit_id            text         NOT NULL,
    amount_cents       integer      NOT NULL CHECK (amount_cents > 0),
    currency           text         NOT NULL DEFAULT 'usd',
    rebate_pct         numeric(5,2) NOT NULL CHECK (rebate_pct > 0 AND rebate_pct <= 100),
    status             text         NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'earned', 'paid', 'forfeited', 'expired')),
    pledged_at         timestamptz  NOT NULL DEFAULT now(),
    window_days        integer      NOT NULL CHECK (window_days > 0),
    window_ends_at     timestamptz  NOT NULL,
    earned_at          timestamptz,
    earned_event_seq   bigint,
    paid_at            timestamptz,
    forfeited_at       timestamptz,
    expired_at         timestamptz,
    UNIQUE (student_id, gate_id)
);

CREATE INDEX rebates_student_idx ON rebates (student_id);

-- Who/what/when for every transition, independent of the events spine: one
-- row per state change, never updated or deleted. The pair CHECK is the
-- state-machine graph enforced at the database level — no illegal edge
-- (backwards, skipping, sideways) can ever be logged, so the machine can
-- only ever issue guarded forward transitions.
CREATE TABLE rebate_transitions (
    id                bigserial PRIMARY KEY,
    rebate_id         bigint      NOT NULL REFERENCES rebates (id) ON DELETE CASCADE,
    from_status       text        NOT NULL,
    to_status         text        NOT NULL,
    actor             text        NOT NULL,
    reason            text        NOT NULL,
    source_event_seq  bigint,
    occurred_at       timestamptz NOT NULL DEFAULT now(),
    CHECK ((from_status, to_status) IN (
        ('none',     'pending'),   -- pledge created by gate.pledged
        ('pending',  'earned'),    -- verified gate.passed inside the window
        ('pending',  'expired'),   -- timed sweep: window elapsed, no passage
        ('earned',   'paid'),      -- runbook payout mark (ledger only)
        ('earned',   'forfeited')  -- runbook forfeit mark (e.g. full refund)
    ))
);

CREATE INDEX rebate_transitions_rebate_idx ON rebate_transitions (rebate_id);

-- Position of the rebate machine on the events spine (seq is the total
-- order). Crash between "transition applied" and "cursor advanced" replays
-- at most the events of one pass; every apply is idempotent, so replay is
-- safe by construction.
CREATE TABLE rebate_cursor (
    consumer text        PRIMARY KEY,
    last_seq bigint      NOT NULL DEFAULT 0
);

COMMIT;
