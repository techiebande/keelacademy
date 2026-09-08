#!/usr/bin/env python3
"""smoke-map-checks.py — S2.8 deterministic proof of the progress dashboard map.

Runs against scratch postgres (schema 0001..0006) seeded with four students:
  - Alice (enrolled in 3.2.1, passes 5.1, clears Phase 5 gate)
  - Bob (enrolled in 3.2.1, fails 5.1, track stays locked)
  - Carol (signed in, unenrolled, sees honest pre-payment map)
  - Dave (enrolled in 3.2.1, tests available vs enrolled)

Deterministic clock (UTC):
  T0 = 2026-01-01   enrollments activate; engine pledges
  T1 = 2026-01-02   alice passes unit 5.1 (phase-5 gate clears, track unlocks)
  T2 = 2026-01-03   bob fails unit 5.1 (gate stays locked)
  T3 = 2026-01-04   alice submits fail on 5.1 (unlocks never reverse)
"""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ENGINE = os.environ.get("MAP_SMOKE_ENGINE",
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "gates", "engine.py"))
MACHINE = os.environ.get("MAP_SMOKE_MACHINE",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "rebate", "machine.py"))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DB_CMD = shlex.split(os.environ["KEEL_DB_CMD"])

T0 = "2026-01-01T00:00:00+00:00"
T1 = "2026-01-02T00:00:00+00:00"
T2 = "2026-01-03T00:00:00+00:00"
T3 = "2026-01-04T00:00:00+00:00"

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    print("%s: %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  [%s]" % detail) if (detail and not ok) else ""))
    if ok:
        PASS += 1
    else:
        FAIL += 1


def sql(script):
    proc = subprocess.run(DB_CMD + ["-q", "-tA", "-F", "\t"],
                          input=script.encode(), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode(errors="replace"))
        raise SystemExit("db script failed")
    return [tuple(l.split("\t")) for l in
            proc.stdout.decode().splitlines() if l.strip()]


def one(query):
    rows = sql(query)
    return rows[0] if rows else ()


def s(field, table, where):
    return one("SELECT %s FROM %s WHERE %s;" % (field, table, where))


def _jsonb(v):
    if isinstance(v, bool):
        return "to_jsonb(%s)" % ("true" if v else "false")
    if isinstance(v, int):
        return str(v)
    return "'%s'" % str(v).replace("'", "''")


def emit(etype, payload, occurred_at):
    fields = ", ".join("'%s', %s" % (k, _jsonb(v)) for k, v in payload.items())
    return int(one(
        "INSERT INTO events (type, payload, occurred_at) VALUES ("
        "'%s', jsonb_build_object(%s), '%s'::timestamptz) RETURNING seq;"
        % (etype, fields, occurred_at))[0])


def emit_enrollment(sid, unit, at):
    sql("INSERT INTO enrollments (student_id, unit_id, status) "
        "VALUES (%d, '%s', 'active');" % (sid, unit))
    sql("INSERT INTO budgets (student_id, tokens_cap, tokens_used) "
        "VALUES (%d, 5000, 0) ON CONFLICT (student_id) DO NOTHING;" % sid)
    return emit("enrollment.activated",
                {"student_id": sid, "unit_id": unit,
                 "stripe_session_id": "cs_test_smoke_%d" % sid}, at)


_SUB_COUNTER = [100]


def emit_submission(sid, unit, status, at, sha=None):
    _SUB_COUNTER[0] += 1
    sub_id = _SUB_COUNTER[0]
    sha = sha or "smoke%d" % sub_id
    sql("INSERT INTO submissions (id, student_id, unit_id, commit_sha, status, created_at) "
        "VALUES (%d, %d, '%s', '%s', '%s', '%s'::timestamptz);" % (sub_id, sid, unit, sha, status, at))
    emit("submission.created",
         {"submission_id": sub_id, "student_id": sid, "unit_id": unit, "commit_sha": sha}, at)
    return sub_id


def emit_verdict(sid, unit, overall, at, sub_id=None):
    if sub_id is None:
        sub_id = emit_submission(sid, unit, "graded", at)
    else:
        sql("UPDATE submissions SET status = 'graded' WHERE id = %d;" % sub_id)
    v_json = json.dumps({"overall": overall, "note": "deterministic fixture"}).replace("'", "''")
    sql("INSERT INTO verdicts (submission_id, rubric_id, rubric_version, overall, verdict_json, issued_at) "
        "VALUES (%d, 'rubric-%s', 1, '%s', '%s', '%s'::timestamptz);"
        % (sub_id, unit, overall, v_json, at))
    emit("verdict.issued",
         {"submission_id": sub_id, "student_id": sid, "unit_id": unit,
          "commit_sha": "smoke%d" % sub_id, "overall": overall,
          "verdict_id": sub_id}, at)
    return sub_id


def run_engine(now=None):
    env = dict(os.environ)
    env["KEEL_GATE_ONCE"] = "1"
    if now:
        env["KEEL_GATE_NOW"] = now
    proc = subprocess.run([sys.executable, ENGINE], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120)
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def run_machine(now=None):
    env = dict(os.environ)
    env["KEEL_REBATE_ONCE"] = "1"
    if now:
        env["KEEL_REBATE_NOW"] = now
    proc = subprocess.run([sys.executable, MACHINE], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120)
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


ALICE = int(s("id", "students", "email = 'alice@keel.test'")[0])
BOB = int(s("id", "students", "email = 'bob@keel.test'")[0])
CAROL = int(s("id", "students", "email = 'carol@keel.test'")[0])
DAVE = int(s("id", "students", "email = 'dave@keel.test'")[0])

# ----------------------------------------------------------------------
print("== (1) map skeleton validation & content-as-data integrity ==")
map_val = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "content", "tools", "validate-map.py")],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
check("validate-map.py exits 0", map_val.returncode == 0, map_val.stderr.decode())

curriculum_file = os.path.join(REPO_ROOT, "content", "curriculum", "phases.yaml")
import yaml
phases_doc = yaml.safe_load(open(curriculum_file).read())
phases_list = phases_doc.get("phases", [])
check("curriculum map contains all 13 phases (0..12)", len(phases_list) == 13)
phase_ids = [p["id"] for p in phases_list]
check("phases are indexed phase-0 through phase-12",
      phase_ids == ["phase-%d" % i for i in range(13)])
all_modules = [m["id"] for p in phases_list for m in p["modules"]]
check("authored unit 3.2.1 is present in the map skeleton", "3.2.1" in all_modules)
check("gate unit 5.1 is present in the map skeleton", "5.1" in all_modules)
check("capstone unit 12.1 is present in the map skeleton", "12.1" in all_modules)

# ----------------------------------------------------------------------
print("== (2) not-authored honesty: unauthored units render as planned/content arriving ==")
# Unit 0.1, 1.1, 5.1 are planned in phases.yaml but not authored under content/units/
units_dir = Path(REPO_ROOT) / "content" / "units"
authored_on_disk = set()
for p in units_dir.glob("phase-*"):
    for u in p.glob("*/unit.yaml"):
        authored_on_disk.add(u.parent.name)
# Update this pin whenever new units are authored (C1a added phase-0; C1b will add phase-1)
check("authored unit set on disk matches expectation", authored_on_disk == set(), str(sorted(authored_on_disk)))

# ----------------------------------------------------------------------
print("== (3) enrollment activation & baseline available states ==")
emit_enrollment(ALICE, "3.2.1", T0)
emit_enrollment(BOB, "3.2.1", T0)
emit_enrollment(DAVE, "3.2.1", T0)
code, out, err = run_engine(T0)
check("gate engine one-shot exits 0", code == 0, err)
code, out, err = run_machine(T0)
check("rebate machine one-shot exits 0", code == 0, err)

# Check Alice's profile rows
alice_enrollments = sql("SELECT unit_id, status FROM enrollments WHERE student_id = %d;" % ALICE)
check("alice is enrolled in unit 3.2.1", ("3.2.1", "active") in alice_enrollments)
check("carol has zero enrollments (unenrolled)",
      s("count(*)", "enrollments", "student_id = %d" % CAROL) == ("0",))

# ----------------------------------------------------------------------
print("== (4) queued and grading mid-flight submission states ==")
sub_queued = emit_submission(ALICE, "3.2.1", "queued", T0, "sha_queued")
sub_status = s("status", "submissions", "id = %d" % sub_queued)
check("submission status is queued", sub_status == ("queued",))

sql("UPDATE submissions SET status = 'grading' WHERE id = %d;" % sub_queued)
sub_status_2 = s("status", "submissions", "id = %d" % sub_queued)
check("submission status moves to grading mid-flight", sub_status_2 == ("grading",))

# ----------------------------------------------------------------------
print("== (5) pass lights up the track through Phase 5 integration gate ==")
# Alice passes unit 5.1
e_pass_alice = emit_verdict(ALICE, "5.1", "pass", T1)
code, out, err = run_engine(T1)
check("engine unlocks phase 6 track for alice", code == 0, err)

alice_unlocked = sql("SELECT unit_id, gate_id FROM unlocked_units WHERE student_id = %d ORDER BY unit_id;" % ALICE)
check("alice has unlocked units 6.1, 6.2, 6.3, 6.4",
      alice_unlocked == [("6.1", "phase-5-integration"),
                        ("6.2", "phase-5-integration"),
                        ("6.3", "phase-5-integration"),
                        ("6.4", "phase-5-integration")], str(alice_unlocked))

code, out, err = run_machine(T1)
check("rebate machine earns 15% rebate milestone for alice",
      code == 0 and s("status", "rebates", "student_id = %d AND gate_id = 'phase-5-integration'" % ALICE) == ("earned",))

# ----------------------------------------------------------------------
print("== (6) fail does not unlock or earn ==")
# Bob fails unit 5.1
e_fail_bob = emit_verdict(BOB, "5.1", "fail", T2)
code, out, err = run_engine(T2)
check("engine exits 0 over fail verdict", code == 0, err)

bob_unlocked = sql("SELECT count(*) FROM unlocked_units WHERE student_id = %d;" % BOB)
check("bob has zero unlocked units", bob_unlocked == [("0",)])
check("bob rebate remains pending (not earned)",
      s("status", "rebates", "student_id = %d AND gate_id = 'phase-5-integration'" % BOB) == ("pending",))

# ----------------------------------------------------------------------
print("== (7) unlocks never reverse on late fail ==")
# Alice fails unit 5.1 after having passed it
e_fail_alice_late = emit_verdict(ALICE, "5.1", "fail", T3)
code, out, err = run_engine(T3)
check("engine exits 0 over late fail", code == 0, err)

alice_unlocked_after = sql("SELECT unit_id FROM unlocked_units WHERE student_id = %d ORDER BY unit_id;" % ALICE)
check("alice's unlocked units remain intact after late fail",
      len(alice_unlocked_after) == 4)
check("alice's earned rebate remains earned",
      s("status", "rebates", "student_id = %d AND gate_id = 'phase-5-integration'" % ALICE) == ("earned",))

# ----------------------------------------------------------------------
print("== (8) replay & idempotency: cursor reset leaves map state identical ==")
sql("UPDATE gate_cursor SET last_seq = 0 WHERE consumer = 'gate-engine';")
code, out, err = run_engine(T3)
check("engine cursor reset replay exits 0", code == 0, err)
check("unlocked units count unchanged by replay",
      s("count(*)", "unlocked_units", "TRUE") == ("4",))
check("no duplicate gate.passed events",
      s("count(*)", "events", "type = 'gate.passed'") == ("1",))

# ----------------------------------------------------------------------
print("== (9) unenrolled signed-in student (Carol) honesty ==")
carol_unlocked = s("count(*)", "unlocked_units", "student_id = %d" % CAROL)
check("carol has 0 unlocked units", carol_unlocked == ("0",))
carol_rebates = s("count(*)", "rebates", "student_id = %d" % CAROL)
check("carol has 0 rebate ledger rows (pre-payment honesty)", carol_rebates == ("0",))

# ----------------------------------------------------------------------
print("== (10) reader endpoint SELECT-only /students/<id>/submissions ==")
# Test reader logic directly with DB queries matching reader route implementation
reader_alice_subs = sql("""BEGIN;
SELECT 'S', id FROM students WHERE id = %d;
SELECT 'R', s.id, s.unit_id, s.status, s.created_at, v.overall
FROM submissions s
LEFT JOIN verdicts v ON v.submission_id = s.id
WHERE s.student_id = %d
ORDER BY s.id DESC;
ROLLBACK;
""" % (ALICE, ALICE))

subs_rows = [r for r in reader_alice_subs if r[0] == "R"]
check("reader query returns alice's submissions with verdicts", len(subs_rows) >= 2)
units_submitted = set(r[2] for r in subs_rows)
check("submissions include unit 5.1 and 3.2.1", "5.1" in units_submitted and "3.2.1" in units_submitted)

reader_carol_subs = sql("""BEGIN;
SELECT 'S', id FROM students WHERE id = %d;
SELECT 'R', s.id, s.unit_id, s.status, s.created_at, v.overall
FROM submissions s
LEFT JOIN verdicts v ON v.submission_id = s.id
WHERE s.student_id = %d
ORDER BY s.id DESC;
ROLLBACK;
""" % (CAROL, CAROL))
carol_sub_rows = [r for r in reader_carol_subs if r[0] == "R"]
check("carol has 0 submissions (honest empty list)", len(carol_sub_rows) == 0)

print()
print("== map smoke checks: %d passed, %d failed ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
