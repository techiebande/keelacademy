#!/usr/bin/env python3
"""smoke-enroll-checks.py — assertions for smoke-enroll.sh (S2.5).

All HTTP is 127.0.0.1-only. The Stripe key in play is a placeholder the fake
never validates; the webhook secret is the shared test secret the fake signs
with, so the enroll server exercises its REAL verification path.
"""

import hashlib
import hmac
import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request

ENROLL = "http://127.0.0.1:%s" % os.environ["ENROLL_SMOKE_PORT"]
FAKE = "http://127.0.0.1:%s" % os.environ["ENROLL_SMOKE_FAKE_PORT"]
TOKEN = os.environ["ENROLL_SMOKE_TOKEN"]
WHSEC = os.environ["ENROLL_SMOKE_WEBHOOK_SECRET"]
DB_CMD = shlex.split(os.environ["ENROLL_SMOKE_DB_CMD"])
SERVER_PY = os.environ["ENROLL_SMOKE_SERVER_PY"]

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("PASS: %s" % name)
    else:
        FAIL += 1
        print("FAIL: %s%s" % (name, (" — %s" % detail) if detail else ""))


def http(method, url, body=None, headers=None):
    """Returns (status, parsed-json-or-None, response-headers)."""
    req = urllib.request.Request(url, data=body, headers=headers or {},
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            parsed = None
            try:
                parsed = json.loads(raw)
            except ValueError:
                pass
            return resp.status, parsed, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw), dict(exc.headers)
        except ValueError:
            return exc.code, None, dict(exc.headers)


def app_headers():
    return {"X-Keel-App-Token": TOKEN, "Content-Type": "application/json"}


def db_sql(sql):
    proc = subprocess.run(
        DB_CMD + ["-q", "-tA", "-F", "\t", "-v", "ON_ERROR_STOP=1"],
        input=sql.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode())
    return [tuple(l.split("\t")) for l in
            proc.stdout.decode().splitlines() if l.strip()]


def db_one(sql):
    rows = db_sql("BEGIN;\n%s\nROLLBACK;\n" % sql)
    return rows[0][0] if rows else None


def sign(body: bytes, secret: str, ts=None) -> str:
    t = str(ts if ts is not None else int(time.time()))
    mac = hmac.new(secret.encode(), ("%s." % t).encode() + body,
                   hashlib.sha256).hexdigest()
    return "t=%s,v1=%s" % (t, mac)


def webhook_event(session_id, student_id=1, unit_id="3.2.1"):
    body = json.dumps({
        "id": "evt_test_%s" % session_id,
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": session_id,
            "payment_status": "paid",
            "client_reference_id": str(student_id),
            "metadata": {"student_id": str(student_id), "unit_id": unit_id},
        }},
    }).encode()
    return body, {"Content-Type": "application/json",
                  "Stripe-Signature": sign(body, WHSEC)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


opener = urllib.request.build_opener(NoRedirect)

# ----------------------------------------------------------------------
print("== (a) health + app-token gate ==")
status, doc, _ = http("GET", ENROLL + "/healthz")
check("healthz answers", status == 200 and doc == {"ok": True})
status, doc, _ = http("GET", ENROLL + "/students/1/profile")
check("student read without token is 401", status == 401, str(doc))
status, doc, _ = http("GET", ENROLL + "/students/1/profile",
                      headers={"X-Keel-App-Token": "wrong-token"})
check("student read with wrong token is 401", status == 401)

# ----------------------------------------------------------------------
print("== (b) bridge: new identity creates + is idempotent ==")
body = json.dumps({"external_id": "auth_new_1", "email": "new.student@keel.test",
                   "name": "New Student"}).encode()
status, doc, _ = http("POST", ENROLL + "/auth/bridge", body, app_headers())
check("bridge creates a student row", status == 200 and doc.get("student_id"),
      str(doc))
NEW_ID = doc["student_id"]
status, doc2, _ = http("POST", ENROLL + "/auth/bridge", body, app_headers())
check("bridge replay returns the same id",
      status == 200 and doc2["student_id"] == NEW_ID)
check("bridge stored the external id",
      db_one("SELECT external_auth_id FROM students WHERE id = %d;" % NEW_ID)
      == "auth_new_1")

# ----------------------------------------------------------------------
print("== (c) bridge: signing up with a known pusher email claims that row ==")
ALICE = int(db_one("SELECT id FROM students WHERE email = 'alice@keel.test';"))
body = json.dumps({"external_id": "auth_alice_now", "email": "alice@keel.test",
                   "name": "Alice K"}).encode()
status, doc, _ = http("POST", ENROLL + "/auth/bridge", body, app_headers())
check("existing email links to the existing row",
      status == 200 and doc["student_id"] == ALICE, str(doc))
check("claim set external_auth_id on alice's row",
      db_one("SELECT external_auth_id FROM students WHERE id = %d;" % ALICE)
      == "auth_alice_now")

# ----------------------------------------------------------------------
print("== (d) bridge: another account claiming a linked email is a 409 ==")
body = json.dumps({"external_id": "auth_impostor", "email": "alice@keel.test",
                   "name": "Someone Else"}).encode()
status, doc, _ = http("POST", ENROLL + "/auth/bridge", body, app_headers())
check("conflicting claim rejected", status == 409, str(doc))
check("no extra student row appeared",
      db_one("SELECT count(*) FROM students WHERE email = 'alice@keel.test';") == "1")

# ----------------------------------------------------------------------
print("== (e) price endpoint honors env config ==")
status, doc, _ = http("GET", ENROLL + "/price?unit=3.2.1", headers=app_headers())
check("price is the configured 1234 cents",
      status == 200 and doc["amount_cents"] == 1234, str(doc))
status, doc, _ = http("GET", ENROLL + "/price?unit=../../etc", headers=app_headers())
check("bad unit id rejected", status == 400)

# ----------------------------------------------------------------------
print("== (f) checkout session creation via the fake stripe ==")
body = json.dumps({"student_id": NEW_ID, "unit_id": "3.2.1",
                   "success_url": "http://127.0.0.1:9/checkout/return?session_id={CHECKOUT_SESSION_ID}",
                   "cancel_url": "http://127.0.0.1:9/checkout/cancel"}).encode()
status, doc, _ = http("POST", ENROLL + "/checkout/session", body, app_headers())
CS1 = doc.get("stripe_session_id") if isinstance(doc, dict) else None
check("session created through the fake",
      status == 200 and CS1 == "cs_fake_000001"
      and doc["url"].startswith(FAKE + "/pay/"), str(doc))
check("checkout_sessions row is pending",
      db_one("SELECT status FROM checkout_sessions WHERE stripe_session_id = '%s';" % CS1)
      == "pending")
status, doc, _ = http("GET", FAKE + "/__count")
check("fake stripe saw exactly one session create",
      status == 200 and doc["sessions_created"] == 1)
bad = json.dumps({"student_id": 99999, "unit_id": "3.2.1",
                  "success_url": "http://x/s", "cancel_url": "http://x/c"}).encode()
status, doc, _ = http("POST", ENROLL + "/checkout/session", bad, app_headers())
check("unknown student cannot start checkout", status == 404)
bad = json.dumps({"student_id": NEW_ID, "unit_id": "9.9",
                  "success_url": "http://x/s", "cancel_url": "http://x/c"}).encode()
status, doc, _ = http("POST", ENROLL + "/checkout/session", bad, app_headers())
check("malformed unit id rejected", status == 422)
bad = json.dumps({"student_id": NEW_ID, "unit_id": "3.2.1",
                  "success_url": "javascript:alert(1)", "cancel_url": "http://x/c"}).encode()
status, doc, _ = http("POST", ENROLL + "/checkout/session", bad, app_headers())
check("non-http success_url rejected", status == 422)

# stripe_not_wired: with no key configured the service must say so, loudly,
# never silently fake a checkout.
probe = subprocess.run(
    [sys.executable, "-c",
     "import os,sys,importlib.util\n"
     "os.environ.pop('STRIPE_SECRET_KEY',None)\n"
     "spec=importlib.util.spec_from_file_location('enroll_srv',%r)\n"
     "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
     "try:\n"
     "    m.create_stripe_checkout_session('3.2.1',1234,1,'http://x/s','http://x/c')\n"
     "    sys.exit(1)\n"
     "except RuntimeError as e:\n"
     "    sys.exit(0 if 'stripe_not_wired' in str(e) else 2)\n" % SERVER_PY],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
check("no STRIPE_SECRET_KEY -> explicit stripe_not_wired",
      probe.returncode == 0, probe.stderr.decode()[-200:])

# ----------------------------------------------------------------------
print("== (g) full loop: pay on the fake page -> signed webhook -> enrollment ==")
req = urllib.request.Request(FAKE + "/pay/" + CS1, method="POST")
try:
    resp = opener.open(req, timeout=10)
    code, headers = resp.status, dict(resp.headers)
except urllib.error.HTTPError as exc:
    code, headers = exc.code, dict(exc.headers)
check("pay answers 302 to the success url",
      code == 302 and headers.get("Location") ==
      "http://127.0.0.1:9/checkout/return?session_id=" + CS1,
      "%s %s" % (code, headers.get("Location")))
check("checkout session completed",
      db_one("SELECT status FROM checkout_sessions WHERE stripe_session_id='%s';" % CS1)
      == "completed")
check("enrollment row active and linked",
      db_one("SELECT e.status || ':' || cs.stripe_session_id FROM enrollments e "
             "JOIN checkout_sessions cs ON cs.id = e.checkout_session_id "
             "WHERE e.student_id = %d AND e.unit_id = '3.2.1';" % NEW_ID)
      == "active:" + CS1)
check("exactly one enrollment.activated event",
      db_one("SELECT count(*) FROM events WHERE type = 'enrollment.activated' "
             "AND payload->>'student_id' = '%d';" % NEW_ID) == "1")
check("budget provisioned at the configured cap",
      db_one("SELECT tokens_cap || ':' || tokens_used FROM budgets "
             "WHERE student_id = %d;" % NEW_ID) == "5000:0")
status, doc, _ = http("GET", ENROLL + "/checkout/status?stripe_session_id=" + CS1,
                      headers=app_headers())
check("checkout status reports completed + enrolled",
      status == 200 and doc["status"] == "completed" and doc["enrolled"] is True)
status, doc, _ = http("GET", ENROLL + "/students/%d/profile" % NEW_ID,
                      headers=app_headers())
check("profile lists the enrollment and the budget",
      status == 200 and doc["enrollments"][0]["unit_id"] == "3.2.1"
      and doc["budget"]["tokens_cap"] == 5000, str(doc))

# ----------------------------------------------------------------------
print("== (h) replayed webhook must not double-enroll ==")
body, headers = webhook_event(CS1, student_id=NEW_ID)
before = db_one("SELECT count(*) FROM events WHERE type='enrollment.activated';")
completed_at = db_one("SELECT completed_at FROM checkout_sessions "
                      "WHERE stripe_session_id='%s';" % CS1)
status1, doc1, _ = http("POST", ENROLL + "/webhook/stripe", body, headers)
status2, doc2, _ = http("POST", ENROLL + "/webhook/stripe", body, headers)
check("both replays answered 200",
      status1 == 200 and status2 == 200, "%s %s" % (status1, status2))
check("second replay reports newly_enrolled=false",
      doc1.get("newly_enrolled") is False and doc2.get("newly_enrolled") is False,
      "%s %s" % (doc1, doc2))
check("still exactly one enrollment row",
      db_one("SELECT count(*) FROM enrollments WHERE student_id=%d;" % NEW_ID) == "1")
check("still exactly one activation event",
      db_one("SELECT count(*) FROM events WHERE type='enrollment.activated';") == before)
check("completed_at untouched by the replay",
      db_one("SELECT completed_at FROM checkout_sessions "
             "WHERE stripe_session_id='%s';" % CS1) == completed_at)

# ----------------------------------------------------------------------
print("== (i) tampered + stale signatures rejected with zero writes ==")
tampered = body.replace(b'"paid"', b'"PAID"')
status, doc, _ = http("POST", ENROLL + "/webhook/stripe", tampered, headers)
check("tampered body fails signature check", status == 400)
stale_body = body
stale_headers = {"Content-Type": "application/json",
                 "Stripe-Signature": sign(body, WHSEC, ts=int(time.time()) - 3600)}
status, doc, _ = http("POST", ENROLL + "/webhook/stripe", stale_body, stale_headers)
check("timestamp outside tolerance rejected", status == 400)
check("no webhook event rows or state changes from the rejects",
      db_one("SELECT count(*) FROM events WHERE type='enrollment.activated';") == before
      and db_one("SELECT count(*) FROM enrollments WHERE student_id=%d;" % NEW_ID) == "1")

# ----------------------------------------------------------------------
print("== (j) unknown checkout session: logged, never enrolled ==")
body, headers = webhook_event("cs_fake_999999", student_id=NEW_ID)
status, doc, _ = http("POST", ENROLL + "/webhook/stripe", body, headers)
check("unknown session acked 200", status == 200)
check("unknown session left a diagnostic event",
      db_one("SELECT count(*) FROM events "
             "WHERE type='enroll.unknown_checkout_session' "
             "AND payload->>'stripe_session_id' = 'cs_fake_999999';") == "1")
check("unknown session created no enrollment",
      db_one("SELECT count(*) FROM enrollments WHERE student_id=%d;" % NEW_ID) == "1")

# ----------------------------------------------------------------------
print("== (k) second checkout for an enrolled student cannot double-enroll ==")
body = json.dumps({"student_id": NEW_ID, "unit_id": "3.2.1",
                   "success_url": "http://127.0.0.1:9/ok?session_id={CHECKOUT_SESSION_ID}",
                   "cancel_url": "http://127.0.0.1:9/cancel"}).encode()
status, doc, _ = http("POST", ENROLL + "/checkout/session", body, app_headers())
CS2 = doc.get("stripe_session_id")
check("second session created", status == 200 and CS2 == "cs_fake_000002")
req = urllib.request.Request(FAKE + "/pay/" + CS2, method="POST")
try:
    resp = opener.open(req, timeout=10)
    code = resp.status
except urllib.error.HTTPError as exc:
    code = exc.code
check("second payment completed", code == 302)
check("still exactly one enrollment after the second payment",
      db_one("SELECT count(*) FROM enrollments WHERE student_id=%d;" % NEW_ID) == "1")
check("still exactly one activation event overall",
      db_one("SELECT count(*) FROM events WHERE type='enrollment.activated';") == before)

# ----------------------------------------------------------------------
print("== (l) student-scoped reads: alice sees her graded submission ==")
status, doc, _ = http("GET", ENROLL + "/students/%d/submissions" % ALICE,
                      headers=app_headers())
ok = (status == 200 and len(doc["submissions"]) == 1
      and doc["submissions"][0]["status"] == "graded"
      and doc["submissions"][0]["overall"] == "pass")
check("own-submissions list carries verdict overall", ok, str(doc))
status, doc, _ = http("GET", ENROLL + "/students/424242/submissions",
                      headers=app_headers())
check("unknown student is a 404", status == 404)

# ----------------------------------------------------------------------
print("== summary: %d passed, %d failed ==" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
