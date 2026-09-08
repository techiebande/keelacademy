-- 0007_practice.sql — completion problem practice attempts (S3.1)
-- Additive only: one new table, no change to any existing table.
-- Existing smoke harnesses apply 0001..0006 explicitly and are unaffected.

BEGIN;

-- One row per completion-problem attempt graded by Layer-1 sandbox checks.
-- Attempts are repeatable by design — no UNIQUE constraint on (student_id, unit_id).
-- Each attempt records the student, unit, pass/fail status, pass count, total checks,
-- per-check results JSON, and submitted files.
CREATE TABLE practice_attempts (
    id              bigserial PRIMARY KEY,
    student_id      bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id         text        NOT NULL,
    passed          boolean     NOT NULL,
    pass_count      integer     NOT NULL CHECK (pass_count >= 0),
    total_checks    integer     NOT NULL CHECK (total_checks >= 0),
    results_json    jsonb       NOT NULL,
    submitted_files jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX practice_attempts_student_unit_idx ON practice_attempts (student_id, unit_id, id DESC);

COMMIT;
