-- 0010_diagnostic.sql — diagnostic placement attempts and initial routing (S4.1)
-- Additive only: one new table for diagnostic attempts.
-- Existing smoke harnesses applying 0001..0009 explicitly are unaffected.

BEGIN;

-- One row per diagnostic placement attempt.
-- Records student, diagnostic id, points earned, total points, percentage score,
-- whether cleared (percentage >= threshold), placement route ('1.3_skip' or 'baseline_0.1'),
-- answers submitted, per-question score breakdown, and creation timestamp.
CREATE TABLE diagnostic_attempts (
    id                bigserial PRIMARY KEY,
    student_id        bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    diagnostic_id     text        NOT NULL,
    passed            boolean     NOT NULL,
    score_pct         numeric(5,2) NOT NULL CHECK (score_pct >= 0 AND score_pct <= 100),
    points_earned     integer     NOT NULL CHECK (points_earned >= 0),
    points_possible   integer     NOT NULL CHECK (points_possible > 0),
    route             text        NOT NULL CHECK (route IN ('1.3_skip', 'baseline_0.1', 'opt_out')),
    answers_json      jsonb       NOT NULL,
    breakdown_json    jsonb       NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX diagnostic_attempts_student_idx ON diagnostic_attempts (student_id, id DESC);

COMMIT;
