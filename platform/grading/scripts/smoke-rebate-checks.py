#!/usr/bin/env python3
"""smoke-rebate-checks.py — S2.6 deterministic proof of the rebate machine.

Runs against the scratch postgres stood up by smoke-rebate.sh (schema
0001..0005, four seeded students, KEEL_PRICE_CENTS_DEFAULT=10000,
KEEL_REBATE_PCT=15, KEEL_REBATE_WINDOW_DAYS=60). Every timestamp is
deterministic: gate events are inserted with explicit occurred_at and the
machine runs one-shot under KEEL_REBATE_NOW — no sleeps anywhere.

The gate.pledged / gate.passed rows inserted here are the published event
contract S2.7's gate engine will emit; until it exists this harness is the
deterministic fake producer.

Clock (all UTC):
    T0  = 2026-01-01   pledge time
    T5  = 2026-01-06   wrong-unit attempt
    T10 = 2026-01-11   in-window passage
    T11 = 2026-01-12   duplicate passage event
    T32 = 2026-02-02   out-of-window passage (window is 30 days)
    T40 = 2026-02-10   past every window
"""

import json
import os
import shlex
import subprocess
import sys

MACHINE = os.environ.get("REBATE_SMOKE_MACHINE",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "rebate", "machine.py"))
DB_CMD = shlex.split(os.environ["KEEL_DB_CMD"])

T0 = "2026-01-01T00:00:00+00:00"
T5 = "2026-01-06T00:00:00+00:00"
T10 = "2026-01-11T00:00:00+00:00"
T11 = "2026-01-12T00:00:00+00:00"
T32 = "2026-02-02T00:00:00+00:00"
T40 = "2026-02-10T00:00:00+00:00"

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


def emit(etype, payload, occurred_at):
    """Insert one gate event row — exactly what S2.7 will write."""
    fields = ", ".join("'%s', %s" % (k, _jsonb(v)) for k, v in payload.items())
    return int(one(
        "INSERT INTO events (type, payload, occurred_at) VALUES ("
        "'%s', jsonb_build_object(%s), '%s'::timestamptz) RETURNING seq;"
        % (etype, fields, occurred_at))[0])


def _jsonb(v):
    if isinstance(v, bool):
        return "to_jsonb(%s)" % ("true" if v else "false")
    if isinstance(v, int):
        return str(v)
    return "'%s'" % str(v).replace("'", "''")


def run_machine(now=None, extra_env=None):
    env = dict(os.environ)
    env["KEEL_REBATE_ONCE"] = "1"
    if now:
        env["KEEL_REBATE_NOW"] = now
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run([sys.executable, MACHINE], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=120)
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def run_mark(flag, rebate_id, reason=None, actor=None):
    env = dict(os.environ)
    if reason:
        env["KEEL_REBATE_REASON"] = reason
    if actor:
        env["KEEL_REBATE_ACTOR"] = actor
    proc = subprocess.run([sys.executable, MACHINE, flag, str(rebate_id)],
                          env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=120)
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def s(field, table, where):
    return one("SELECT %s FROM %s WHERE %s;" % (field, table, where))


# ----------------------------------------------------------------------
print("== (a) gate.pledged creates the pending ledger row ==")
e_pledge_alice = emit("gate.pledged",
                      {"student_id": 1, "gate_id": "phase-5-integration",
                       "unit_id": "5.1", "window_days": 30}, T0)
code, out, _ = run_machine(T0)
check("machine one-shot exits 0", code == 0, out)
row = s("status, amount_cents, rebate_pct::text, window_days, "
        "to_char(window_ends_at, 'YYYY-MM-DD'), earned_at IS NULL",
        "rebates", "student_id = 1 AND gate_id = 'phase-5-integration'")
check("pending row with frozen amount 15% of $100 = $15.00",
      row == ("pending", "1500", "15.00", "30", "2026-01-31", "t"), str(row))
check("rebate.pledged event on the spine",
      s("count(*)", "events", "type = 'rebate.pledged'") == ("1",))
tr = one("SELECT from_status, to_status, actor, reason, source_event_seq "
         "FROM rebate_transitions WHERE rebate_id = 1;")
check("transition none->pending references the source event",
      tr == ("none", "pending", "rebate-machine", "gate.pledged",
             str(e_pledge_alice)), str(tr))

# ----------------------------------------------------------------------
print("== (b) verified in-window gate.passed earns, once ==")
e_pass_alice = emit("gate.passed",
                    {"student_id": 1, "gate_id": "phase-5-integration",
                     "unit_id": "5.1", "passed_at": T10}, T10)
code, out, _ = run_machine(T10)
check("machine exits 0", code == 0, out)
row = s("status, earned_event_seq, "
        "to_char(earned_at, 'YYYY-MM-DD HH24:MI')",
        "rebates", "student_id = 1 AND gate_id = 'phase-5-integration'")
check("earned, tagged with the earning event seq and deterministic time",
      row == ("earned", str(e_pass_alice), "2026-01-11 00:00"), str(row))
check("exactly one rebate.earned event",
      s("count(*)", "events", "type = 'rebate.earned'") == ("1",))
check("exactly one pending->earned transition",
      s("count(*)", "rebate_transitions",
        "rebate_id = 1 AND from_status = 'pending' "
        "AND to_status = 'earned'") == ("1",))

# ----------------------------------------------------------------------
print("== (c) replayed gate events are absorbed (earn-once) ==")
sql("UPDATE rebate_cursor SET last_seq = 0 WHERE consumer = 'rebate-machine';")
code, out, _ = run_machine(T10)
check("cursor reset + full replay exits 0", code == 0, out)
check("replay changes nothing: still exactly one earned transition",
      s("count(*)", "rebate_transitions",
        "rebate_id = 1 AND to_status IN ('pending', 'earned')") == ("2",))
check("replay changes nothing: still one rebate.earned event",
      s("count(*)", "events", "type = 'rebate.earned'") == ("1",))
e_dup_alice = emit("gate.passed",
                   {"student_id": 1, "gate_id": "phase-5-integration",
                    "unit_id": "5.1", "passed_at": T10}, T11)
code, out, _ = run_machine(T11)
check("a second distinct gate.passed is also absorbed", code == 0, out)
check("no second earn: one row, one earned transition, one event",
      s("count(*)", "rebates", "student_id = 1") == ("1",)
      and s("count(*)", "rebate_transitions",
            "rebate_id = 1 AND to_status = 'earned'") == ("1",)
      and s("count(*)", "events", "type = 'rebate.earned'") == ("1",))
check("the duplicate is logged as a rejected diagnostic",
      s("count(*)", "events",
        "type = 'rebate.rejected' AND payload->>'reason' = 'not_pending' "
        "AND payload->>'source_event_seq' = '%d'" % e_dup_alice) == ("1",))

# ----------------------------------------------------------------------
print("== (d) out-of-window passage and timed expiry ==")
emit("gate.pledged", {"student_id": 2, "gate_id": "phase-5-integration",
                      "unit_id": "5.1", "window_days": 30}, T0)
run_machine(T0)
e_late_bob = emit("gate.passed",
                  {"student_id": 2, "gate_id": "phase-5-integration",
                   "unit_id": "5.1", "passed_at": T32}, T32)
code, out, _ = run_machine(T32)
check("machine exits 0 on the late passage", code == 0, out)
check("late passage rejected out_of_window, never earned",
      s("count(*)", "events",
        "type = 'rebate.rejected' AND payload->>'reason' = 'out_of_window' "
        "AND payload->>'source_event_seq' = '%d'" % e_late_bob) == ("1",)
      and s("count(*)", "events", "type = 'rebate.earned'") == ("1",))
check("the same pass's sweep executed the timed transition to expired",
      s("status, to_char(expired_at, 'YYYY-MM-DD')", "rebates",
        "student_id = 2") == ("expired", "2026-02-02"))
check("expiry left its event and transition",
      s("count(*)", "events", "type = 'rebate.expired'") == ("1",)
      and s("count(*)", "rebate_transitions",
            "from_status = 'pending' AND to_status = 'expired'") == ("1",))
# pure timed expiry: a pledge that simply never gets a passage
emit("gate.pledged", {"student_id": 4, "gate_id": "phase-5-integration",
                      "unit_id": "5.1", "window_days": 30}, T0)
run_machine(T0)
code, out, _ = run_machine(T40)
check("window elapsed with no passage at all: expired", code == 0, out)
check("dave's rebate expired by the sweep alone",
      s("status", "rebates", "student_id = 4") == ("expired",))
check("an expired rebate cannot be earned retroactively",
      emit("gate.passed",
           {"student_id": 4, "gate_id": "phase-5-integration",
            "unit_id": "5.1", "passed_at": T10}, T10) > 0
      and (run_machine(T40)[0] == 0)
      and s("status", "rebates", "student_id = 4") == ("expired",)
      and s("count(*)", "events", "type = 'rebate.earned'") == ("1",))

# ----------------------------------------------------------------------
print("== (e) wrong-unit rejection, then the right unit still earns ==")
emit("gate.pledged", {"student_id": 3, "gate_id": "capstone",
                      "unit_id": "12.1"}, T0)  # no window_days -> config 60
run_machine(T0)
check("pledge without window_days uses the configured default (60)",
      s("window_days", "rebates", "student_id = 3") == ("60",))
e_wrong = emit("gate.passed",
               {"student_id": 3, "gate_id": "capstone",
                "unit_id": "3.2.1", "passed_at": T5}, T5)
run_machine(T5)
check("wrong-unit passage rejected, rebate untouched",
      s("count(*)", "events",
        "type = 'rebate.rejected' AND payload->>'reason' = 'wrong_unit' "
        "AND payload->>'source_event_seq' = '%d'" % e_wrong) == ("1",)
      and s("status, unit_id", "rebates", "student_id = 3")
      == ("pending", "12.1"))
emit("gate.passed", {"student_id": 3, "gate_id": "capstone",
                     "unit_id": "12.1", "passed_at": T10}, T10)
run_machine(T10)
check("the matching unit then earns the capstone rebate",
      s("status", "rebates", "student_id = 3") == ("earned",))

# ----------------------------------------------------------------------
print("== (f) unknown gate / unknown student / no pledge ==")
emit("gate.pledged", {"student_id": 1, "gate_id": "phase-3-mini",
                      "unit_id": "3.2.1"}, T0)
emit("gate.passed", {"student_id": 2, "gate_id": "capstone",
                     "unit_id": "12.1"}, T5)
emit("gate.pledged", {"student_id": 999, "gate_id": "phase-5-integration",
                      "unit_id": "5.1"}, T0)
code, out, _ = run_machine(T40)
check("machine exits 0 over the junk events", code == 0, out)
check("unknown gate rejected with no ledger row",
      s("count(*)", "events",
        "type = 'rebate.rejected' AND payload->>'reason' = 'unknown_gate'")
      == ("1",)
      and s("count(*)", "rebates", "gate_id = 'phase-3-mini'") == ("0",))
check("passage without a pledge rejected",
      s("count(*)", "events",
        "type = 'rebate.rejected' AND payload->>'reason' = 'no_pledge'")
      == ("1",))
check("unknown student rejected with no ledger row",
      s("count(*)", "events",
        "type = 'rebate.rejected' AND payload->>'reason' = 'unknown_student'")
      == ("1",)
      and s("count(*)", "rebates", "student_id = 999") == ("0",))
check("still exactly 4 rebates (1 per student per gate)",
      s("count(*)", "rebates", "TRUE") == ("4",))

# ----------------------------------------------------------------------
print("== (g) runbook marks: earned -> paid / forfeited, never backwards ==")
# Look ids up, never assume them: ON CONFLICT DO NOTHING still burns
# bigserial values, so the (c) cursor-reset replay shifted every id after
# alice's. Rebates: alice (paid path), bob (expired), dave (expired),
# carol (earned capstone).
R_ALICE = s("id", "rebates", "student_id = 1 AND gate_id = 'phase-5-integration'")[0]
R_BOB = s("id", "rebates", "student_id = 2 AND gate_id = 'phase-5-integration'")[0]
R_CAROL = s("id", "rebates", "student_id = 3 AND gate_id = 'capstone'")[0]
code, out, err = run_mark("--mark-paid", R_ALICE,
                          reason="stripe refund pi_test_123", actor="founder")
check("mark-paid exits 0", code == 0, err)
check("LEDGER ONLY banner says no money moved",
      "LEDGER ONLY" in err and "FOUNDER-WIRING.md" in err)
check("paid row + transition + event",
      s("status", "rebates", "id = %s" % R_ALICE) == ("paid",)
      and one("SELECT actor, reason FROM rebate_transitions "
              "WHERE rebate_id = %s AND to_status = 'paid';" % R_ALICE)
      == ("founder", "stripe refund pi_test_123")
      and s("count(*)", "events", "type = 'rebate.paid'") == ("1",))
code, out, err = run_mark("--mark-paid", R_ALICE)
check("second mark-paid refused (no sideways)", code == 1, err)
code, out, err = run_mark("--mark-paid", R_BOB)
check("mark-paid on expired refused (no backwards)", code == 1, err)
code, out, err = run_mark("--mark-forfeited", R_CAROL, reason="full refund issued")
check("mark-forfeited on earned works", code == 0, err)
code, out, err = run_mark("--mark-paid", R_CAROL)
check("forfeited cannot become paid", code == 1, err)
emit("gate.passed", {"student_id": 1, "gate_id": "phase-5-integration",
                     "unit_id": "5.1", "passed_at": T11}, T11)
run_machine(T11)
check("a paid rebate ignores new passages (not_pending)",
      s("count(*)", "events", "type = 'rebate.earned'") == ("2",)
      and s("status", "rebates", "id = %s" % R_ALICE) == ("paid",))

# ----------------------------------------------------------------------
print("== (h) full cursor-reset replay over the final state ==")
sql("UPDATE rebate_cursor SET last_seq = 0 WHERE consumer = 'rebate-machine';")
code, out, _ = run_machine(T40)
check("full replay over terminal states exits 0", code == 0, out)
check("statuses unchanged by the replay",
      s("string_agg(status, ',' ORDER BY student_id)", "rebates", "TRUE")
      == ("paid,expired,forfeited,expired",))
check("no transition edge was duplicated by the replay",
      one("SELECT count(DISTINCT (rebate_id, from_status, to_status)), "
          "count(*) FROM rebate_transitions;")[0]
      == one("SELECT count(DISTINCT (rebate_id, from_status, to_status)), "
             "count(*) FROM rebate_transitions;")[1])

# ----------------------------------------------------------------------
print("== (i) ledger auditability: who/what/when on every transition ==")
rows = sql("SELECT count(*) FROM rebate_transitions "
           "WHERE actor = '' OR reason = '' OR occurred_at IS NULL;")
check("no transition lacks actor/reason/occurred_at", rows[0][0] == "0")
proc = subprocess.run([sys.executable, MACHINE, "--ledger"], env=os.environ,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      timeout=120)
lines = [l for l in proc.stdout.decode().splitlines() if l.strip()]
docs = [json.loads(l) for l in lines]
check("--ledger emits one JSON doc per rebate", len(docs) == 4, str(len(docs)))
paid_doc = next(d for d in docs if d["rebate_id"] == 1)
check("ledger doc carries who/what/when across the full history",
      [t["to_status"] for t in paid_doc["transitions"]]
      == ["pending", "earned", "paid"]
      and all(t["actor"] and t["reason"] and t["occurred_at"]
              for t in paid_doc["transitions"])
      and paid_doc["amount_cents"] == 1500, json.dumps(paid_doc)[:200])

print()
print("== rebate machine checks: %d passed, %d failed ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
