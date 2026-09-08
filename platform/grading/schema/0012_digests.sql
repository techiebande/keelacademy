-- 0012_digests.sql — weekly personalized digest records and delivery audit (S4.3)
-- Additive only: one new table for retention digests.
-- Existing smoke harnesses applying 0001..0011 explicitly are unaffected.

BEGIN;

CREATE TABLE digests (
    id           serial PRIMARY KEY,
    student_id   integer NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    cohort_week  text NOT NULL, -- e.g. '2026-W35'
    content_json jsonb NOT NULL, -- contains the 4 structured pillars
    email_to     text NOT NULL,
    delivered_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (student_id, cohort_week)
);

CREATE INDEX digests_student_idx ON digests (student_id, id DESC);
CREATE INDEX digests_cohort_week_idx ON digests (cohort_week);

COMMIT;
