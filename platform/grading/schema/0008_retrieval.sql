-- 0008_retrieval.sql — retrieval drill attempts and grading (S3.2)
-- Additive only: one new table for retrieval drill attempts.
-- Existing smoke harnesses applying 0001..0007 explicitly are unaffected.

BEGIN;

-- One row per retrieval drill attempt evaluated by the Layer-2 judge through the proxy.
-- Attempts are repeatable by design (no UNIQUE constraint on student_id, unit_id, seed_index).
-- Records student, unit, seed index, seed prompt, student answer, pass/fail status,
-- feedback, evidence quote, full structured verdict JSON, and tokens charged.
CREATE TABLE retrieval_attempts (
    id              bigserial PRIMARY KEY,
    student_id      bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id         text        NOT NULL,
    seed_index      integer     NOT NULL CHECK (seed_index >= 0),
    seed_prompt     text        NOT NULL,
    student_answer  text        NOT NULL,
    passed          boolean     NOT NULL,
    feedback        text        NOT NULL,
    evidence        text        NOT NULL,
    verdict_json    jsonb       NOT NULL,
    tokens_charged  integer     NOT NULL DEFAULT 0 CHECK (tokens_charged >= 0),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX retrieval_attempts_student_unit_idx ON retrieval_attempts (student_id, unit_id, id DESC);
CREATE INDEX retrieval_attempts_scheduler_idx ON retrieval_attempts (student_id, unit_id, seed_index, created_at DESC);

COMMIT;
