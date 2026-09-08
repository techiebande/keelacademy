#!/usr/bin/env python3
"""enroll/fake_stripe.py — deterministic offline fake of the Stripe surface
S2.5 uses (house offline-determinism convention, like proxy/fake_upstream.py).

Mirrors exactly these real calls, same wire shapes:

1. POST /v1/checkout/sessions        (real: api.stripe.com checkout session
                                      create; form-encoded body, bearer key,
                                      JSON {id, url} response)
2. GET  /pay/<session-id>            (real: the hosted checkout.stripe.com
                                      payment page the session url points at)
3. POST /pay/<session-id>            (real: the customer completing payment;
                                      the fake then delivers the
                                      checkout.session.completed webhook and
                                      redirects to success_url, which is what
                                      real Stripe does on payment success)
4. GET  /__count                     (fake-only: sessions created, for proofs)

Webhook delivery signs the body with Stripe's documented scheme — header
Stripe-Signature: t=<unix-ts>,v1=<hex HMAC-SHA256(secret, "<t>." + body)> —
so the enroll server's verification path is the real one, exercised offline.

No network leaves 127.0.0.1; the bearer key is accepted but never validated
or echoed (it is a placeholder in credential-free runs); sessions live in
process memory, which is enough because every proof run starts fresh.

Env:
    KEEL_FAKE_STRIPE_PORT          listen port (default 8799)
    KEEL_FAKE_STRIPE_WEBHOOK_URL   where completed-session events are POSTed
    KEEL_FAKE_STRIPE_WEBHOOK_SECRET signing secret for those events
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SESSIONS = {}  # id -> dict(form fields), process-lifetime
COUNTER = [0]  # deterministic ids: cs_fake_000001, cs_fake_000002, ...


def sign(body: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    mac = hmac.new(secret.encode(), ("%s." % ts).encode() + body,
                   hashlib.sha256).hexdigest()
    return "t=%s,v1=%s" % (ts, mac)


def money(cents: int) -> str:
    return "$%d.%02d" % (cents // 100, cents % 100)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("fake-stripe: %s %s\n" % (self.command, self.path))

    def _respond(self, code, body: bytes, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _pay_html(self, session_id: str) -> bytes:
        s = SESSIONS[session_id]
        name = s.get("line_items[0][price_data][product_data][name]", "Keel Academy unit")
        amount = int(s.get("line_items[0][price_data][unit_amount]", "0"))
        cancel = s.get("cancel_url", "/")
        html = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Offline test checkout</title>
<style>
 body { font-family: ui-sans-serif, system-ui, sans-serif; background: #fafafa;
        color: #18181b; display: grid; place-items: center; min-height: 100vh; margin: 0; }
 main { background: #fff; border: 1px solid #e4e4e7; border-radius: 10px;
        padding: 2.2rem 2.4rem; width: min(92vw, 26rem); }
 p { color: #52525b; font-size: 0.9rem; line-height: 1.6; margin: 0.5rem 0 1.4rem; }
 h1 { font-size: 1.05rem; margin: 0; }
 .amount { font-size: 2rem; font-weight: 650; margin: 1.2rem 0 0.2rem; }
 .sid { font-family: ui-monospace, monospace; font-size: 0.72rem; color: #a1a1aa; }
 form { margin-top: 1.6rem; display: flex; gap: 0.8rem; }
 button { flex: 1; background: #635bff; color: #fff; border: 0; border-radius: 6px;
          padding: 0.7rem 1rem; font-size: 0.9rem; font-weight: 600; cursor: pointer; }
 button:hover { opacity: 0.9; }
 a.cancel { color: #52525b; font-size: 0.85rem; text-decoration: none;
            align-self: center; }
</style></head>
<body><main>
 <h1>Keel Academy test checkout</h1>
 <div class="amount">%(amount)s</div>
 <div class="sid">%(sid)s</div>
 <p>This page stands in for Stripe's hosted checkout so the enrollment flow
    can be proven with no Stripe account and no network. Completing it fires
    the same signed webhook the real service sends.</p>
 <form method="post" action="/pay/%(sid)s">
   <button type="submit">Pay %(amount)s</button>
   <a class="cancel" href="%(cancel)s">Cancel</a>
 </form>
</main></body></html>
""" % {"amount": money(amount), "sid": session_id, "cancel": cancel}
        return html.encode()

    def do_GET(self):
        if self.path == "/__count":
            self._respond(200, json.dumps({"sessions_created": COUNTER[0]}).encode())
            return
        if self.path.startswith("/pay/"):
            sid = self.path[len("/pay/"):]
            if sid not in SESSIONS:
                self._respond(404, b'{"error": "unknown session"}')
                return
            self._respond(200, self._pay_html(sid), content_type="text/html; charset=utf-8")
            return
        self._respond(404, b'{"error": "not found"}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        if self.path == "/v1/checkout/sessions":
            fields = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
            flat = {k: v[0] for k, v in fields.items()}
            for required in ("mode", "success_url", "cancel_url",
                             "metadata[student_id]", "metadata[unit_id]"):
                if not flat.get(required):
                    self._respond(400, json.dumps({
                        "error": {"message": "missing %s" % required}}).encode())
                    return
            COUNTER[0] += 1
            sid = "cs_fake_%06d" % COUNTER[0]
            SESSIONS[sid] = flat
            # The real API returns a long document; the enroll server only
            # reads id and url, so the fake carries those plus the fields a
            # real completed-session webhook object would carry.
            self._respond(200, json.dumps({
                "id": sid,
                "object": "checkout.session",
                "mode": flat.get("mode"),
                "url": "http://127.0.0.1:%s/pay/%s" % (
                    os.environ.get("KEEL_FAKE_STRIPE_PORT", "8799"), sid),
                "payment_status": "unpaid",
                "amount_total": int(flat.get(
                    "line_items[0][price_data][unit_amount]", "0")),
                "metadata": {
                    "student_id": flat.get("metadata[student_id]"),
                    "unit_id": flat.get("metadata[unit_id]"),
                },
            }).encode())
            return

        if self.path.startswith("/pay/"):
            sid = self.path[len("/pay/"):]
            if sid not in SESSIONS:
                self._respond(404, b'{"error": "unknown session"}')
                return
            s = SESSIONS[sid]
            event = {
                "id": "evt_fake_%s" % sid[len("cs_fake_"):],
                "object": "event",
                "type": "checkout.session.completed",
                "data": {"object": {
                    "id": sid,
                    "object": "checkout.session",
                    "payment_status": "paid",
                    "client_reference_id": s.get("client_reference_id"),
                    "metadata": {
                        "student_id": s.get("metadata[student_id]"),
                        "unit_id": s.get("metadata[unit_id]"),
                    },
                }},
            }
            body = json.dumps(event).encode()
            url = os.environ.get("KEEL_FAKE_STRIPE_WEBHOOK_URL", "")
            secret = os.environ.get("KEEL_FAKE_STRIPE_WEBHOOK_SECRET", "")
            if url and secret:
                req = urllib.request.Request(
                    url, data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Stripe-Signature": sign(body, secret),
                    },
                    method="POST",
                )
                try:
                    urllib.request.urlopen(req, timeout=10).read()
                except OSError as exc:
                    sys.stderr.write("fake-stripe: webhook delivery failed: %s\n"
                                     % type(exc).__name__)
                    self._respond(502, b'{"error": "webhook delivery failed"}')
                    return
            else:
                sys.stderr.write("fake-stripe: no webhook URL/secret configured; "
                                 "completing without delivery\n")
            success = s.get("success_url", "/")
            # Real Stripe substitutes {CHECKOUT_SESSION_ID} in the success
            # URL at redirect time; so does the fake.
            success = success.replace("{CHECKOUT_SESSION_ID}", sid)
            self.send_response(302)
            self.send_header("Location", success)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self._respond(404, b'{"error": "not found"}')


def main():
    port = int(os.environ.get("KEEL_FAKE_STRIPE_PORT", "8799"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write("fake-stripe listening on 127.0.0.1:%d\n" % port)
    server.serve_forever()


if __name__ == "__main__":
    main()
