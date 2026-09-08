-- 0011_pods.sql — peer accountability pods, memberships, and weekly posts (S4.2)
-- Additive only: three new tables for pod community architecture.
-- Existing smoke harnesses applying 0001..0010 explicitly are unaffected.

BEGIN;

CREATE TABLE pods (
    id                 serial PRIMARY KEY,
    name               text        NOT NULL,
    cohort_week        text        NOT NULL,  -- e.g. '2026-W35'
    discord_channel_id text,
    discord_role_id    text,
    created_at         timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX pods_cohort_week_idx ON pods (cohort_week);

CREATE TABLE pod_memberships (
    pod_id      integer     REFERENCES pods(id) ON DELETE CASCADE,
    student_id  bigint      REFERENCES students(id) ON DELETE CASCADE,
    joined_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    active      boolean     NOT NULL DEFAULT true,
    PRIMARY KEY (pod_id, student_id)
);

CREATE INDEX pod_memberships_student_idx ON pod_memberships (student_id, active);

CREATE TABLE pod_posts (
    id                 serial PRIMARY KEY,
    pod_id             integer     REFERENCES pods(id) ON DELETE CASCADE,
    student_id         bigint      REFERENCES students(id) ON DELETE CASCADE,
    week_number        integer     NOT NULL CHECK (week_number >= 1),
    shipped_text       text        NOT NULL,
    broke_text         text        NOT NULL,
    next_text          text        NOT NULL,
    discord_message_id text,
    created_at         timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (pod_id, student_id, week_number)
);

CREATE INDEX pod_posts_pod_week_idx ON pod_posts (pod_id, week_number, id DESC);
CREATE INDEX pod_posts_student_idx ON pod_posts (student_id, week_number);

COMMIT;
