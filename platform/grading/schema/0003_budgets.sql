-- 0003_budgets.sql — per-student LLM token budgets (S1.5)
-- Forward-only like 0001/0002; fresh-apply, idempotency not required.

BEGIN;

CREATE TABLE budgets (
    student_id  bigint      PRIMARY KEY REFERENCES students (id) ON DELETE CASCADE,
    tokens_cap  bigint      NOT NULL CHECK (tokens_cap >= 0),
    tokens_used bigint      NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

COMMIT;
