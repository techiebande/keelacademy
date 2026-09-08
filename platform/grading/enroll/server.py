#!/usr/bin/env python3
"""enroll/server.py — identity bridge + enrollment (S2.5 Stripe per-unit
legacy; S2.6 Paddle all-access subscription).

The learner app authenticates students with managed auth (Clerk in real
wiring, an offline fake in credential-free environments) but holds no
database credentials, exactly like the S2.4 reader. This service is the
write-side boundary between the two:

    GET  /healthz                       -> {"ok": true}
    POST /auth/bridge                   -> link auth identity to a students row
    GET  /students/<id>/profile         -> student row + enrollments + budget
    GET  /students/<id>/submissions     -> the student's own submissions
    GET  /price?unit=<unit-id>          -> configured price for a unit
    POST /checkout/session              -> create a Stripe Checkout session
    GET  /checkout/status?stripe_session_id=<id> -> pending/completed + enrolled
    POST /webhook/stripe                -> checkout.session.completed -> enroll

App-facing routes (everything but the webhook) authenticate with the header
X-Keel-App-Token, a shared secret from env KEEL_ENROLL_SECRET that lives in
the app's server environment only (never NEXT_PUBLIC, never a client bundle).
The webhook route instead verifies Stripe's own signature scheme, below.

Stripe calls. Session creation POSTs form-encoded fields exactly like the
real API (line_items[0][price_data][...] etc.) to KEEL_STRIPE_API_URL
(default https://api.stripe.com/v1) with the key from env STRIPE_SECRET_KEY
(env only; never logged; bearer only). Point KEEL_STRIPE_API_URL at
enroll/fake_stripe.py for the offline deterministic proof — same call shape,
zero network, zero credentials.

Webhook signature (byte-for-byte Stripe's documented scheme, verified over
the RAW body before any JSON parsing, mirroring intake's HMAC-first rule):
the Stripe-Signature header carries t=<unix-ts>,v1=<hex>; the expected v1 is
hex(HMAC-SHA256(KEEL_STRIPE_WEBHOOK_SECRET, "<t>." + raw_body)). A timestamp
outside KEEL_STRIPE_TOLERANCE_S (default 300; 0 disables the age check for
delayed-replay proofs) is rejected.

Idempotency. A replayed checkout.session.completed must not double-enroll:
enrollments UNIQUE (student_id, unit_id) with ON CONFLICT DO NOTHING is the
arbiter, and the enrollment.activated event is appended only when the insert
returned a row. Replays (and completions of a second checkout after the
student is already enrolled) return 200 with newly_enrolled=false. The
budget row the grading proxy requires is provisioned on first enrollment
(INSERT ... ON CONFLICT DO NOTHING, cap from KEEL_DEFAULT_BUDGET_TOKENS).

Database access follows the house convention: env KEEL_DB_CMD (shlex-split,
psql-compatible) via the shared db.py helper, one session per request.
"""

import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Add grading dir to sys.path to import shared db module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import db_sql, sql_str
import auth_core as auth  # sibling module; the script dir is sys.path[0]

MAX_BODY_BYTES = 5 * 1024 * 1024  # reject anything bigger before parsing
UNIT_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")  # unit "0.1" (curriculum) or a
# three-part section id; two-part is the real unit id shape (proof 2026-09-07)
STRIPE_CALL_TIMEOUT_S = 15


def app_token():
    return os.environ.get("KEEL_ENROLL_SECRET", "")


def price_for_unit(unit_id):
    """Unit price in cents: KEEL_PRICE_CENTS_<id with dots as underscores>,
    else KEEL_PRICE_CENTS_DEFAULT, else 4900."""
    specific = os.environ.get("KEEL_PRICE_CENTS_" + unit_id.replace(".", "_"))
    if specific and specific.isdigit():
        return int(specific)
    fallback = os.environ.get("KEEL_PRICE_CENTS_DEFAULT", "4900")
    return int(fallback) if fallback.isdigit() else 4900


def default_budget_tokens():
    try:
        return int(os.environ.get("KEEL_DEFAULT_BUDGET_TOKENS", "100000"))
    except ValueError:
        return 100000


def create_stripe_checkout_session(unit_id, amount_cents, student_id,
                                   success_url, cancel_url):
    """Call the Stripe API (real or fake — same wire shape) to create a
    Checkout Session. Returns (session_id, session_url) or raises
    RuntimeError with a short code for the caller to map to an HTTP status.

    Field names mirror https://docs.stripe.com/api/checkout/session/create:
    inline price_data so no Price object needs to pre-exist; metadata and
    client_reference_id carry the student/unit so the webhook can enroll
    without trusting anything else in the payload.
    """
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise RuntimeError("stripe_not_wired")
    base = os.environ.get("KEEL_STRIPE_API_URL", "https://api.stripe.com/v1")
    fields = {
        "mode": "payment",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(amount_cents),
        "line_items[0][price_data][product_data][name]":
            "Keel Academy unit %s" % unit_id,
        "client_reference_id": str(student_id),
        "metadata[student_id]": str(student_id),
        "metadata[unit_id]": unit_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/checkout/sessions",
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=STRIPE_CALL_TIMEOUT_S) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Never echo the body upstream sent; it can echo the bearer key.
        sys.stderr.write("enroll: stripe answered HTTP %d\n" % exc.code)
        raise RuntimeError("stripe_error")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        sys.stderr.write("enroll: stripe call failed: %s\n" % type(exc).__name__)
        raise RuntimeError("stripe_unreachable")

    session_id = doc.get("id")
    session_url = doc.get("url")
    if not session_id or not session_url:
        raise RuntimeError("stripe_bad_response")
    return session_id, session_url


def verify_stripe_signature(raw, header, secret, tolerance_s):
    """Stripe's scheme: t and v1 pairs in the header; v1 must equal
    HMAC-SHA256(secret, "<t>." + raw_body). Constant-time compare; the
    timestamp age check is skipped when tolerance_s is 0."""
    if not secret:
        return False
    parts = {}
    for item in header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts.setdefault(k.strip(), v.strip())
    ts = parts.get("t", "")
    v1 = parts.get("v1", "")
    if not ts or not v1:
        return False
    if tolerance_s > 0:
        try:
            age = abs(int(time.time()) - int(ts))
        except ValueError:
            return False
        if age > tolerance_s:
            return False
    expected = hmac.new(
        secret.encode(), ("%s." % ts).encode() + raw, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(v1, expected)


# ----------------------------------------------------------------------
# S2.6 all-access subscription (Paddle Billing). KEEL_BILLING_PROVIDER
# selects the surface: paddle (real API), stripe (S2.5 per-unit legacy),
# fake (offline deterministic proof, enroll/fake_paddle.py — same wire
# shapes as the real API, including the {"data": ...} envelope).
# ----------------------------------------------------------------------

PADDLE_CALL_TIMEOUT_S = 15


def billing_provider():
    return os.environ.get("KEEL_BILLING_PROVIDER", "fake")


def paddle_api():
    """(base_url, bearer_key) for the Paddle Billing API (real or fake —
    same wire shapes). The key is env-only, never logged. With provider
    paddle a missing key is a hard error; with fake the key is a
    placeholder (the fake accepts but never validates it)."""
    key = os.environ.get("PADDLE_API_KEY", "")
    if billing_provider() == "paddle" and not key:
        raise RuntimeError("paddle_not_wired")
    if billing_provider() == "fake":
        base = os.environ.get("KEEL_FAKE_PADDLE_URL", "http://127.0.0.1:8798")
    else:
        base = os.environ.get("KEEL_PADDLE_API_URL", "https://api.paddle.com")
    return base.rstrip("/"), key


def paddle_call(method, path, doc=None):
    """One Paddle API call. Real Paddle wraps every response in
    {"data": ...} and answers 201 on create; the fake mirrors both.
    Returns the inner data. Errors raise RuntimeError with a short code —
    never the response body, which can echo the bearer key."""
    base, key = paddle_api()
    body = json.dumps(doc).encode() if doc is not None else None
    req = urllib.request.Request(
        base + path,
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=PADDLE_CALL_TIMEOUT_S) as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        sys.stderr.write("enroll: paddle answered HTTP %d\n" % exc.code)
        raise RuntimeError("paddle_error")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        sys.stderr.write("enroll: paddle call failed: %s\n"
                         % type(exc).__name__)
        raise RuntimeError("paddle_unreachable")
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if data is None:
        raise RuntimeError("paddle_bad_response")
    return data


def paddle_price_info(price_id):
    """(amount_cents, currency) for the all-access price. On the real API
    unit_price.amount is a STRING in lowest currency units."""
    data = paddle_call("GET", "/prices/" + price_id)
    up = data.get("unit_price") or {}
    amount = str(up.get("amount") or "")
    if not amount.isdigit():
        raise RuntimeError("paddle_bad_response")
    return int(amount), str(up.get("currency_code") or "USD").lower()


def paddle_subscription_checkout(student_id, student_email, display_name,
                                 success_url):
    """Create (or reuse) a Paddle subscription checkout. Real Paddle: POST
    /customers (once per student), then POST /transactions with
    items/price_id + customer_id + checkout:{url} + custom_data. The
    webhook resolves the student from custom_data.student_id; the
    subscription_signups row (written by the caller) is the fallback.
    Returns (transaction_id, checkout_url, customer_id, price_id)."""
    price_id = os.environ.get("PADDLE_PRICE_ID", "")
    if not price_id:
        raise RuntimeError("paddle_not_wired")
    rows = db_sql(
        "BEGIN;\n"
        "SELECT customer_id, transaction_id FROM subscription_signups\n"
        "WHERE student_id = %d ORDER BY id DESC LIMIT 1;\n"
        "ROLLBACK;\n" % student_id
    )
    customer_id, txn_id = ("", "")
    if rows:
        customer_id, txn_id = str(rows[0][0]), str(rows[0][1])
    if customer_id and txn_id:
        # Reuse the previous signup while its transaction is still payable
        # (a refresh of the checkout page must not stack up transactions).
        txn = paddle_call("GET", "/transactions/" + txn_id)
        if str(txn.get("status") or "") in ("ready", "draft"):
            url = (txn.get("checkout") or {}).get("url")
            if url:
                return txn_id, str(url), customer_id, price_id
    if not customer_id:
        customer = paddle_call("POST", "/customers", {
            "email": student_email,
            "name": display_name,
        })
        customer_id = str(customer.get("id") or "")
        if not customer_id:
            raise RuntimeError("paddle_bad_response")
    txn = paddle_call("POST", "/transactions", {
        "items": [{"price_id": price_id, "quantity": 1}],
        "customer_id": customer_id,
        "custom_data": {"student_id": student_id},
        "checkout": {"url": success_url},
    })
    txn_id = str(txn.get("id") or "")
    url = (txn.get("checkout") or {}).get("url")
    if not txn_id or not url:
        raise RuntimeError("paddle_bad_response")
    return txn_id, str(url), customer_id, price_id


def verify_paddle_signature(raw, header, secret, tolerance_s):
    """Paddle's scheme: header Paddle-Signature: ts=<unix-ts>;h1=<hex>; the
    expected h1 is hex(HMAC-SHA256(secret, "<ts>:" + raw_body)). Verified
    over the RAW body before any JSON parsing. Constant-time compare; the
    timestamp age check is skipped when tolerance_s is 0."""
    if not secret:
        return False
    parts = {}
    for item in header.split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            parts.setdefault(k.strip(), v.strip())
    ts = parts.get("ts", "")
    h1 = parts.get("h1", "")
    if not ts or not h1:
        return False
    if tolerance_s > 0:
        try:
            age = abs(int(time.time()) - int(ts))
        except ValueError:
            return False
        if age > tolerance_s:
            return False
    expected = hmac.new(
        secret.encode(), ("%s:" % ts).encode() + raw, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(h1, expected)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Minimal logging; never log headers (they carry tokens/signatures)
        # or bodies (they carry student emails).
        sys.stderr.write("enroll: %s %s\n" % (self.command, self.path))

    def _read_body(self):
        """Read Content-Length bytes with a hard cap and guarded parse.
        Returns (ok, raw)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return False, b""
        if length < 0 or length > MAX_BODY_BYTES:
            return False, b""
        return True, self.rfile.read(length) if length else b""

    def _app_authorized(self):
        expected = app_token()
        if not expected:
            return False
        supplied = self.headers.get("X-Keel-App-Token", "")
        return hmac.compare_digest(supplied, expected)

    def _bad_token(self):
        self._respond(401, {"error": "invalid app token"})

    # ------------------------------------------------------------------
    # GET routes
    # ------------------------------------------------------------------

    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, {"ok": True})
            return

        if not self._app_authorized():
            self._bad_token()
            return

        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/price":
            unit = (query.get("unit") or [""])[0]
            if not UNIT_RE.match(unit):
                self._respond(400, {"error": "bad unit id"})
                return
            self._respond(200, {
                "unit_id": unit,
                "amount_cents": price_for_unit(unit),
                "currency": "usd",
            })
            return

        if parsed.path == "/subscription/price":
            # GET: the app fetches the all-access price for the checkout
            # page before offering the subscribe button.
            self._handle_subscription_price()
            return

        if parsed.path == "/subscription/status":
            self._handle_subscription_status()
            return

        if parsed.path == "/checkout/status":
            sid = (query.get("stripe_session_id") or [""])[0]
            if not re.match(r"^[A-Za-z0-9_\-]{1,128}$", sid):
                self._respond(400, {"error": "bad session id"})
                return
            rows = db_sql(
                "BEGIN;\n"
                "SELECT cs.status, e.id\n"
                "FROM checkout_sessions cs\n"
                "LEFT JOIN enrollments e\n"
                "  ON e.checkout_session_id = cs.id\n"
                "WHERE cs.stripe_session_id = %s;\n"
                "ROLLBACK;\n" % sql_str(sid)
            )
            if not rows:
                self._respond(404, {"error": "not_found"})
                return
            self._respond(200, {
                "stripe_session_id": sid,
                "status": rows[0][0],
                "enrolled": rows[0][1] != "",
            })
            return

        m = re.match(r"^/students/(\d{1,15})/(profile|submissions)$", parsed.path)
        if m:
            self._student_route(int(m.group(1)), m.group(2))
            return

        self._respond(404, {"error": "not found"})

    def _student_route(self, student_id, which):
        # SELECTs only; tab-scrub the human-free-text columns (db.py splits
        # rows on tab). The profile script tags each statement's rows ('S',
        # 'E', 'B', 'R') so the four result sets parse unambiguously.
        if which == "profile":
            rows = db_sql(
                "BEGIN;\n"
                "SELECT 'S', id, email, replace(display_name, chr(9), ' ')\n"
                "FROM students WHERE id = %d;\n"
                "SELECT 'E', unit_id, status, enrolled_at FROM enrollments\n"
                "WHERE student_id = %d ORDER BY unit_id;\n"
                "SELECT 'B', tokens_cap, tokens_used FROM budgets\n"
                "WHERE student_id = %d;\n"
                "SELECT 'R', gate_id, status, amount_cents, currency,\n"
                "        pledged_at, window_ends_at, earned_at, paid_at,\n"
                "        forfeited_at, expired_at\n"
                "FROM rebates WHERE student_id = %d ORDER BY id;\n"
                "ROLLBACK;\n" % (student_id, student_id, student_id, student_id)
            )
            student = next((r for r in rows if r[0] == "S"), None)
            if not student:
                self._respond(404, {"error": "not_found"})
                return
            enrollments = [
                {"unit_id": r[1], "status": r[2], "enrolled_at": r[3]}
                for r in rows if r[0] == "E"
            ]
            budget_rows = [r for r in rows if r[0] == "B"]
            budget = {"tokens_cap": int(budget_rows[0][1]),
                      "tokens_used": int(budget_rows[0][2])} if budget_rows \
                else None
            rebates = [
                {"gate_id": r[1], "status": r[2], "amount_cents": int(r[3]),
                 "currency": r[4], "pledged_at": r[5], "window_ends_at": r[6],
                 "earned_at": r[7] or None, "paid_at": r[8] or None,
                 "forfeited_at": r[9] or None, "expired_at": r[10] or None}
                for r in rows if r[0] == "R"
            ]
            self._respond(200, {
                "student_id": int(student[1]),
                "email": student[2],
                "display_name": student[3] or None,
                "enrollments": enrollments,
                "budget": budget,
                "rebates": rebates,
            })
            return

        # which == "submissions": the auth-gated list for /me. Includes the
        # verdict overall when graded, so the list can show pass/fail without
        # a second round trip to the reader. Unknown student -> 404 (an empty
        # list is reserved for a real student with no submissions yet).
        exists = db_sql(
            "BEGIN;\n"
            "SELECT id FROM students WHERE id = %d;\n"
            "ROLLBACK;\n" % student_id
        )
        if not exists:
            self._respond(404, {"error": "not_found"})
            return
        rows = db_sql(
            "BEGIN;\n"
            "SELECT s.id, s.unit_id, s.status, s.created_at, v.overall\n"
            "FROM submissions s\n"
            "LEFT JOIN verdicts v ON v.submission_id = s.id\n"
            "WHERE s.student_id = %d\n"
            "ORDER BY s.id DESC;\n"
            "ROLLBACK;\n" % student_id
        )
        self._respond(200, {"submissions": [
            {"id": int(r[0]), "unit_id": r[1], "status": r[2],
             "created_at": r[3], "overall": r[4] or None}
            for r in rows
        ]})

    # ------------------------------------------------------------------
    # POST routes
    # ------------------------------------------------------------------

    def do_POST(self):
        if self.path == "/webhook/paddle":
            self._handle_paddle_webhook()
            return
        if self.path == "/webhook/stripe":
            self._handle_webhook()
            return

        if not self._app_authorized():
            # Drain the body before answering so keep-alive parsing of the
            # next request on this connection starts at the right offset.
            self._read_body()
            self._bad_token()
            return

        if self.path == "/auth/bridge":
            self._handle_bridge()
            return
        if self.path in ("/auth/signup", "/auth/login", "/auth/session",
                         "/auth/logout", "/auth/oauth",
                         "/auth/reset/request", "/auth/reset/confirm"):
            self._handle_auth(self.path)
            return
        if self.path == "/checkout/session":
            self._handle_checkout_session()
            return
        if self.path == "/subscription/price":
            self._handle_subscription_price()
            return
        if self.path == "/checkout/subscription":
            self._handle_subscription_checkout()
            return
        if self.path == "/enroll":
            self._handle_enroll()
            return
        self._respond(404, {"error": "not found"})

    def _handle_auth(self, route: str):
        """Self-owned auth endpoints (0015): all POST JSON behind the app
        token, implemented in auth_core. Errors map to (status, code)."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw) if raw else {}
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return
        try:
            if route == "/auth/signup":
                result = auth.signup(str(payload.get("email") or ""),
                                     str(payload.get("password") or ""),
                                     payload.get("name"))
            elif route == "/auth/login":
                result = auth.login(str(payload.get("email") or ""),
                                    str(payload.get("password") or ""))
            elif route == "/auth/session":
                user = auth.session_user(str(payload.get("session_token") or ""))
                if not user:
                    self._respond(404, {"error": "no_session"})
                    return
                self._respond(200, {"user": user})
                return
            elif route == "/auth/logout":
                auth.revoke_session(str(payload.get("session_token") or ""))
                self._respond(200, {"ok": True})
                return
            elif route == "/auth/oauth":
                result = auth.oauth_login(
                    str(payload.get("provider") or ""),
                    str(payload.get("subject") or ""),
                    str(payload.get("email") or ""),
                    payload.get("name"))
            elif route == "/auth/reset/request":
                auth.request_reset(str(payload.get("email") or ""))
                self._respond(200, {"ok": True})
                return
            else:  # /auth/reset/confirm
                auth.confirm_reset(str(payload.get("token") or ""),
                                   str(payload.get("password") or ""))
                self._respond(200, {"ok": True})
                return
            self._respond(200, result)
        except auth.AuthError as exc:
            self._respond(exc.status, {"error": exc.code})
        except RuntimeError:
            self._respond(500, {"error": "database error"})

    def _handle_bridge(self):
        """Link a managed-auth identity to a students row.

        Resolution order: existing row by external_auth_id; else existing row
        by email with a NULL external_auth_id (claim it — this is how a
        student who pushed submissions before signing up keeps their
        history); else insert a new row. An email already linked to a
        DIFFERENT auth account is a 409, not a silent merge.
        """
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return
        external_id = str(payload.get("external_id") or "")
        email = str(payload.get("email") or "").strip().lower()
        name = payload.get("name")
        if not external_id or len(external_id) > 191 \
                or "@" not in email or len(email) > 320:
            self._respond(422, {"error": "external_id and a valid email are required"})
            return
        if name is not None:
            name = str(name).replace("\t", " ")[:200]

        sql = """BEGIN;
WITH existing AS (
    SELECT id FROM students WHERE external_auth_id = %s
), claimed AS (
    UPDATE students SET external_auth_id = %s
    WHERE email = %s AND external_auth_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM existing)
    RETURNING id
), inserted AS (
    INSERT INTO students (email, display_name, external_auth_id)
    SELECT %s, %s, %s
    WHERE NOT EXISTS (SELECT 1 FROM existing)
      AND NOT EXISTS (SELECT 1 FROM claimed)
      AND NOT EXISTS (SELECT 1 FROM students WHERE email = %s AND external_auth_id IS NOT NULL)
    RETURNING id
), renamed AS (
    UPDATE students SET display_name = COALESCE(%s, display_name)
    WHERE id IN (SELECT id FROM existing UNION SELECT id FROM claimed
                 UNION SELECT id FROM inserted)
      AND %s IS NOT NULL
    RETURNING id
)
SELECT COALESCE((SELECT id FROM existing), (SELECT id FROM claimed),
                (SELECT id FROM inserted)),
       EXISTS (SELECT 1 FROM students WHERE email = %s
               AND external_auth_id IS NOT NULL
               AND external_auth_id <> %s);
COMMIT;
""" % (
            sql_str(external_id), sql_str(external_id), sql_str(email),
            sql_str(email), sql_str(name), sql_str(external_id), sql_str(email),
            sql_str(name), sql_str(name),
            sql_str(email), sql_str(external_id),
        )
        try:
            rows = db_sql(sql)
        except RuntimeError:
            self._respond(500, {"error": "database error"})
            return
        student_id, email_taken = rows[0]
        if not student_id:
            self._respond(409, {"error": "email_linked_to_other_account"})
            return
        self._respond(200, {"ok": True, "student_id": int(student_id)})

    def _handle_checkout_session(self):
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return
        student_id = payload.get("student_id")
        unit_id = str(payload.get("unit_id") or "")
        success_url = str(payload.get("success_url") or "")
        cancel_url = str(payload.get("cancel_url") or "")
        if not isinstance(student_id, int) or not UNIT_RE.match(unit_id) \
                or not success_url.startswith(("http://", "https://")) \
                or not cancel_url.startswith(("http://", "https://")):
            self._respond(422, {"error": "student_id, unit_id, success_url, cancel_url required"})
            return

        # The student must exist (the app bridges the identity first).
        rows = db_sql(
            "BEGIN;\n"
            "SELECT id FROM students WHERE id = %d;\n"
            "ROLLBACK;\n" % student_id
        )
        if not rows:
            self._respond(404, {"error": "unknown student"})
            return

        amount = price_for_unit(unit_id)
        try:
            session_id, session_url = create_stripe_checkout_session(
                unit_id, amount, student_id, success_url, cancel_url
            )
        except RuntimeError as exc:
            code = str(exc)
            status = {"stripe_not_wired": 503,
                      "stripe_unreachable": 502,
                      "stripe_error": 502,
                      "stripe_bad_response": 502}.get(code, 502)
            self._respond(status, {"error": code})
            return

        # Already enrolled? Real Stripe would still take the money, so the
        # app must not offer the button; the service double-checks and marks
        # the session expired so a stale tab cannot enroll-and-charge again.
        try:
            db_sql(
                "BEGIN;\n"
                "INSERT INTO checkout_sessions\n"
                "  (stripe_session_id, student_id, unit_id, amount_cents)\n"
                "VALUES (%s, %d, %s, %d);\n"
                "COMMIT;\n" % (sql_str(session_id), student_id,
                               sql_str(unit_id), amount),
                want_rows=False,
            )
        except RuntimeError:
            self._respond(500, {"error": "database error"})
            return
        self._respond(200, {
            "ok": True,
            "stripe_session_id": session_id,
            "url": session_url,
            "amount_cents": amount,
            "currency": "usd",
        })

    def _handle_subscription_price(self):
        """All-access price for the checkout page. Sourced from the billing
        provider (fake or real Paddle API) so the number on the page is
        always the price Paddle will actually charge."""
        price_id = os.environ.get("PADDLE_PRICE_ID", "")
        if not price_id:
            self._respond(503, {"error": "paddle_not_wired"})
            return
        try:
            amount, currency = paddle_price_info(price_id)
        except RuntimeError as exc:
            code = str(exc)
            self._respond({"paddle_not_wired": 503}.get(code, 502),
                          {"error": code})
            return
        self._respond(200, {
            "price_id": price_id,
            "amount_cents": amount,
            "currency": currency,
            "interval": "month",
        })

    def _handle_subscription_checkout(self):
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return
        student_id = payload.get("student_id")
        success_url = str(payload.get("success_url") or "")
        if not isinstance(student_id, int) \
                or not success_url.startswith(("http://", "https://")):
            self._respond(422, {"error": "student_id and success_url required"})
            return
        rows = db_sql(
            "BEGIN;\n"
            "SELECT email, replace(display_name, chr(9), ' ') FROM students\n"
            "WHERE id = %d;\n"
            "ROLLBACK;\n" % student_id
        )
        if not rows:
            self._respond(404, {"error": "unknown student"})
            return
        email, display_name = str(rows[0][0]), (rows[0][1] or None)
        try:
            txn_id, url, customer_id, price_id = paddle_subscription_checkout(
                student_id, email, display_name, success_url)
        except RuntimeError as exc:
            code = str(exc)
            status = {"paddle_not_wired": 503}.get(code, 502)
            self._respond(status, {"error": code})
            return
        try:
            db_sql(
                "BEGIN;\n"
                "INSERT INTO subscription_signups\n"
                "  (transaction_id, customer_id, student_id)\n"
                "VALUES (%s, %s, %d)\n"
                "ON CONFLICT (transaction_id) DO UPDATE\n"
                "  SET customer_id = EXCLUDED.customer_id,\n"
                "      student_id = EXCLUDED.student_id;\n"
                "COMMIT;\n" % (sql_str(txn_id), sql_str(customer_id),
                              student_id),
                want_rows=False,
            )
        except RuntimeError:
            self._respond(500, {"error": "database error"})
            return
        self._respond(200, {
            "ok": True,
            "transaction_id": txn_id,
            "url": url,
            "amount_cents": None,
            "currency": None,
            "price_id": price_id,
        })

    def _handle_enroll(self):
        """Grant unit access because the student holds an ACTIVE
        subscription (owner decision 2026-09-07: enrollment follows the
        subscription, not a per-unit payment). Idempotent: the enrollments
        UNIQUE (student_id, unit_id) arbiter + ON CONFLICT DO NOTHING make
        replays no-ops; the enrollment.activated event is appended only
        when the insert returned a row. The budget row the grading proxy
        requires is provisioned on first enrollment, exactly like the
        webhook path."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        try:
            payload = json.loads(raw)
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return
        student_id = payload.get("student_id")
        unit_id = str(payload.get("unit_id") or "")
        if not isinstance(student_id, int) or not UNIT_RE.match(unit_id):
            self._respond(422, {"error": "student_id and unit_id required"})
            return
        rows = db_sql(
            "BEGIN;\n"
            "SELECT 1 FROM subscriptions\n"
            "WHERE student_id = %d AND status IN ('active','trialing');\n"
            "ROLLBACK;\n" % student_id
        )
        if not rows:
            # No active subscription. Distinguish an unknown student (404)
            # from a known one without access (402) so the app can show the
            # checkout page instead of an error.
            exists = db_sql(
                "BEGIN;\nSELECT id FROM students WHERE id = %d;\nROLLBACK;\n"
                % student_id
            )
            self._respond(404 if not exists else 402,
                          {"error": "unknown_student" if not exists
                                    else "no_active_subscription"})
            return
        sql = """BEGIN;
WITH ins AS (
    INSERT INTO enrollments (student_id, unit_id)
    VALUES (%d, %s)
    ON CONFLICT (student_id, unit_id) DO NOTHING
    RETURNING id, student_id, unit_id
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'enrollment.activated',
           jsonb_build_object('student_id', student_id,
                              'unit_id', unit_id::text,
                              'subscription', true)
    FROM ins RETURNING id
), bud AS (
    INSERT INTO budgets (student_id, tokens_cap, tokens_used)
    SELECT student_id, %d, 0 FROM ins
    ON CONFLICT (student_id) DO NOTHING
    RETURNING student_id
)
SELECT EXISTS (SELECT 1 FROM ins);
COMMIT;
""" % (student_id, sql_str(unit_id), default_budget_tokens())
        try:
            ins_rows = db_sql(sql)
        except RuntimeError:
            self._respond(500, {"error": "database error"})
            return
        self._respond(200, {
            "ok": True,
            "enrolled": True,
            "newly_enrolled": ins_rows[0][0] == "t",
        })

    def _handle_paddle_webhook(self):
        """Paddle Billing webhook. Paddle retries any non-2xx (sandbox:
        3 tries over ~15 minutes) and re-sends the identical payload with
        the same event_id, so handlers are convergent: UPSERT to the
        latest state keyed by the Paddle entity id. Events are NOT
        ordered — subscription.updated can arrive before
        subscription.created."""
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        secret = os.environ.get("KEEL_PADDLE_WEBHOOK_SECRET", "")
        if not secret:
            sys.stderr.write("enroll: paddle webhook refused: "
                             "KEEL_PADDLE_WEBHOOK_SECRET not set\n")
            self._respond(503, {"error": "server misconfigured"})
            return
        try:
            tolerance = int(os.environ.get("KEEL_PADDLE_TOLERANCE_S", "300"))
        except ValueError:
            tolerance = 300
        header = self.headers.get("Paddle-Signature", "")
        if not verify_paddle_signature(raw, header, secret, tolerance):
            self._respond(400, {"error": "invalid signature"})
            return
        try:
            event = json.loads(raw)
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return
        etype = str(event.get("event_type") or "")
        d = event.get("data") or {}

        if etype == "transaction.completed":
            txn_id = str(d.get("id") or "")
            if not txn_id:
                self._respond(400, {"error": "event carries no transaction id"})
                return
            custom = d.get("custom_data") or {}
            sid = custom.get("student_id")
            if sid is None or str(sid).strip() == "" \
                    or not str(sid).strip().lstrip("-").isdigit():
                sid = None
            else:
                sid = int(str(sid).strip())
            sub_id = str(d.get("subscription_id") or "") or None
            totals = (d.get("details") or {}).get("totals") or {}
            amount = str(totals.get("total") or "")
            amount = int(amount) if amount.isdigit() else 0
            currency = str(d.get("currency_code") or "USD").lower()
            if sid is None:
                sid_rows = db_sql(
                    "BEGIN;\n"
                    "SELECT student_id FROM subscription_signups\n"
                    "WHERE transaction_id = %s;\n"
                    "ROLLBACK;\n" % sql_str(txn_id)
                )
                sid = int(sid_rows[0][0]) if sid_rows else None
            db_sql(
                "BEGIN;\n"
                "INSERT INTO payments (paddle_transaction_id, student_id,\n"
                "                      paddle_subscription_id, amount_cents,\n"
                "                      currency)\n"
                "VALUES (%s, %s, %s, %d, %s)\n"
                "ON CONFLICT (paddle_transaction_id) DO UPDATE\n"
                "  SET student_id = COALESCE(EXCLUDED.student_id,\n"
                "                            payments.student_id),\n"
                "      paddle_subscription_id =\n"
                "        COALESCE(EXCLUDED.paddle_subscription_id,\n"
                "                 payments.paddle_subscription_id),\n"
                "      amount_cents = EXCLUDED.amount_cents,\n"
                "      currency = EXCLUDED.currency;\n"
                "COMMIT;\n" % (sql_str(txn_id),
                              str(sid) if sid is not None else "NULL",
                              sql_str(sub_id) if sub_id else "NULL",
                              amount, sql_str(currency)),
                want_rows=False,
            )
            self._respond(200, {"ok": True, "handled": True})
            return

        if etype in ("subscription.created", "subscription.updated",
                     "subscription.canceled"):
            sub = d
            sub_id = str(sub.get("id") or "")
            if not sub_id:
                self._respond(400, {"error": "event carries no subscription id"})
                return
            status = str(sub.get("status") or "")
            if status not in ("active", "trialing", "past_due",
                              "paused", "canceled"):
                status = "canceled"
            items = sub.get("items") or []
            price_id = ""
            if items and isinstance(items[0], dict):
                price_id = str((items[0].get("price") or {}).get("id") or "")
            custom = sub.get("custom_data") or {}
            sid = custom.get("student_id")
            if sid is None or str(sid).strip() == "" \
                    or not str(sid).strip().lstrip("-").isdigit():
                sid = None
            else:
                sid = int(str(sid).strip())
            customer_id = str(sub.get("customer_id") or "")
            scheduled = sub.get("scheduled_change") or None
            ends = ((sub.get("current_billing_period") or {}).get("ends_at")
                    or sub.get("next_billed_at") or "")
            if sid is None:
                # Fallback chain: the customer -> signup link (written at
                # checkout creation), else an existing subscription row.
                sid_rows = db_sql(
                    "BEGIN;\n"
                    "SELECT s.student_id FROM subscription_signups s\n"
                    "WHERE s.customer_id = %s\n"
                    "UNION ALL\n"
                    "SELECT b.student_id FROM subscriptions b\n"
                    "WHERE b.paddle_subscription_id = %s;\n"
                    "ROLLBACK;\n" % (sql_str(customer_id), sql_str(sub_id))
                )
                if not sid_rows:
                    db_sql(
                        "BEGIN;\n"
                        "INSERT INTO events (type, payload) VALUES (\n"
                        "'enroll.unknown_paddle_subscription',\n"
                        "jsonb_build_object('paddle_subscription_id', %s::text,\n"
                        "                   'customer_id', %s::text));\n"
                        "COMMIT;\n" % (sql_str(sub_id), sql_str(customer_id)),
                        want_rows=False,
                    )
                    self._respond(200, {"ok": True, "handled": False})
                    return
                sid = int(sid_rows[0][0])
            ends_sql = ("'%s'::timestamptz" % str(ends).replace("'", "''")) \
                if ends else "NULL"
            db_sql(
                "BEGIN;\n"
                "INSERT INTO subscriptions (paddle_subscription_id, student_id,\n"
                "                           customer_id, price_id, status,\n"
                "                           scheduled_change,\n"
                "                           current_period_ends_at, canceled_at)\n"
                "VALUES (%s, %d, %s, %s, %s, %s, %s,\n"
                "        CASE WHEN %s = 'canceled' THEN now() ELSE NULL END)\n"
                "ON CONFLICT (paddle_subscription_id) DO UPDATE\n"
                "  SET student_id = EXCLUDED.student_id,\n"
                "      customer_id = EXCLUDED.customer_id,\n"
                "      price_id = EXCLUDED.price_id,\n"
                "      status = EXCLUDED.status,\n"
                "      scheduled_change = EXCLUDED.scheduled_change,\n"
                "      current_period_ends_at = EXCLUDED.current_period_ends_at,\n"
                "      canceled_at = EXCLUDED.canceled_at,\n"
                "      updated_at = now();\n"
                "COMMIT;\n" % (sql_str(sub_id), sid, sql_str(customer_id),
                              sql_str(price_id), sql_str(status),
                              sql_str(scheduled) if scheduled else "NULL",
                              ends_sql, sql_str(status)),
                want_rows=False,
            )
            self._respond(200, {"ok": True, "handled": True})
            return

        # Paddle sends many event types to the same destination; ack the
        # ones we do not act on so they are not redelivered.
        self._respond(200, {"ok": True, "handled": False})

    def _handle_subscription_status(self):
        """GET /subscription/status?transaction_id=... — what the app's
        checkout success page polls (lib/enroll.ts fetchSubscriptionStatus).
        Resolution order for the status of ONE checkout transaction:
        1. A subscription row linked to this transaction through the
           payments ledger (transaction.completed carries
           subscription_id) — authoritative, including canceled later.
        2. A payments row for this transaction without a linked
           subscription yet — money landed, subscription event still in
           flight: "pending".
        3. The student's most recent subscription row (repeat customer
           with an older canceled plan and a fresh unpaid checkout).
        4. Otherwise "pending" (checkout created, nothing confirmed yet).
        Unknown transaction: 404."""
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        txn_id = (query.get("transaction_id") or [""])[0]
        if not re.match(r"^[A-Za-z0-9_\-]{1,128}$", txn_id):
            self._respond(400, {"error": "bad transaction id"})
            return
        rows = db_sql(
            "BEGIN;\n"
            "SELECT student_id FROM subscription_signups\n"
            "WHERE transaction_id = %s;\n"
            "ROLLBACK;\n" % sql_str(txn_id)
        )
        if not rows:
            self._respond(404, {"error": "not_found"})
            return
        student_id = int(rows[0][0])
        status = None
        linked = db_sql(
            "BEGIN;\n"
            "SELECT s.status FROM payments p\n"
            "JOIN subscriptions s\n"
            "  ON s.paddle_subscription_id = p.paddle_subscription_id\n"
            "WHERE p.paddle_transaction_id = %s\n"
            "ORDER BY s.id DESC LIMIT 1;\n"
            "ROLLBACK;\n" % sql_str(txn_id)
        )
        if linked:
            status = str(linked[0][0])
        else:
            paid = db_sql(
                "BEGIN;\n"
                "SELECT EXISTS (SELECT 1 FROM payments\n"
                "WHERE paddle_transaction_id = %s);\n"
                "ROLLBACK;\n" % sql_str(txn_id)
            )
            if paid and paid[0][0] == "t":
                status = "pending"
            else:
                latest = db_sql(
                    "BEGIN;\n"
                    "SELECT status FROM subscriptions\n"
                    "WHERE student_id = %d\n"
                    "ORDER BY created_at DESC, id DESC LIMIT 1;\n"
                    "ROLLBACK;\n" % student_id
                )
                status = str(latest[0][0]) if latest else "pending"
        self._respond(200, {"transaction_id": txn_id, "status": status})

    def _handle_webhook(self):
        ok, raw = self._read_body()
        if not ok:
            self._respond(413, {"error": "body too large"})
            return
        secret = os.environ.get("KEEL_STRIPE_WEBHOOK_SECRET", "")
        if not secret:
            sys.stderr.write("enroll: webhook refused: KEEL_STRIPE_WEBHOOK_SECRET not set\n")
            self._respond(503, {"error": "server misconfigured"})
            return
        try:
            tolerance = int(os.environ.get("KEEL_STRIPE_TOLERANCE_S", "300"))
        except ValueError:
            tolerance = 300
        header = self.headers.get("Stripe-Signature", "")
        if not verify_stripe_signature(raw, header, secret, tolerance):
            self._respond(400, {"error": "invalid signature"})
            return

        try:
            event = json.loads(raw)
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return
        if event.get("type") != "checkout.session.completed":
            # Stripe sends many event types to the same endpoint; ack the
            # ones we do not act on so they are not redelivered.
            self._respond(200, {"ok": True, "handled": False})
            return

        session = (event.get("data") or {}).get("object") or {}
        stripe_session_id = str(session.get("id") or "")
        if not stripe_session_id:
            self._respond(400, {"error": "event carries no session id"})
            return

        # Idempotent completion: the guarded UPDATE moves pending ->
        # completed at most once; enrollments UNIQUE (student_id, unit_id)
        # with ON CONFLICT DO NOTHING makes replayed completions no-ops; the
        # event is appended only when the enrollment row was newly inserted.
        sql = """BEGIN;
WITH upd AS (
    UPDATE checkout_sessions
    SET status = 'completed', completed_at = now()
    WHERE stripe_session_id = %s AND status = 'pending'
    RETURNING id
), ins AS (
    INSERT INTO enrollments (student_id, unit_id, checkout_session_id)
    SELECT student_id, unit_id, id FROM checkout_sessions
    WHERE stripe_session_id = %s
    ON CONFLICT (student_id, unit_id) DO NOTHING
    RETURNING id, student_id, unit_id
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'enrollment.activated',
           jsonb_build_object('student_id', student_id,
                              'unit_id', unit_id::text,
                              'stripe_session_id', %s::text)
    FROM ins RETURNING id
), bud AS (
    INSERT INTO budgets (student_id, tokens_cap, tokens_used)
    SELECT student_id, %d, 0 FROM ins
    ON CONFLICT (student_id) DO NOTHING
    RETURNING student_id
)
SELECT EXISTS (SELECT 1 FROM ins), EXISTS (SELECT 1 FROM upd);
COMMIT;
""" % (sql_str(stripe_session_id), sql_str(stripe_session_id),
       sql_str(stripe_session_id), default_budget_tokens())
        try:
            rows = db_sql(sql)
        except RuntimeError:
            self._respond(500, {"error": "database error"})
            return
        # psql prints booleans as t/f strings; compare explicitly so an "f"
        # (truthy as a Python string) is never mistaken for success.
        newly_enrolled, cs_updated = rows[0]

        if cs_updated != "t" and newly_enrolled != "t":
            # Not a session this service created (or already completed by an
            # earlier delivery AND already enrolled). Distinguish the first
            # case with a diagnostic event, mirroring intake.unknown_pusher;
            # already-completed replays are silent no-ops.
            rows2 = db_sql(
                "BEGIN;\n"
                "SELECT status FROM checkout_sessions\n"
                "WHERE stripe_session_id = %s;\n"
                "ROLLBACK;\n" % sql_str(stripe_session_id)
            )
            if not rows2:
                db_sql(
                    "BEGIN;\n"
                    "INSERT INTO events (type, payload) VALUES ("
                    "'enroll.unknown_checkout_session',"
                    "jsonb_build_object('stripe_session_id', %s::text));\n"
                    "COMMIT;\n" % sql_str(stripe_session_id),
                    want_rows=False,
                )
        self._respond(200, {
            "ok": True,
            "handled": True,
            "newly_enrolled": newly_enrolled == "t",
        })


def main():
    port = int(os.environ.get("KEEL_ENROLL_PORT", "8791"))
    if not app_token():
        sys.stderr.write("refusing to start: KEEL_ENROLL_SECRET not set\n")
        sys.exit(1)
    if not os.environ.get("KEEL_STRIPE_WEBHOOK_SECRET"):
        sys.stderr.write(
            "enroll: warning: KEEL_STRIPE_WEBHOOK_SECRET not set; "
            "webhook requests will be refused until it is\n"
        )
    if not os.environ.get("KEEL_PADDLE_WEBHOOK_SECRET"):
        sys.stderr.write(
            "enroll: warning: KEEL_PADDLE_WEBHOOK_SECRET not set; "
            "paddle webhook requests will be refused until it is\n"
        )
    # Fail fast on a bad KEEL_DB_CMD.
    db_sql("BEGIN;\nSELECT 1;\nROLLBACK;\n", want_rows=False)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write("enroll listening on 127.0.0.1:%d\n" % port)
    server.serve_forever()


if __name__ == "__main__":
    main()
