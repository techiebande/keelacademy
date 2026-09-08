-- smoke.sql — proof checks for 0001_init.sql. Run with psql -v ON_ERROR_STOP=1.
-- Each DO block prints PASS or raises (which aborts psql with ON_ERROR_STOP).

-- (a) happy path: student -> submission -> verdict
DO $$
DECLARE
    v_student bigint;
    v_submission bigint;
BEGIN
    INSERT INTO students (email, display_name)
    VALUES ('smoke@example.com', 'Smoke Tester')
    RETURNING id INTO v_student;

    INSERT INTO submissions (student_id, unit_id, commit_sha, repo_url, status)
    VALUES (v_student, '3.2.1', 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
            'https://github.com/smoke/repo', 'graded')
    RETURNING id INTO v_submission;

    INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json)
    VALUES (v_submission, '3.2.1', 1, 'pass',
            '{"overall": "pass", "criteria": []}'::jsonb);

    RAISE NOTICE 'PASS (a) student/submission/verdict insert';
END $$;

-- (b) exactly-once: a second verdict for the same submission MUST fail
DO $$
DECLARE
    v_submission bigint;
BEGIN
    SELECT id INTO v_submission FROM submissions WHERE unit_id = '3.2.1';
    BEGIN
        INSERT INTO verdicts (submission_id, overall, verdict_json)
        VALUES (v_submission, 'fail', '{"overall": "fail"}'::jsonb);
        RAISE EXCEPTION 'FAIL (b) second verdict was accepted — exactly-once violated';
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'PASS (b) duplicate verdict rejected: % (%)', SQLERRM, SQLSTATE;
    END;
END $$;

-- (c) duplicate (student, unit, commit_sha) submission MUST fail
DO $$
DECLARE
    v_student bigint;
BEGIN
    SELECT student_id INTO v_student FROM submissions WHERE unit_id = '3.2.1';
    BEGIN
        INSERT INTO submissions (student_id, unit_id, commit_sha, status)
        VALUES (v_student, '3.2.1', 'deadbeefdeadbeefdeadbeefdeadbeefdeadbeef', 'queued');
        RAISE EXCEPTION 'FAIL (c) duplicate submission was accepted';
    EXCEPTION
        WHEN unique_violation THEN
            RAISE NOTICE 'PASS (c) duplicate submission rejected: % (%)', SQLERRM, SQLSTATE;
    END;
END $$;

-- (d) event seq is monotonically increasing
DO $$
DECLARE
    s1 bigint;
    s2 bigint;
BEGIN
    INSERT INTO events (type, payload)
    VALUES ('smoke.tick', '{"n": 1}'::jsonb) RETURNING seq INTO s1;
    INSERT INTO events (type, payload)
    VALUES ('smoke.tick', '{"n": 2}'::jsonb) RETURNING seq INTO s2;
    IF s2 <= s1 THEN
        RAISE EXCEPTION 'FAIL (d) seq not monotonic: % then %', s1, s2;
    END IF;
    RAISE NOTICE 'PASS (d) event seq monotonic: % < %', s1, s2;
END $$;

-- (e) progress upsert path
DO $$
DECLARE
    v_student bigint;
    s1 text;
    s2 text;
BEGIN
    SELECT id INTO v_student FROM students WHERE email = 'smoke@example.com';

    INSERT INTO progress (student_id, unit_id, state, unlocked_at)
    VALUES (v_student, '3.2.1', 'unlocked', now())
    ON CONFLICT (student_id, unit_id) DO UPDATE
        SET state = EXCLUDED.state, unlocked_at = EXCLUDED.unlocked_at
    RETURNING state INTO s1;

    INSERT INTO progress (student_id, unit_id, state, passed_at)
    VALUES (v_student, '3.2.1', 'passed', now())
    ON CONFLICT (student_id, unit_id) DO UPDATE
        SET state = EXCLUDED.state, passed_at = EXCLUDED.passed_at
    RETURNING state INTO s2;

    IF s1 <> 'unlocked' OR s2 <> 'passed' THEN
        RAISE EXCEPTION 'FAIL (e) upsert states wrong: % -> %', s1, s2;
    END IF;
    RAISE NOTICE 'PASS (e) progress upsert: unlocked -> passed (one row)';
END $$;

-- (f) audit-grade deletes: deleting a submission with a verdict MUST be restricted
DO $$
DECLARE
    v_submission bigint;
BEGIN
    SELECT id INTO v_submission FROM submissions WHERE unit_id = '3.2.1';
    BEGIN
        DELETE FROM submissions WHERE id = v_submission;
        RAISE EXCEPTION 'FAIL (f) submission with verdict was deleted';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'PASS (f) verdict history RESTRICTs submission delete: % (%)', SQLERRM, SQLSTATE;
    END;
END $$;
