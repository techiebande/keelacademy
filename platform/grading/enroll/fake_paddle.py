#!/usr/bin/env python3
"""enroll/fake_paddle.py — deterministic offline fake of the Paddle Billing
surface the enroll service's subscription code calls (S2.6, house
offline-determinism convention, like enroll/fake_stripe.py).

Mirrors exactly these real calls, same wire shapes:

1. POST /customers          (real: POST api.paddle.com/customers; {id: cus_..})
2. GET  /prices/<price-id>  (real: GET /prices/{id}; unit_price.amount is a
                             STRING in lowest units, billing_cycle.interval)
3. POST /transactions       (real: POST /transactions with items/price_id,
                             customer_id, checkout.url, custom_data;
                             {id: txn_..., checkout: {url}})
4. GET  /pay/<txn-id>       (real: the hosted checkout page checkout.url
                             points at)
5. POST /pay/<txn-id>       (real: the customer completing payment; the fake
                             then delivers transaction.completed AND
                             subscription.created webhooks and redirects to
                             checkout.url — what real Paddle does)

Webhook delivery signs the body with Paddle's documented scheme — header
Paddle-Signature: ts=<unix-ts>;h1=<hex HMAC-SHA256(secret, "<ts>:<body>")> —
so the enroll server's verification path is the real one, exercised offline.

No network leaves 127.0.0.1; the bearer key is accepted but never validated
or echoed; state lives in process memory, enough because every proof run
starts fresh.

Env:
    KEEL_FAKE_PADDLE_PORT           listen port (default 8798)
    KEEL_FAKE_PADDLE_WEBHOOK_URL    where subscription events are POSTed
    KEEL_FAKE_PADDLE_WEBHOOK_SECRET signing secret for those events
    KEEL_FAKE_PADDLE_PRICE_ID       price the fake sells
                                    (default pri_fake_allaccess_monthly)
    KEEL_FAKE_PADDLE_AMOUNT_CENTS   price amount (default 4900)
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CUSTOMERS = {}   # customer_id -> email, process-lifetime
TXNS = {}        # transaction_id -> dict, process-lifetime
COUNTER = [0]    # deterministic ids: cus_fake_000001 / txn_fake_000001


def price_id():
    return os.environ.get("KEEL_FAKE_PADDLE_PRICE_ID",
                          "pri_fake_allaccess_monthly")


def amount_cents():
    return int(os.environ.get("KEEL_FAKE_PADDLE_AMOUNT_CENTS", "4900"))


def sign(body: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    mac = hmac.new(secret.encode(), ("%s:" % ts).encode() + body,
                   hashlib.sha256).hexdigest()
    return "ts=%s;h1=%s" % (ts, mac)


def deliver_webhook(event_type, data):
    event = {
        "event_id": "evt_fake_%d" % COUNTER[0],
        "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_type": event_type,
        "data": data,
    }
    body = json.dumps(event).encode()
    url = os.environ.get("KEEL_FAKE_PADDLE_WEBHOOK_URL", "")
    secret = os.environ.get("KEEL_FAKE_PADDLE_WEBHOOK_SECRET", "")
    if not url or not secret:
        sys.stderr.write("fake-paddle: no webhook URL/secret configured; "
                         "%s not delivered\n" % event_type)
        return False
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json",
            "Paddle-Signature": sign(body, secret),
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10).read()
    return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("fake-paddle: %s %s\n" % (self.command, self.path))

    def _respond(self, code, body: bytes, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, doc):
        self._respond(code, json.dumps(doc).encode())

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def _pay_html(self, txn_id: str) -> bytes:
        return ("""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Offline test checkout</title>
<style>
 body { font-family: ui-sans-serif, system-ui, sans-serif; background: #fafafa;
        color: #18181b; display: grid; place-items: center; min-height: 100vh; margin: 0; }
 main { background: #fff; border: 1px solid #e4e4e7; border-radius: 10px;
        padding: 2rem 2.5rem; text-align: center; }
 button { background: #18181b; color: #fff; border: 0; border-radius: 8px;
          padding: .6rem 1.4rem; font-size: 1rem; cursor: pointer; }
</style></head>
<body><main>
 <h1>All-access subscription</h1>
 <p>$%d.%02d / month &mdash; offline test checkout</p>
 <form method="post" action="/pay/%s"><button>Subscribe</button></form>
</main></body></html>""" % (
            amount_cents() // 100, amount_cents() % 100, txn_id)).encode()

    def do_GET(self):
        if self.path == "/__count":
            self._json(200, {"customers": len(CUSTOMERS),
                             "transactions": len(TXNS)})
            return
        if self.path.startswith("/prices/"):
            pid = self.path[len("/prices/"):]
            if pid != price_id():
                self._json(404, {"error": {"code": "not_found"}})
                return
            self._json(200, {"data": {
                "id": price_id(),
                "status": "active",
                "unit_price": {"amount": str(amount_cents()),
                               "currency_code": "USD"},
                "billing_cycle": {"interval": "month", "frequency": 1},
                "tax_category": "saas",
            }})
            return
        if self.path.startswith("/transactions/"):
            txn_id = self.path[len("/transactions/"):]
            if txn_id not in TXNS:
                self._json(404, {"error": {"code": "not_found"}})
                return
            t = TXNS[txn_id]
            self._json(200, {"data": {
                "id": txn_id,
                "status": t["status"],
                "customer_id": t["customer_id"],
                "custom_data": t["custom_data"],
                "checkout": {"url": "http://127.0.0.1:%s/pay/%s" % (
                    os.environ.get("KEEL_FAKE_PADDLE_PORT", "8798"), txn_id)},
            }})
            return
        if self.path.startswith("/pay/"):
            txn_id = self.path[len("/pay/"):]
            if txn_id not in TXNS:
                self._json(404, {"error": "unknown transaction"})
                return
            self._respond(200, self._pay_html(txn_id),
                          content_type="text/html")
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        n = COUNTER[0] + 1
        if self.path == "/customers":
            doc = self._read_json()
            cid = "cus_fake_%06d" % n
            COUNTER[0] = n
            CUSTOMERS[cid] = str(doc.get("email") or "")
            self._json(201, {"data": {"id": cid,
                                      "email": doc.get("email") or ""}})
            return

        if self.path == "/transactions":
            doc = self._read_json()
            item = (doc.get("items") or [{}])[0]
            pid = str(item.get("price_id") or "")
            if pid != price_id():
                self._json(422, {"error": {"code": "price_not_found"}})
                return
            txn_id = "txn_fake_%06d" % n
            COUNTER[0] = n
            TXNS[txn_id] = {
                "status": "ready",
                "price_id": pid,
                "customer_id": str(doc.get("customer_id") or ""),
                "custom_data": doc.get("custom_data") or {},
                "success_url": str((doc.get("checkout") or {}).get("url")
                                   or "/"),
            }
            self._json(201, {"data": {
                "id": txn_id,
                "status": "ready",
                "customer_id": TXNS[txn_id]["customer_id"],
                "custom_data": TXNS[txn_id]["custom_data"],
                "checkout": {"url": "http://127.0.0.1:%s/pay/%s" % (
                    os.environ.get("KEEL_FAKE_PADDLE_PORT", "8798"), txn_id)},
            }})
            return

        if self.path.startswith("/pay/"):
            self._complete_payment(self.path[len("/pay/"):])
            return

        self._json(404, {"error": "not found"})

    def _complete_payment(self, txn_id: str):
        if txn_id not in TXNS:
            self._json(404, {"error": "unknown transaction"})
            return
        t = TXNS[txn_id]
        t["status"] = "completed"
        sub_id = "sub_fake_%s" % txn_id[len("txn_fake_"):]
        ends = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                             time.gmtime(time.time() + 31 * 24 * 3600))
        deliver_webhook("transaction.completed", {
            "id": txn_id,
            "status": "completed",
            "customer_id": t["customer_id"],
            "subscription_id": sub_id,
            "currency_code": "USD",
            "details": {"totals": {"total": str(amount_cents())}},
            "custom_data": t["custom_data"],
        })
        deliver_webhook("subscription.created", {
            "id": sub_id,
            "status": "active",
            "customer_id": t["customer_id"],
            "items": [{"price": {"id": t["price_id"]}}],
            "current_billing_period": {"ends_at": ends},
            "scheduled_change": None,
            "custom_data": t["custom_data"],
        })
        success = t["success_url"].replace("{TRANSACTION_ID}", txn_id)
        self.send_response(302)
        self.send_header("Location", success)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    port = int(os.environ.get("KEEL_FAKE_PADDLE_PORT", "8798"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write("fake-paddle listening on 127.0.0.1:%d\n" % port)
    server.serve_forever()


if __name__ == "__main__":
    main()
