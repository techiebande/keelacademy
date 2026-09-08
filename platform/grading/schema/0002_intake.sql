-- 0002_intake.sql — webhook intake (S1.2)
-- Forward-only, like 0001. Fresh-apply; idempotency not required.

BEGIN;

ALTER TABLE submissions ADD COLUMN pusher_email text;

COMMIT;
