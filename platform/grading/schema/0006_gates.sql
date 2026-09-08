-- 0006_gates.sql — gate unlock state + engine cursor (S2.7)
-- Additive only: two new tables, no change to any existing table.
-- Existing smoke harnesses apply 0001..0005 explicitly and are unaffected.

BEGIN;

-- Per-student unlocked units, written by the gate engine
-- (gates/engine.py) when a gate clears. One row per (student, unit), ever:
-- the UNIQUE constraint is the unlock idempotency seed (same pattern as
-- verdicts.submission_id and enrollments (student_id, unit_id)) — the
-- database, not engine memory, decides that a replayed verdict.issued or a
-- second passing submission cannot unlock twice.
--
-- FORWARD-ONLY BY CONSTRUCTION: the engine only ever INSERTs (ON CONFLICT
-- DO NOTHING); no code path UPDATEs or DELETEs here. A later fail verdict
-- can never re-lock a unit; unlock state never moves backwards.
-- source_event_seq points at the verdict.issued event that caused the
-- unlock, so every row traces to its cause on the spine.
CREATE TABLE unlocked_units (
    id                 bigserial PRIMARY KEY,
    student_id         bigint       NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id            text         NOT NULL,
    gate_id            text         NOT NULL,
    unlocked_at        timestamptz  NOT NULL DEFAULT now(),
    source_event_seq   bigint       NOT NULL,
    UNIQUE (student_id, unit_id)
);

CREATE INDEX unlocked_units_student_idx ON unlocked_units (student_id);

-- Position of the gate engine on the events spine (seq is the total
-- order), mirroring rebate_cursor. Crash between "state applied" and
-- "cursor advanced" replays at most the events of one pass; every apply is
-- idempotent (guarded inserts + emission guards), so replay is safe by
-- construction.
CREATE TABLE gate_cursor (
    consumer text        PRIMARY KEY,
    last_seq bigint      NOT NULL DEFAULT 0
);

COMMIT;
