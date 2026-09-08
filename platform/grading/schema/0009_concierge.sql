-- 0009_concierge.sql — concierge chat turns and mode audit (S3.5)
-- Additive only: one new table for concierge turns.
-- Existing smoke harnesses applying 0001..0008 explicitly are unaffected.

BEGIN;

-- One row per concierge Q&A turn.
-- Turns are repeatable by design (no UNIQUE constraint on student_id, unit_id).
-- Records student, unit, derived mode ('teach' | 'guard'), student question,
-- assistant answer, tokens charged, and creation timestamp.
CREATE TABLE concierge_turns (
    id              bigserial PRIMARY KEY,
    student_id      bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id         text        NOT NULL,
    mode            text        NOT NULL CHECK (mode IN ('teach', 'guard')),
    question        text        NOT NULL,
    answer          text        NOT NULL,
    tokens_charged  integer     NOT NULL DEFAULT 0 CHECK (tokens_charged >= 0),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX concierge_turns_student_unit_idx ON concierge_turns (student_id, unit_id, id DESC);
CREATE INDEX concierge_turns_mode_idx ON concierge_turns (mode, created_at DESC);

COMMIT;
