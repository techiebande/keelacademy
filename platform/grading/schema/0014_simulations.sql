-- 0014_simulations.sql — simulation engine for Phase 11 business discovery-call & reviewer reps (S4.5)
-- Forward-only, additive migration.

BEGIN;

CREATE TABLE simulations (
    id            serial PRIMARY KEY,
    student_id    integer NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    persona_id    text NOT NULL,
    status        text NOT NULL DEFAULT 'in_progress'
                  CHECK (status IN ('in_progress', 'concluded', 'graded', 'abandoned')),
    turns_json    jsonb NOT NULL DEFAULT '[]'::jsonb,
    score_pct     numeric(5,2),
    passed        boolean,
    verdict_json  jsonb,
    created_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at  timestamptz
);

CREATE INDEX simulations_student_idx ON simulations (student_id);
CREATE INDEX simulations_persona_idx ON simulations (persona_id);
CREATE INDEX simulations_status_idx ON simulations (status);

COMMIT;
