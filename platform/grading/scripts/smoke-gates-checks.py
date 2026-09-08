#!/usr/bin/env python3
"""smoke-gates-checks.py — S2.7 deterministic proof of the gate engine.

Runs against the scratch postgres stood up by smoke-gates.sh (schema
0001..0006, four seeded students, KEEL_PRICE_CENTS_DEFAULT=10000,
KEEL_REBATE_PCT=15, KEEL_REBATE_WINDOW_DAYS=60). Every timestamp is
deterministic: upstream events are inserted with explicit occurred_at and
the engine runs one-shot under KEEL_GATE_NOW — no sleeps anywhere.

The enrollment.activated and verdict.issued rows inserted here are shaped
byte-for-byte like the real writers (enroll/server.py's webhook CTE and
worker.py's finish_submission payload). They are the deterministic offline
fake for the verdict pipeline; everything DOWNSTREAM of them is real: the
engine evaluates, unlocks, and emits, and the rebate machine earns from the
engine's own gate.pledged / gate.passed events — no faked gate rows.

Seed students: alice and bob enrolled (active enrollment on 3.2.1), carol
signed up but never paid, dave enrolled. Ids are looked up by email, never
assumed.

Clock (all UTC):
    T0  = 2026-01-01   enrollments activate; engine pledges
    T1  = 2026-01-02   alice passes unit 5.1 (phase-5 gate clears)
    T2  = 2026-01-03   bob fails unit 5.1
    T3  = 2026-01-04   carol (unenrolled) passes unit 5.1
    T4  = 2026-01-05   dave passes unit 3.2.1 (no rule for that unit)
    T5  = 2026-01-06   alice passes unit 12.1 (capstone clears)
    T6  = 2026-01-07   alice fails unit 5.1 again (after the unlock)
    T7  = 2026-01-08   alice's second enrollment activates
"""

import json
import os
import shlex
import subprocess
import sys

ENGINE = os.environ.get("GATES_SMOKE_ENGINE",
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "gates", "engine.py"))
MACHINE = os.environ.get("GATES_SMOKE_MACHINE",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "rebate", "machine.py"))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
DB_CMD = shlex.split(os.environ["KEEL_DB_CMD"])

T0 = "2026-01-01T00:00:00+00:00"
T1 = "2026-01-02T00:00:00+00:00"
T2 = "2026-01-03T00:00:00+00:00"
T3 = "2026-01-04T00:00:00+00:00"
T4 = "2026-01-05T00:00:00+00:00"
T5 = "2026-01-06T00:00:00+00:00"
T6 = "2026-01-07T00:00:00+00:00"
T7 = "2026-01-08T00:00:00+00:00"

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
    """Insert one upstream event row — shaped exactly as the real writer."""
    fields = ", ".join("'%s', %s" % (k, _jsonb(v)) for k, v in payload.items())
    return int(one(
        "INSERT INTO events (type, payload, occurred_at) VALUES ("
        "'%s', jsonb_build_object(%s), '%s'::timestamptz) RETURNING seq;"
        % (etype, fields, occurred_at))[0])


def emit_enrollment(sid, unit, at):
    """Mirror enroll/server.py's webhook: the enrollments ROW lands first
    (the table is authoritative for gate coupling), then the event."""
    sql("INSERT INTO enrollments (student_id, unit_id, status) "
        "VALUES (%d, '%s', 'active');" % (sid, unit))
    # exactly enroll/server.py's enrollment.activated payload
    return emit("enrollment.activated",
                {"student_id": sid, "unit_id": unit,
                 "stripe_session_id": "cs_test_smoke_%d" % sid}, at)


_SUB_COUNTER = [900]


def emit_verdict(sid, unit, overall, at):
    """Mirror the verdict pipeline: submissions row, verdicts row, then
    worker.py's finish_submission event (exactly its payload shape)."""
    _SUB_COUNTER[0] += 1
    sub_id = _SUB_COUNTER[0]
    sql("INSERT INTO submissions (student_id, unit_id, commit_sha, status) "
        "VALUES (%d, '%s', 'smoke%d', 'graded');" % (sid, unit, sub_id))
    sql("INSERT INTO verdicts (submission_id, rubric_id, rubric_version, "
        "overall, verdict_json) VALUES (%d, 'rubric-%s', 1, '%s', "
        "'{\"overall\": \"%s\", \"note\": \"deterministic smoke fixture\"}');"
        % (sub_id, unit, overall, overall))
    return emit("verdict.issued",
                {"submission_id": sub_id, "student_id": sid, "unit_id": unit,
                 "commit_sha": "smoke%d" % sub_id, "overall": overall,
                 "verdict_id": sub_id}, at)


def run_engine(now=None, extra_env=None):
    env = dict(os.environ)
    env["KEEL_GATE_ONCE"] = "1"
    if now:
        env["KEEL_GATE_NOW"] = now
    if extra_env:
        env.update(extra_env)
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
print("== (0) rules are content-as-data; --rules audits them ==")
proc = subprocess.run([sys.executable, ENGINE, "--rules"], env=os.environ,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
docs = [json.loads(l) for l in proc.stdout.decode().splitlines() if l.strip()]
check("--rules exits 0 with one JSON doc per rule", proc.returncode == 0 and len(docs) == 2,
      proc.stderr.decode())
by_gate = {d["gate_id"]: d for d in docs}
check("phase-5-integration gates unit 5.1 and unlocks the phase 6 track",
      by_gate.get("phase-5-integration", {}).get("unit_id") == "5.1"
      and by_gate.get("phase-5-integration", {}).get("unlocks")
      == ["6.1", "6.2", "6.3", "6.4"], json.dumps(docs)[:200])
check("capstone gates unit 12.1 and unlocks nothing (final gate)",
      by_gate.get("capstone", {}).get("unit_id") == "12.1"
      and by_gate.get("capstone", {}).get("unlocks") == [], json.dumps(docs)[:200])

# ----------------------------------------------------------------------
print("== (1) enrollment activation -> engine gate.pledged -> machine pending ==")
e_enroll_alice = emit_enrollment(ALICE, "3.2.1", T0)
e_enroll_bob = emit_enrollment(BOB, "3.2.1", T0)
e_enroll_dave = emit_enrollment(DAVE, "3.2.1", T0)
code, out, err = run_engine(T0)
check("engine one-shot exits 0", code == 0, err or out)
pledged = sql("SELECT payload->>'student_id', payload->>'gate_id', "
              "payload->>'unit_id', occurred_at FROM events "
              "WHERE type = 'gate.pledged' ORDER BY seq;")
check("two pledges per enrolled student, one per rebate rule",
      len(pledged) == 6
      and sorted((p[0], p[1]) for p in pledged)
      == sorted([(str(s), g) for s in (ALICE, BOB, DAVE)
                 for g in ("capstone", "phase-5-integration")]),
      str(pledged))
check("pledge payloads carry exactly the published contract fields",
      all(set(json.loads(p_payload[0]).keys())
          == {"student_id", "gate_id", "unit_id"}
          for p_payload in sql("SELECT payload::text FROM events "
                               "WHERE type = 'gate.pledged';")),
      "payload key check")
check("pledge occurred_at tracks the enrollment event time",
      all(p[3].startswith("2026-01-01") for p in pledged), str(pledged))
code, out, err = run_machine(T0)
check("rebate machine consumes the engine's pledges: 6 pending",
      code == 0 and s("count(*)", "rebates", "TRUE") == ("6",)
      and s("count(*)", "rebates", "status = 'pending'") == ("6",), err or out)
check("pledged amounts frozen from the shared price convention",
      s("count(*)", "rebates", "amount_cents = 1500") == ("6",))
check("no pledge for carol (she never enrolled)",
      s("count(*)", "events",
        "type = 'gate.pledged' AND payload->>'student_id' = '%d'" % CAROL) == ("0",))

# ----------------------------------------------------------------------
print("== (2) passing verdict unlocks + emits gate.passed; machine earns ==")
e_pass_alice = emit_verdict(ALICE, "5.1", "pass", T1)
code, out, err = run_engine(T1)
check("engine exits 0 on the passing verdict", code == 0, err or out)
rows = sql("SELECT unit_id, gate_id, source_event_seq, "
           "to_char(unlocked_at, 'YYYY-MM-DD') FROM unlocked_units "
           "WHERE student_id = %d ORDER BY unit_id;" % ALICE)
check("phase 6 track unlocked: one row per rule unlock, forward-only insert",
      rows == [("6.1", "phase-5-integration", str(e_pass_alice), "2026-01-02"),
               ("6.2", "phase-5-integration", str(e_pass_alice), "2026-01-02"),
               ("6.3", "phase-5-integration", str(e_pass_alice), "2026-01-02"),
               ("6.4", "phase-5-integration", str(e_pass_alice), "2026-01-02")],
      str(rows))
unlocked_events = sql("SELECT payload->>'student_id', payload->>'unit_id', "
                      "payload->>'gate_id', payload->>'source_event_seq' "
                      "FROM events WHERE type = 'unit.unlocked' ORDER BY seq;")
check("unit.unlocked events on the spine, one per new row, cause-linked",
      len(unlocked_events) == 4
      and all(u[0] == str(ALICE) and u[2] == "phase-5-integration"
              and u[3] == str(e_pass_alice) for u in unlocked_events),
      str(unlocked_events))
gp = one("SELECT payload::text, to_char(occurred_at, 'YYYY-MM-DD HH24:MI') "
         "FROM events WHERE type = 'gate.passed';")
gp_payload = json.loads(gp[0]) if gp else {}
check("gate.passed emitted exactly per the S2.6 contract",
      gp_payload == {"student_id": ALICE, "gate_id": "phase-5-integration",
                     "unit_id": "5.1", "passed_at": "2026-01-02T00:00:00+00:00"}
      and gp[1] == "2026-01-02 00:00", str(gp))
code, out, err = run_machine(T1)
check("rebate machine EARNS from the engine-emitted gate.passed",
      code == 0
      and s("status", "rebates",
            "student_id = %d AND gate_id = 'phase-5-integration'" % ALICE)
      == ("earned",)
      and s("count(*)", "events", "type = 'rebate.earned'") == ("1",), err or out)
check("the earning event seq points at the engine's gate.passed",
      s("earned_event_seq", "rebates",
        "student_id = %d AND gate_id = 'phase-5-integration'" % ALICE)
      == one("SELECT seq FROM events WHERE type = 'gate.passed';"))
check("capstone rebate still pending for alice",
      s("status", "rebates",
        "student_id = %d AND gate_id = 'capstone'" % ALICE) == ("pending",))

# ----------------------------------------------------------------------
print("== (3) fail verdict does not unlock ==")
e_fail_bob = emit_verdict(BOB, "5.1", "fail", T2)
code, out, err = run_engine(T2)
check("engine exits 0 over the fail verdict", code == 0, err or out)
check("no unlock rows and no gate.passed for bob",
      s("count(*)", "unlocked_units", "student_id = %d" % BOB) == ("0",)
      and s("count(*)", "events",
            "type = 'gate.passed' AND payload->>'student_id' = '%d'" % BOB)
      == ("0",))
check("bob's rebates remain pending after the fail",
      s("count(*)", "rebates",
        "student_id = %d AND status = 'pending'" % BOB) == ("2",))

# ----------------------------------------------------------------------
print("== (4) replayed verdicts are no-ops (cursor reset + duplicate pass) ==")
sql("UPDATE gate_cursor SET last_seq = 0 WHERE consumer = 'gate-engine';")
code, out, err = run_engine(T1)
check("full cursor-reset replay exits 0", code == 0, err or out)
check("replay adds no unlock rows", s("count(*)", "unlocked_units", "TRUE") == ("4",))
check("replay adds no unit.unlocked events",
      s("count(*)", "events", "type = 'unit.unlocked'") == ("4",))
check("replay adds no gate.pledged events",
      s("count(*)", "events", "type = 'gate.pledged'") == ("6",))
check("replay adds no second gate.passed",
      s("count(*)", "events", "type = 'gate.passed'") == ("1",))
e_pass_alice_2 = emit_verdict(ALICE, "5.1", "pass", T2)  # a SECOND submission passes later
code, out, err = run_engine(T2)
check("second distinct passing verdict also a no-op for unlocks",
      code == 0 and s("count(*)", "unlocked_units", "TRUE") == ("4",), err or out)
check("no second gate.passed for the same (student, gate)",
      s("count(*)", "events", "type = 'gate.passed'") == ("1",))

# ----------------------------------------------------------------------
print("== (5) unenrolled student's verdict ignored (enrollments authoritative) ==")
e_pass_carol = emit_verdict(CAROL, "5.1", "pass", T3)
code, out, err = run_engine(T3)
check("engine exits 0 over the unenrolled verdict", code == 0, err or out)
check("no unlock, no gate.passed, no pledge ever for carol",
      s("count(*)", "unlocked_units", "student_id = %d" % CAROL) == ("0",)
      and s("count(*)", "events",
            "payload->>'student_id' = '%d' AND type IN "
            "('gate.passed', 'gate.pledged', 'unit.unlocked')" % CAROL) == ("0",))

# ----------------------------------------------------------------------
print("== (6) wrong-unit verdict refused (no rule for 3.2.1) ==")
e_pass_dave = emit_verdict(DAVE, "3.2.1", "pass", T4)
code, out, err = run_engine(T4)
check("engine exits 0 while refusing the no-rule unit", code == 0, err or out)
check("no unlock, no gate.passed for dave's 3.2.1 verdict",
      s("count(*)", "unlocked_units", "student_id = %d" % DAVE) == ("0",)
      and s("count(*)", "events",
            "type = 'gate.passed' AND payload->>'student_id' = '%d'" % DAVE)
      == ("0",))
check("dave's pledges stand (his enrollment was real) but nothing earned",
      s("count(*)", "rebates",
        "student_id = %d AND status = 'pending'" % DAVE) == ("2",))

# ----------------------------------------------------------------------
print("== (7) unlock never moves backwards ==")
before = sql("SELECT unit_id, to_char(unlocked_at, 'YYYY-MM-DD HH24:MI:SS') "
             "FROM unlocked_units WHERE student_id = %d ORDER BY unit_id;" % ALICE)
e_fail_alice = emit_verdict(ALICE, "5.1", "fail", T6)
code, out, err = run_engine(T6)
after = sql("SELECT unit_id, to_char(unlocked_at, 'YYYY-MM-DD HH24:MI:SS') "
            "FROM unlocked_units WHERE student_id = %d ORDER BY unit_id;" % ALICE)
check("a later fail verdict leaves every unlocked row untouched",
      code == 0 and before == after and len(after) == 4, err or out)
check("no re-lock or reversal event type exists on the spine",
      s("count(*)", "events",
        "type IN ('unit.locked', 'unit.relocked')") == ("0",))
check("the earned rebate stays earned",
      s("status", "rebates",
        "student_id = %d AND gate_id = 'phase-5-integration'" % ALICE) == ("earned",))

# ----------------------------------------------------------------------
print("== (8) capstone: clears the gate, unlocks nothing, earns the rebate ==")
e_capstone_alice = emit_verdict(ALICE, "12.1", "pass", T5)
code, out, err = run_engine(T5)
check("engine exits 0 on the capstone pass", code == 0, err or out)
check("capstone gate.passed emitted; zero unlock rows for it",
      s("count(*)", "events",
        "type = 'gate.passed' AND payload->>'gate_id' = 'capstone'") == ("1",)
      and s("count(*)", "unlocked_units", "gate_id = 'capstone'") == ("0",))
code, out, err = run_machine(T5)
check("rebate machine earns the capstone rebate from the engine's event",
      code == 0
      and s("status", "rebates",
            "student_id = %d AND gate_id = 'capstone'" % ALICE) == ("earned",)
      and s("count(*)", "events", "type = 'rebate.earned'") == ("2",), err or out)

# ----------------------------------------------------------------------
print("== (9) second enrollment pledges nothing new (window tracks the first payment) ==")
e_enroll_alice2 = emit_enrollment(ALICE, "5.1", T7)
code, out, err = run_engine(T7)
check("engine exits 0 over the second enrollment", code == 0, err or out)
check("no new gate.pledged events",
      s("count(*)", "events", "type = 'gate.pledged'") == ("6",))

# ----------------------------------------------------------------------
print("== (10) KEEL_CONTENT_ROOT lever: a scratch rule set can gate unit 3.2.1 ==")
# This is the reviewer's lever for driving a REAL 3.2.1 grading through the
# engine: point the engine at a scratch content copy whose rules gate the
# unit being graded. The real content repo is never touched. The cursor is
# reset so the already-consumed verdict replays under the new rule set; all
# prior effects are guarded no-ops, which this section re-proves implicitly.
import shutil
import tempfile

sql("UPDATE gate_cursor SET last_seq = 0 WHERE consumer = 'gate-engine';")
scratch = tempfile.mkdtemp(prefix="keel-gates-smoke-content-")
try:
    shutil.copytree(os.path.join(REPO_ROOT, "content"),
                    os.path.join(scratch, "content"))
    with open(os.path.join(scratch, "content", "gates", "phase-3-exit.yaml"),
              "w", encoding="utf-8") as fh:
        fh.write(
            "gate_id: phase-3-exit\n"
            "title: Phase 3 exit gate\n"
            "unit_id: \"3.2.1\"\n"
            "unlocks: [\"3.2.2\"]\n"
            "rebate: false\n"
            "summary: A passing verdict on unit 3.2.1 clears this gate.\n")
    code, out, err = run_engine(T4, extra_env={
        "KEEL_CONTENT_ROOT": os.path.join(scratch, "content")})
    check("engine under the scratch rule set unlocks 3.2.2 from dave's verdict",
          code == 0
          and s("count(*)", "unlocked_units",
                "student_id = %d AND unit_id = '3.2.2'" % DAVE) == ("1",),
          err or out)
    check("replay under the new rule set duplicated nothing else",
          s("count(*)", "unlocked_units", "TRUE") == ("5",)
          and s("count(*)", "events", "type = 'gate.pledged'") == ("6",)
          and s("count(DISTINCT (payload->>'student_id', payload->>'gate_id'))",
                "events", "type = 'gate.passed'")
          == s("count(*)", "events", "type = 'gate.passed'"))
    # A duplicate-unit rule set is a hard config error, not a silent guess.
    with open(os.path.join(scratch, "content", "gates", "phase-3-exit-dup.yaml"),
              "w", encoding="utf-8") as fh:
        fh.write(
            "gate_id: phase-3-exit-dup\n"
            "title: Duplicate unit gate\n"
            "unit_id: \"3.2.1\"\n"
            "unlocks: [\"9.9.9\"]\n"
            "rebate: false\n"
            "summary: A second rule for the same unit.\n")
    env = dict(os.environ)
    env["KEEL_CONTENT_ROOT"] = os.path.join(scratch, "content")
    proc = subprocess.run([sys.executable, ENGINE], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    check("duplicate unit across rules is a config error (exit 2)",
          proc.returncode == 2 and "duplicate unit_id" in proc.stderr.decode(),
          proc.stderr.decode())
finally:
    shutil.rmtree(scratch, ignore_errors=True)
    ok = not os.path.exists(scratch)
    check("scratch content copy deleted", ok)

# ----------------------------------------------------------------------
print("== (11) spine hygiene: only engine event types were added ==")
types = sql("SELECT type, count(*) FROM events GROUP BY type ORDER BY type;")
expected = {"enrollment.activated": 4, "gate.pledged": 6, "gate.passed": 3,
            "rebate.earned": 2, "rebate.pledged": 6, "unit.unlocked": 5,
            "verdict.issued": 7}
check("event type counts exactly as the story demands",
      dict((t, int(c)) for t, c in types) == expected, str(types))
check("no UPDATE/DELETE path exists: unlocked_units still holds exactly 5 rows",
      s("count(*)", "unlocked_units", "TRUE") == ("5",))

print()
print("== gate engine checks: %d passed, %d failed ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
