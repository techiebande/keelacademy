-- 0013_gallery.sql — public build gallery v1 (S4.4)
-- Additive only: one new table for opt-in public portfolio showcase.
-- Existing smoke harnesses applying 0001..0012 explicitly are unaffected.

BEGIN;

CREATE TABLE gallery_projects (
    id                    serial PRIMARY KEY,
    student_id            integer NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    unit_id               text NOT NULL,
    submission_id         integer NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    title                 text NOT NULL,
    description           text NOT NULL,
    repo_url              text,
    demo_url              text,
    walkthrough_video_url text,
    published             boolean NOT NULL DEFAULT true,
    created_at            timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at            timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (student_id, unit_id)
);

CREATE INDEX gallery_projects_published_idx ON gallery_projects (published, created_at DESC);
CREATE INDEX gallery_projects_student_idx ON gallery_projects (student_id);
CREATE INDEX gallery_projects_unit_idx ON gallery_projects (unit_id);
CREATE INDEX gallery_projects_submission_idx ON gallery_projects (submission_id);

COMMIT;
