-- 0001_init.sql — keelacademy grading core schema (S1.1)
-- Plain SQL, forward-only, fresh-apply per migration number.

BEGIN;

CREATE TABLE students (
    id              bigserial PRIMARY KEY,
    email           text        NOT NULL UNIQUE,
    display_name    text,
    external_auth_id text       UNIQUE,            -- populated by managed auth at S2.5
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Append-only spine of the event-driven design.
-- Later services append: submission.created, verdict.issued, gate.unlocked, ...
-- Never UPDATE or DELETE here; seq is the total order.
CREATE TABLE events (
    id          bigserial PRIMARY KEY,
    seq         bigserial UNIQUE,
    type        text        NOT NULL,
    payload     jsonb       NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX events_type_occurred_at_idx ON events (type, occurred_at);

CREATE TABLE submissions (
    id         bigserial PRIMARY KEY,
    student_id bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id    text        NOT NULL,
    commit_sha text        NOT NULL,
    repo_url   text,
    status     text        NOT NULL
        CHECK (status IN ('queued', 'grading', 'graded', 'error')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (student_id, unit_id, commit_sha)
);

CREATE INDEX submissions_student_idx ON submissions (student_id);

-- Audit-grade: one verdict per submission, ever. The UNIQUE constraint is the
-- seed of S1.3's exactly-once guarantee — the DB, not app memory, decides.
CREATE TABLE verdicts (
    id           bigserial PRIMARY KEY,
    submission_id bigint     NOT NULL UNIQUE REFERENCES submissions (id) ON DELETE RESTRICT,
    rubric_id    text,
    rubric_version int,
    overall      text        NOT NULL CHECK (overall IN ('pass', 'fail')),
    verdict_json jsonb       NOT NULL,
    issued_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE progress (
    id          bigserial PRIMARY KEY,
    student_id  bigint      NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    unit_id     text        NOT NULL,
    state       text        NOT NULL CHECK (state IN ('locked', 'unlocked', 'passed')),
    unlocked_at timestamptz,
    passed_at   timestamptz,
    UNIQUE (student_id, unit_id)
);

CREATE INDEX progress_student_idx ON progress (student_id);

COMMIT;
