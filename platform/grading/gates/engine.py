#!/usr/bin/env python3
"""platform/grading/gates/engine.py — gate engine (S2.7).

Architecture §4/§8: phase gates are real. A student cannot access a gated
unit until the gate in front of it clears on a VERIFIED verdict, never on
self-reported completion. This engine is the arbiter: it watches the events
spine the verdict pipeline already writes and turns verdicts into unlock
state plus the published gate event contract the rebate machine consumes.

Consumed events (nothing else; the engine adds no grading logic):

    verdict.issued        {submission_id, student_id, unit_id, commit_sha,
                           overall, verdict_id}     (written by worker.py)
    enrollment.activated  {student_id, unit_id, stripe_session_id}
                                                    (written by enroll/server.py)

Emitted events:

    unit.unlocked  {student_id, unit_id, gate_id, unlocked_at,
                    source_event_seq}
        One per newly unlocked unit, in the same transaction as the unlock
        row. Guarded by the row insert itself: a replayed verdict.issued or
        a second passing submission inserts nothing and emits nothing.
    gate.pledged  {student_id, gate_id, unit_id}          (S2.6 contract)
        Fired when a student's FIRST enrollment activates, so the rebate
        window tracks the real payment. Only for rules with rebate: true.
        Emitted once per (student, gate): the guard is a spine lookup, so
        cursor-reset replay is exactly-once.
    gate.passed   {student_id, gate_id, unit_id, passed_at} (S2.6 contract)
        A verified gate passage: a verdict.issued with overall 'pass' for
        the rule's unit, from an ENROLLED student. passed_at is the verdict
        event's occurred_at. Emitted once per (student, gate) for the same
        guard reason; the rebate machine absorbs replays anyway, but the
        spine stays clean.

Rules are content-as-data: content/gates/<gate-id>.yaml (gate_id, title,
unit_id, unlocks, rebate, summary), validated by content/tools/
validate-gates.py. The engine REFUSES to evaluate verdicts for any unit
without a rule (no unlock, no gate event) and treats only verdict.issued
events with overall 'pass' as gate-relevant. Enrollment coupling: the
enrollments table is authoritative — verdicts of students with no active
enrollment are ignored.

Unlock state lives in unlocked_units (migration 0006): insert-only, so an
unlock can never move backwards or be earned twice. The old 0001 `progress`
table stays untouched scaffolding.

Idempotency: unlocked_units UNIQUE (student_id, unit_id) with ON CONFLICT DO
NOTHING absorbs replayed verdicts; emission guards (spine NOT EXISTS for
gate.pledged/gate.passed, insert-RETURNING for unit.unlocked) absorb cursor
resets; the cursor only ever moves forward and a crash replays at most one
pass of harmless no-ops.

Deterministic clock: KEEL_GATE_NOW (ISO 8601) overrides now() for
unlocked_at — a test knob for proving the engine at fixed points;
production leaves it unset.

Usage:
    KEEL_DB_CMD="... psql ..." python3 gates/engine.py            # poll loop
    KEEL_GATE_ONCE=1 ... python3 gates/engine.py                  # one pass
    ... engine.py --rules                                        # audit dump

Stdlib + PyYAML (same dependency set as layer1.py); database access via
the shared db.py (KEEL_DB_CMD convention).
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import db_sql, sql_str

CONSUMER = "gate-engine"
GATE_EVENT_TYPES = ("gate.pledged", "gate.passed")
UNIT_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")  # dotted pair (5.1) or triple (3.2.1)
GATE_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
GRADING_DIR = Path(__file__).resolve().parent.parent  # platform/grading


class ConfigError(Exception):
    pass


def log(msg):
    sys.stdout.write("[gate] %s\n" % msg)
    sys.stdout.flush()


# ----------------------------------------------------------------------
# Rules: content-as-data
# ----------------------------------------------------------------------

def content_root():
    """content/ root: KEEL_CONTENT_ROOT override, else the repo this file
    lives in (same convention as layer1.py)."""
    root = os.environ.get("KEEL_CONTENT_ROOT")
    if root:
        return Path(root)
    return GRADING_DIR.parents[1] / "content"


def load_rules():
    """Parse content/gates/*.yaml into {unit_id: rule}. Structural errors
    are ConfigError: the engine refuses to run on an ambiguous rule set
    (duplicate gate or unit), mirroring the validator's cross-file rules."""
    gates_dir = content_root() / "gates"
    if not gates_dir.is_dir():
        raise ConfigError("no gates directory at %s" % gates_dir)
    rules = {}
    seen_gate_ids = {}
    for path in sorted(gates_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise ConfigError("%s does not parse: %s" % (path.name, exc))
        if not isinstance(doc, dict):
            raise ConfigError("%s is not a mapping" % path.name)
        gate_id = str(doc.get("gate_id") or "")
        unit_id = str(doc.get("unit_id") or "")
        unlocks = doc.get("unlocks")
        if not GATE_ID_RE.match(gate_id) or gate_id != path.stem:
            raise ConfigError("%s: gate_id %r must equal the file name stem"
                              % (path.name, gate_id))
        if not UNIT_RE.match(unit_id):
            raise ConfigError("%s: bad unit_id %r" % (path.name, unit_id))
        if not isinstance(unlocks, list) or \
                not all(UNIT_RE.match(str(u)) for u in unlocks):
            raise ConfigError("%s: unlocks must be a list of unit ids" % path.name)
        if not isinstance(doc.get("rebate"), bool):
            raise ConfigError("%s: rebate must be true or false" % path.name)
        if gate_id in seen_gate_ids:
            raise ConfigError("duplicate gate_id %s in %s and %s"
                              % (gate_id, seen_gate_ids[gate_id], path.name))
        if unit_id in rules:
            raise ConfigError(
                "duplicate unit_id %s in %s and %s: a verdict must satisfy "
                "at most one gate" % (unit_id, rules[unit_id]["_src"], path.name))
        seen_gate_ids[gate_id] = path.name
        rules[unit_id] = {
            "gate_id": gate_id,
            "title": str(doc.get("title") or gate_id),
            "unit_id": unit_id,
            "unlocks": [str(u) for u in unlocks],
            "rebate": bool(doc["rebate"]),
            "summary": str(doc.get("summary") or ""),
            "_src": path.name,
        }
    if not rules:
        raise ConfigError("no gate rules found under %s" % gates_dir)
    return rules


RULES = None  # set in main(); --rules dumps it


def rebate_rules():
    return [r for r in RULES.values() if r["rebate"]]


# ----------------------------------------------------------------------
# Clock
# ----------------------------------------------------------------------

def now_sql():
    """SQL expression for the current instant: now(), or the KEEL_GATE_NOW
    override as a timestamptz literal (deterministic proofs)."""
    raw = os.environ.get("KEEL_GATE_NOW")
    if not raw:
        return "now()"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ConfigError("KEEL_GATE_NOW is not an ISO timestamp: %r" % raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return "%s::timestamptz" % sql_str(parsed.isoformat())


def ts_literal(value):
    """Validate an ISO timestamp from an event payload and render it as a
    timestamptz literal. Returns None when absent/invalid."""
    iso = ts_iso(value)
    if iso is None:
        return None
    return "%s::timestamptz" % sql_str(iso)


def ts_iso(value):
    """Normalized ISO 8601 string for a timestamp from the spine (psql prints
    timestamptz as '2026-01-02 00:00:00+00'; jsonb payloads carry the 'T'
    form). None when absent/invalid."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


# ----------------------------------------------------------------------
# Event handlers — one transaction per event: state + spine events commit
# atomically; a crash before the cursor advances replays the event into a
# harmless no-op.
# ----------------------------------------------------------------------

def handle_enrollment(seq, payload, occurred_at):
    """enrollment.activated -> gate.pledged for each rebate rule, on the
    student's FIRST enrollment only, so the rebate window tracks the single
    real payment that enrolled them. Later enrollments pledge nothing; the
    rebate machine would absorb a repeat pledge anyway (UNIQUE student+gate)
    but the spine stays clean."""
    sid = payload.get("student_id")
    if not str(sid or "").isdigit():
        log("enrollment seq=%s skipped: bad student_id" % seq)
        return
    sid = int(sid)

    pledges = rebate_rules()
    if not pledges:
        log("enrollment seq=%s: no rebate rules, nothing to pledge" % seq)
        return

    # (gate_id, unit_id) VALUES list, straight from the rule data.
    values = ", ".join("(%s, %s)" % (sql_str(r["gate_id"]), sql_str(r["unit_id"]))
                       for r in pledges)
    fired_at = ts_literal(occurred_at) or now_sql()

    sql = """BEGIN;
WITH env AS (
    SELECT EXISTS (SELECT 1 FROM students WHERE id = %d) AS student_ok,
           (SELECT count(*) FROM enrollments WHERE student_id = %d) = 1
               AS is_first
), pev AS (
    INSERT INTO events (type, payload, occurred_at)
    SELECT 'gate.pledged',
           jsonb_build_object('student_id', %d, 'gate_id', g.gate_id,
                              'unit_id', g.unit_id),
           %s
    FROM (VALUES %s) AS g(gate_id, unit_id)
    WHERE (SELECT is_first FROM env)
      AND NOT EXISTS (
          SELECT 1 FROM events e
          WHERE e.type = 'gate.pledged'
            AND e.payload->>'student_id' = %s
            AND e.payload->>'gate_id' = g.gate_id)
    RETURNING (payload->>'gate_id') AS gate_id
)
SELECT (SELECT student_ok FROM env), (SELECT is_first FROM env),
       (SELECT count(*) FROM pev);
COMMIT;
""" % (sid, sid, sid, fired_at, values, sql_str(str(sid)))
    rows = db_sql(sql)
    student_ok, is_first, pledged = rows[0]
    if student_ok != "t":
        log("enrollment seq=%s ignored: unknown student %d" % (seq, sid))
        return
    if is_first != "t":
        log("enrollment seq=%s: student %d already enrolled earlier; "
            "no new pledge (window tracks the first payment)" % (seq, sid))
        return
    log("pledged student=%d gate(s)=%s from enrollment seq=%s"
        % (sid, pledged, seq))


def handle_verdict(seq, payload, occurred_at):
    """verdict.issued -> unlock rows + unit.unlocked + gate.passed.

    Only overall 'pass' is gate-relevant; only units with a rule are
    evaluated; only ENROLLED students count (enrollments is authoritative).
    Everything here is guarded, so replay at any cursor position is a
    no-op."""
    sid = payload.get("student_id")
    unit = str(payload.get("unit_id") or "")
    overall = str(payload.get("overall") or "")
    if not str(sid or "").isdigit():
        log("verdict seq=%s skipped: bad student_id" % seq)
        return
    sid = int(sid)

    rule = RULES.get(unit)
    if rule is None:
        # Refusal, not an error: most units have no gate. No unlock, no
        # gate event, no diagnostic noise on the spine.
        log("verdict seq=%s refused: no gate rule for unit %s" % (seq, unit))
        return
    if overall != "pass":
        log("verdict seq=%s not gate-relevant: overall=%s (unit %s)"
            % (seq, overall, unit))
        return

    gate = rule["gate_id"]
    passed_at_iso = ts_iso(occurred_at)
    passed_at = ts_literal(occurred_at) or now_sql()

    # Unlock inserts for the rule's unlocks (capstone has none: it is the
    # final gate and unlocks nothing after it).
    if rule["unlocks"]:
        units_values = ", ".join(sql_str(u) for u in rule["unlocks"])
        unlock_sql = """ins AS (
    INSERT INTO unlocked_units (student_id, unit_id, gate_id,
                                unlocked_at, source_event_seq)
    SELECT %d, u, %s, %s, %d
    FROM unnest(ARRAY[%s]::text[]) u
    WHERE (SELECT ok FROM env)
    ON CONFLICT (student_id, unit_id) DO NOTHING
    RETURNING student_id, unit_id, unlocked_at
), uev AS (
    INSERT INTO events (type, payload)
    SELECT 'unit.unlocked', jsonb_build_object(
               'student_id', student_id, 'unit_id', unit_id,
               'gate_id', %s, 'unlocked_at', unlocked_at::text,
               'source_event_seq', %s::bigint)
    FROM ins
), unlocked_count AS (
    SELECT count(*) AS n FROM ins
),
""" % (sid, sql_str(gate), now_sql(), seq, units_values,
       sql_str(gate), seq)
    else:
        unlock_sql = """unlocked_count AS (SELECT 0 AS n),
"""

    sql = """BEGIN;
WITH env AS (
    SELECT EXISTS (SELECT 1 FROM enrollments
                   WHERE student_id = %d AND status = 'active') AS ok
),
%s
gp AS (
    INSERT INTO events (type, payload, occurred_at)
    SELECT 'gate.passed',
           jsonb_build_object('student_id', %d, 'gate_id', %s,
                              'unit_id', %s, 'passed_at', %s::jsonb),
           %s
    WHERE (SELECT ok FROM env)
      AND NOT EXISTS (
          SELECT 1 FROM events e
          WHERE e.type = 'gate.passed'
            AND e.payload->>'student_id' = %s
            AND e.payload->>'gate_id' = %s)
    RETURNING seq
)
SELECT (SELECT ok FROM env), (SELECT n FROM unlocked_count),
       (SELECT count(*) FROM gp);
COMMIT;
""" % (sid, unlock_sql, sid, sql_str(gate), sql_str(unit),
       sql_str(json.dumps(passed_at_iso)), passed_at,
       sql_str(str(sid)), sql_str(gate))
    rows = db_sql(sql)
    enrolled, unlocked, passed = rows[0]
    if enrolled != "t":
        log("verdict seq=%s ignored: student %d has no active enrollment "
            "(enrollments table is authoritative)" % (seq, sid))
        return
    log("verdict seq=%s: gate=%s student=%d unlocked=%s unit(s), "
        "gate.passed emitted=%s"
        % (seq, gate, sid, unlocked, passed))


# ----------------------------------------------------------------------
# Poll loop
# ----------------------------------------------------------------------

def read_cursor():
    rows = db_sql(
        "BEGIN;\n"
        "SELECT COALESCE((SELECT last_seq FROM gate_cursor\n"
        "                 WHERE consumer = %s), 0);\n"
        "ROLLBACK;\n" % sql_str(CONSUMER))
    return int(rows[0][0])


def advance_cursor(seq):
    db_sql(
        "BEGIN;\n"
        "INSERT INTO gate_cursor (consumer, last_seq) VALUES (%s, %d)\n"
        "ON CONFLICT (consumer) DO UPDATE SET last_seq = EXCLUDED.last_seq\n"
        "WHERE EXCLUDED.last_seq > gate_cursor.last_seq;\n"
        "COMMIT;\n" % (sql_str(CONSUMER), seq),
        want_rows=False)


def process_events():
    cursor = read_cursor()
    rows = db_sql(
        "BEGIN;\n"
        "SELECT seq, type, payload, occurred_at FROM events\n"
        "WHERE type IN ('verdict.issued', 'enrollment.activated')\n"
        "  AND seq > %d\n"
        "ORDER BY seq;\n"
        "ROLLBACK;\n" % cursor)
    for seq_s, etype, payload_s, occurred_at in rows:
        seq = int(seq_s)
        try:
            payload = json.loads(payload_s)
            if not isinstance(payload, dict):
                raise ValueError("payload is not an object")
        except ValueError:
            log("event seq=%s skipped: malformed payload" % seq)
            advance_cursor(seq)
            continue
        if etype == "verdict.issued":
            handle_verdict(seq, payload, occurred_at)
        else:
            handle_enrollment(seq, payload, occurred_at)
        advance_cursor(seq)
    return len(rows)


def run_once():
    processed = process_events()
    log("pass complete: %d event(s) processed" % processed)


def dump_rules():
    for rule in sorted(RULES.values(), key=lambda r: r["gate_id"]):
        doc = {k: v for k, v in rule.items() if not k.startswith("_")}
        doc["_source"] = str(content_root() / "gates" / rule["_src"])
        sys.stdout.write(json.dumps(doc, sort_keys=True) + "\n")


def main():
    global RULES
    args = sys.argv[1:]
    RULES = load_rules()
    if args and args[0] == "--rules":
        dump_rules()
        return 0
    if args:
        sys.stderr.write("usage: engine.py [--rules]\n"
                         "       (poll loop; KEEL_GATE_ONCE=1 for one pass)\n")
        return 2

    # Fail fast on a bad KEEL_DB_CMD.
    db_sql("BEGIN;\nSELECT 1;\nROLLBACK;\n", want_rows=False)
    if os.environ.get("KEEL_GATE_ONCE", "0").lower() in ("1", "true", "yes"):
        run_once()
        return 0
    interval = float(os.environ.get("KEEL_GATE_POLL_S", "2"))
    log("engine armed: %d rule(s) (%s); listening for verdict.issued + "
        "enrollment.activated every %gs"
        % (len(RULES), ", ".join(sorted(r["gate_id"] for r in RULES.values())),
           interval))
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigError as exc:
        sys.stderr.write("[gate] config error: %s\n" % exc)
        sys.exit(2)
