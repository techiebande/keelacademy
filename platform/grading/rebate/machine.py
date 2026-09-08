#!/usr/bin/env python3
"""platform/grading/rebate/machine.py — rebate state machine (S2.6).

Policy (school-architecture.md §8): a portion of the one-time price is
refunded when a student clears VERIFIED gates — the Phase 5 integration
gate inside a configured window, and again at capstone — never on
self-reported completion. This machine is the ledger for that promise:

    pending -> earned                (gate.passed, verified, inside window)
    pending -> expired               (timed sweep: window elapsed, no passage)
    earned  -> paid | forfeited      (runbook marks; see FOUNDER-WIRING.md)

No other edge exists; the rebate_transitions pair CHECK enforces the graph
at the database level and every UPDATE is guarded on its from-state, so a
rebate can never move backwards or be earned twice for the same gate.

Consumption point — the published gate event contract (S2.7 will emit these
onto the same append-only events spine the verdict pipeline already writes;
until then harnesses fake them deterministically by inserting the same rows):

    gate.pledged  {student_id, gate_id, unit_id, window_days?}
        Pledge a rebate for (student, gate): creates the pending ledger row.
        window_days defaults to the machine's config for that gate.
    gate.passed   {student_id, gate_id, unit_id, passed_at?}
        A verified gate passage. passed_at (ISO timestamp) defaults to the
        event's occurred_at. Earns only when the rebate is pending, the
        unit matches the pledge, and the passage is inside the window.

The machine emits its own spine events so every transition is event-sourced:
rebate.pledged, rebate.earned, rebate.expired, rebate.paid, rebate.forfeited,
and rebate.rejected (diagnostic: an attempt that changed nothing — wrong
unit, no pledge, unknown gate/student, out-of-window passage, terminal
state). A replayed gate.passed that already earned is a silent no-op.

NO MONEY MOVES HERE. amounts are ledger numbers; paying out is a documented
manual / Stripe-refund runbook step (platform/FOUNDER-WIRING.md), recorded
via --mark-paid after the refund is issued for real.

Idempotency: rebates UNIQUE (student_id, gate_id) absorbs replayed pledges;
guarded UPDATEs absorb replayed passages; the cursor (rebate_cursor) only
ever moves forward and a crash replays at most one pass of harmless no-ops.

Deterministic clock: KEEL_REBATE_NOW (ISO 8601) overrides now() everywhere
(pledge times, expiry sweep, runbook marks) — a test/admin knob for proving
window expiry without sleeping; production leaves it unset.

Usage:
    KEEL_DB_CMD="... psql ..." python3 rebate/machine.py            # poll loop
    KEEL_REBATE_ONCE=1 ... python3 rebate/machine.py                # one pass
    ... machine.py --ledger                                        # audit dump
    ... machine.py --ledger <student_id>
    ... machine.py --mark-paid <rebate_id> --reason "stripe refund pi_..."
    ... machine.py --mark-forfeited <rebate_id> --reason "..."

Stdlib only; database access via the shared db.py (KEEL_DB_CMD convention).
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import db_sql, sql_str

CONSUMER = "rebate-machine"
GATE_EVENT_TYPES = ("gate.pledged", "gate.passed")
UNIT_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")  # 3.2.1 today; phase gates (5.9) fit

# Architecture §8: rebate portion is configurable, band 15-20%. 15 is the
# conservative default; anything outside the band is a founder decision.
DEFAULT_REBATE_PCT = 15
DEFAULT_WINDOW_DAYS = 365


class ConfigError(Exception):
    pass


def log(msg):
    sys.stdout.write("[rebate] %s\n" % msg)
    sys.stdout.flush()


def configured_gates():
    raw = os.environ.get("KEEL_REBATE_GATES", "phase-5-integration,capstone")
    gates = [g.strip() for g in raw.split(",") if g.strip()]
    if not gates:
        raise ConfigError("KEEL_REBATE_GATES resolved to an empty list")
    return gates


def rebate_pct():
    raw = os.environ.get("KEEL_REBATE_PCT", str(DEFAULT_REBATE_PCT))
    try:
        pct = float(raw)
    except ValueError:
        raise ConfigError("KEEL_REBATE_PCT is not a number: %r" % raw)
    if not (0 < pct <= 100):
        raise ConfigError("KEEL_REBATE_PCT must be in (0, 100]: %r" % raw)
    return pct


def window_days_for(gate_id, event_override=None):
    if event_override is not None:
        try:
            days = int(event_override)
        except (TypeError, ValueError):
            days = None
        if days is not None and days > 0:
            return days
    env = "KEEL_REBATE_WINDOW_DAYS_" + gate_id.upper().replace("-", "_")
    raw = os.environ.get(env) or os.environ.get("KEEL_REBATE_WINDOW_DAYS",
                                                str(DEFAULT_WINDOW_DAYS))
    try:
        days = int(raw)
    except ValueError:
        raise ConfigError("%s is not an integer: %r" % (env, raw))
    if days <= 0:
        raise ConfigError("%s must be positive: %r" % (env, raw))
    return days


def price_for_unit(unit_id):
    """Same convention as enroll/server.py (kept in sync deliberately; the
    enroll service owns checkout, the machine owns the rebate ledger, and
    both read the identical env knobs so a pledged amount always reconciles
    with what was charged)."""
    specific = os.environ.get("KEEL_PRICE_CENTS_" + unit_id.replace(".", "_"))
    if specific and specific.isdigit():
        return int(specific)
    fallback = os.environ.get("KEEL_PRICE_CENTS_DEFAULT", "4900")
    return int(fallback) if fallback.isdigit() else 4900


def now_sql():
    """SQL expression for the current instant: now(), or the KEEL_REBATE_NOW
    override as a timestamptz literal (deterministic proofs of expiry)."""
    raw = os.environ.get("KEEL_REBATE_NOW")
    if not raw:
        return "now()"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ConfigError("KEEL_REBATE_NOW is not an ISO timestamp: %r" % raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return "%s::timestamptz" % sql_str(parsed.isoformat())


def ts_literal(value):
    """Validate an ISO timestamp from an event payload and render it as a
    timestamptz literal. Returns None when absent/invalid."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return "%s::timestamptz" % sql_str(parsed.isoformat())


def append_rejected(reason, seq, payload):
    """Best-effort diagnostic: log why an attempt changed nothing. Never
    raises into the poll loop's event ordering."""
    db_sql(
        "BEGIN;\n"
        "INSERT INTO events (type, payload) VALUES ("
        "'rebate.rejected',"
        "jsonb_build_object('reason', %s::text,"
        "'source_event_seq', %s::bigint,"
        "'student_id', %s::text, 'gate_id', %s::text, 'unit_id', %s::text));\n"
        "COMMIT;\n" % (sql_str(reason), seq or "NULL",
                       sql_str(payload.get("student_id") or ""),
                       sql_str(payload.get("gate_id") or ""),
                       sql_str(payload.get("unit_id") or "")),
        want_rows=False,
    )
    log("rejected seq=%s reason=%s" % (seq, reason))


# ----------------------------------------------------------------------
# Event handlers — one transaction per event: row + transition + spine event
# commit atomically; a crash before the cursor advances replays the event
# into a harmless no-op.
# ----------------------------------------------------------------------

def handle_pledged(seq, payload):
    gates = configured_gates()
    gate = str(payload.get("gate_id") or "")
    unit = str(payload.get("unit_id") or "")
    sid = payload.get("student_id")
    if not str(sid or "").isdigit():
        append_rejected("bad_student_id", seq, payload)
        return
    sid = int(sid)
    if gate not in gates:
        append_rejected("unknown_gate", seq, payload)
        return
    if not UNIT_RE.match(unit):
        append_rejected("bad_unit_id", seq, payload)
        return
    days = window_days_for(gate, payload.get("window_days"))
    amount = int(price_for_unit(unit) * rebate_pct() // 100)
    if amount <= 0:
        append_rejected("price_too_small_for_rebate", seq, payload)
        return

    sql = """BEGIN;
WITH ins AS (
    INSERT INTO rebates (student_id, gate_id, unit_id, amount_cents,
                         currency, rebate_pct, window_days, window_ends_at)
    SELECT %d, %s, %s, %d, 'usd', %s::numeric, %d,
           %s + make_interval(days => %d)
    WHERE EXISTS (SELECT 1 FROM students WHERE id = %d)
    ON CONFLICT (student_id, gate_id) DO NOTHING
    RETURNING id, student_id, gate_id, unit_id, amount_cents, window_days
), tr AS (
    INSERT INTO rebate_transitions (rebate_id, from_status, to_status,
                                    actor, reason, source_event_seq)
    SELECT id, 'none', 'pending', 'rebate-machine', 'gate.pledged', %s::bigint
    FROM ins
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'rebate.pledged', jsonb_build_object(
               'rebate_id', id, 'student_id', student_id,
               'gate_id', gate_id, 'unit_id', unit_id,
               'amount_cents', amount_cents, 'currency', 'usd',
               'window_days', window_days,
               'source_event_seq', %s::bigint)
    FROM ins
)
SELECT COALESCE((SELECT id FROM ins), 0),
       EXISTS (SELECT 1 FROM students WHERE id = %d);
COMMIT;
""" % (sid, sql_str(gate), sql_str(unit), amount,
       sql_str("%.2f" % rebate_pct()), days, now_sql(), days,
       sid, seq, seq, sid)
    rows = db_sql(sql)
    rebate_id, student_exists = rows[0]
    if rebate_id == "0" and student_exists != "t":
        append_rejected("unknown_student", seq, payload)
        return
    if rebate_id == "0":
        log("pledge seq=%s absorbed (rebate already exists) student=%d gate=%s"
            % (seq, sid, gate))
        return
    log("pledged student=%d gate=%s rebate=%s amount=%dc window=%dd"
        % (sid, gate, rebate_id, amount, days))


def handle_passed(seq, payload, occurred_at=None):
    gate = str(payload.get("gate_id") or "")
    unit = str(payload.get("unit_id") or "")
    sid = payload.get("student_id")
    if not str(sid or "").isdigit():
        append_rejected("bad_student_id", seq, payload)
        return
    sid = int(sid)
    if gate not in configured_gates():
        append_rejected("unknown_gate", seq, payload)
        return
    passage = ts_literal(payload.get("passed_at"))
    if payload.get("passed_at") and passage is None:
        append_rejected("bad_passed_at", seq, payload)
        return
    if passage is None:
        # fall back to the event's own occurred_at, then the machine clock
        passage = ts_literal(occurred_at) or now_sql()

    sql = """BEGIN;
WITH upd AS (
    UPDATE rebates
    SET status = 'earned', earned_at = %s, earned_event_seq = %s::bigint
    WHERE student_id = %d AND gate_id = %s AND status = 'pending'
      AND unit_id = %s AND %s <= window_ends_at
    RETURNING id, student_id, gate_id, amount_cents, currency
), tr AS (
    INSERT INTO rebate_transitions (rebate_id, from_status, to_status,
                                    actor, reason, source_event_seq)
    SELECT id, 'pending', 'earned', 'rebate-machine', 'gate.passed', %s::bigint
    FROM upd
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'rebate.earned', jsonb_build_object(
               'rebate_id', id, 'student_id', student_id,
               'gate_id', gate_id, 'unit_id', %s::text,
               'amount_cents', amount_cents, 'currency', currency,
               'source_event_seq', %s::bigint)
    FROM upd
)
SELECT COALESCE((SELECT count(*) FROM upd), 0);
SELECT status, unit_id, earned_event_seq, window_ends_at
FROM rebates WHERE student_id = %d AND gate_id = %s;
COMMIT;
""" % (now_sql(), seq, sid, sql_str(gate), sql_str(unit), passage,
       seq, sql_str(unit), seq, sid, sql_str(gate))
    rows = db_sql(sql)
    earned_count = rows[0][0]
    if earned_count != "0":
        log("earned seq=%s student=%d gate=%s" % (seq, sid, gate))
        return
    if len(rows) < 2:
        append_rejected("no_pledge", seq, payload)
        return
    status, row_unit, earned_seq, window_ends = rows[1]
    if row_unit != unit:
        append_rejected("wrong_unit", seq, payload)
    elif earned_seq == str(seq):
        # the replay of the event that earned this rebate: silent no-op
        # whatever the current terminal status (paid/forfeited later on)
        log("passage seq=%s absorbed (replay of the earning event)" % seq)
    elif status != "pending":
        append_rejected("not_pending", seq, payload)
    else:
        # pending, right unit, but the guarded earn did not fire: the only
        # remaining guard is the window — passage landed outside it.
        append_rejected("out_of_window", seq, payload)


# ----------------------------------------------------------------------
# Timed transition + runbook marks
# ----------------------------------------------------------------------

def sweep_expired():
    sql = """BEGIN;
WITH upd AS (
    UPDATE rebates SET status = 'expired', expired_at = %s
    WHERE status = 'pending' AND %s > window_ends_at
    RETURNING id, student_id, gate_id, amount_cents
), tr AS (
    INSERT INTO rebate_transitions (rebate_id, from_status, to_status,
                                    actor, reason)
    SELECT id, 'pending', 'expired', 'rebate-machine',
           'window elapsed without gate passage'
    FROM upd
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'rebate.expired', jsonb_build_object(
               'rebate_id', id, 'student_id', student_id,
               'gate_id', gate_id, 'amount_cents', amount_cents)
    FROM upd
)
SELECT COALESCE((SELECT count(*) FROM upd), 0);
COMMIT;
""" % (now_sql(), now_sql())
    count = db_sql(sql)[0][0]
    if count != "0":
        log("expired %s rebate(s) (window elapsed)" % count)
    return int(count)


def runbook_mark(rebate_id, to_status):
    """earned -> paid | forfeited. Ledger only: prints the runbook banner and
    refuses anything that is not a forward transition from earned."""
    allowed = {"paid": ("paid_at", "rebate.paid"),
               "forfeited": ("forfeited_at", "rebate.forfeited")}
    ts_col, event_type = allowed[to_status]
    reason = os.environ.get("KEEL_REBATE_REASON", "runbook mark")
    actor = os.environ.get("KEEL_REBATE_ACTOR", "runbook")
    sql = """BEGIN;
WITH upd AS (
    UPDATE rebates SET status = '%s', %s = %s
    WHERE id = %d AND status = 'earned'
    RETURNING id, student_id, gate_id, amount_cents, currency
), tr AS (
    INSERT INTO rebate_transitions (rebate_id, from_status, to_status,
                                    actor, reason)
    SELECT id, 'earned', '%s', %s, %s FROM upd
), ev AS (
    INSERT INTO events (type, payload)
    SELECT '%s', jsonb_build_object(
               'rebate_id', id, 'student_id', student_id,
               'gate_id', gate_id, 'amount_cents', amount_cents,
               'currency', currency, 'actor', %s::text, 'reason', %s::text)
    FROM upd
)
SELECT COALESCE((SELECT count(*) FROM upd), 0);
COMMIT;
""" % (to_status, ts_col, now_sql(), rebate_id, to_status,
       sql_str(actor), sql_str(reason), event_type,
       sql_str(actor), sql_str(reason))
    count = db_sql(sql)[0][0]
    if count == "0":
        sys.stderr.write(
            "[rebate] refused: rebate %s is not in status 'earned' — "
            "transitions never move backwards\n" % rebate_id)
        return 1
    sys.stderr.write(
        "[rebate] LEDGER ONLY: rebate %s marked %s. No money moved — "
        "execute the actual refund per the payout runbook in "
        "platform/FOUNDER-WIRING.md\n" % (rebate_id, to_status))
    log("mark rebate=%s -> %s actor=%s reason=%s"
        % (rebate_id, to_status, actor, reason))
    return 0


def dump_ledger(student_id=None):
    where = "" if student_id is None else "WHERE r.student_id = %d" % student_id
    rows = db_sql(
        "BEGIN;\n"
        "SELECT r.id, r.student_id, s.email, r.gate_id, r.unit_id, r.status,\n"
        "       r.amount_cents, r.currency, r.rebate_pct, r.window_days,\n"
        "       r.pledged_at, r.window_ends_at, r.earned_at, r.paid_at,\n"
        "       r.forfeited_at, r.expired_at\n"
        "FROM rebates r JOIN students s ON s.id = r.student_id\n"
        "%s ORDER BY r.id;\n"
        "ROLLBACK;\n" % where)
    rebates = {}
    order = []
    for r in rows:
        rec = {
            "rebate_id": int(r[0]), "student_id": int(r[1]), "email": r[2],
            "gate_id": r[3], "unit_id": r[4], "status": r[5],
            "amount_cents": int(r[6]), "currency": r[7],
            "rebate_pct": r[8], "window_days": int(r[9]),
            "pledged_at": r[10], "window_ends_at": r[11],
            "earned_at": r[12] or None, "paid_at": r[13] or None,
            "forfeited_at": r[14] or None, "expired_at": r[15] or None,
            "transitions": [],
        }
        rebates[int(r[0])] = rec
        order.append(int(r[0]))
    if order:
        trows = db_sql(
            "BEGIN;\n"
            "SELECT rebate_id, from_status, to_status, actor, reason,\n"
            "       source_event_seq, occurred_at\n"
            "FROM rebate_transitions WHERE rebate_id IN (%s)\n"
            "ORDER BY id;\n"
            "ROLLBACK;\n" % ",".join(str(i) for i in order))
        for t in trows:
            rid = int(t[0])
            if rid in rebates:
                rebates[rid]["transitions"].append({
                    "from_status": t[1], "to_status": t[2], "actor": t[3],
                    "reason": t[4],
                    "source_event_seq": int(t[5]) if t[5] else None,
                    "occurred_at": t[6],
                })
    for rid in order:
        sys.stdout.write(json.dumps(rebates[rid], sort_keys=True) + "\n")


# ----------------------------------------------------------------------
# Poll loop
# ----------------------------------------------------------------------

def read_cursor():
    rows = db_sql(
        "BEGIN;\n"
        "SELECT COALESCE((SELECT last_seq FROM rebate_cursor\n"
        "                 WHERE consumer = %s), 0);\n"
        "ROLLBACK;\n" % sql_str(CONSUMER))
    return int(rows[0][0])


def advance_cursor(seq):
    db_sql(
        "BEGIN;\n"
        "INSERT INTO rebate_cursor (consumer, last_seq) VALUES (%s, %d)\n"
        "ON CONFLICT (consumer) DO UPDATE SET last_seq = EXCLUDED.last_seq\n"
        "WHERE EXCLUDED.last_seq > rebate_cursor.last_seq;\n"
        "COMMIT;\n" % (sql_str(CONSUMER), seq),
        want_rows=False)


def process_events():
    cursor = read_cursor()
    rows = db_sql(
        "BEGIN;\n"
        "SELECT seq, type, payload, occurred_at FROM events\n"
        "WHERE type IN ('gate.pledged', 'gate.passed') AND seq > %d\n"
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
        if etype == "gate.pledged":
            handle_pledged(seq, payload)
        else:
            handle_passed(seq, payload, occurred_at)
        advance_cursor(seq)
    return len(rows)


def run_once():
    processed = process_events()
    expired = sweep_expired()
    log("pass complete: %d event(s) processed, %d expiration(s)"
        % (processed, expired))


def main():
    args = sys.argv[1:]
    if args and args[0] == "--ledger":
        sid = int(args[1]) if len(args) > 1 else None
        dump_ledger(sid)
        return 0
    if args and args[0] in ("--mark-paid", "--mark-forfeited"):
        if len(args) < 2 or not args[1].isdigit():
            sys.stderr.write("usage: machine.py --mark-paid <rebate_id> "
                             "[--reason ...] (reason via KEEL_REBATE_REASON)\n")
            return 2
        # Fail fast on a bad KEEL_DB_CMD.
        db_sql("BEGIN;\nSELECT 1;\nROLLBACK;\n", want_rows=False)
        return runbook_mark(int(args[1]),
                            "paid" if args[0] == "--mark-paid" else "forfeited")
    if args:
        sys.stderr.write(
            "usage: machine.py [--ledger [student_id] | "
            "--mark-paid <id> | --mark-forfeited <id>]\n"
            "       (reason/actor for runbook marks via KEEL_REBATE_REASON / "
            "KEEL_REBATE_ACTOR)\n")
        return 2

    db_sql("BEGIN;\nSELECT 1;\nROLLBACK;\n", want_rows=False)
    if os.environ.get("KEEL_REBATE_ONCE", "0").lower() in ("1", "true", "yes"):
        run_once()
        return 0
    interval = float(os.environ.get("KEEL_REBATE_POLL_S", "2"))
    log("listening for %s + expiry sweep every %gs"
        % ("/".join(GATE_EVENT_TYPES), interval))
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigError as exc:
        sys.stderr.write("[rebate] config error: %s\n" % exc)
        sys.exit(2)
