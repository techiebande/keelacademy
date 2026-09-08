#!/usr/bin/env python3
"""community/fake_email.py — deterministic offline fake Email server (S4.3).

Captures outgoing email dispatches (SMTP / HTTP API) for verification in tests.
Exposes:
- POST /api/v1/send (or HTTP webhook / SMTP API delivery)
- GET /__emails (list of received emails)
- GET /__count (count of received emails)
- POST /__reset (clear recorded emails)

Stdlib only.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_lock = threading.Lock()
_emails: list[dict[str, Any]] = []
_msg_counter = 0


def bump_email_id() -> str:
    global _msg_counter
    with _lock:
        _msg_counter += 1
        return f"email_{_msg_counter:06d}"


def add_email(rec: dict[str, Any]) -> None:
    with _lock:
        _emails.append(rec)


def get_emails() -> list[dict[str, Any]]:
    with _lock:
        return list(_emails)


def reset_emails() -> None:
    global _emails, _msg_counter
    with _lock:
        _emails = []
        _msg_counter = 0


class FakeEmailHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, code: int, body: dict[str, Any] | str) -> None:
        if isinstance(body, dict):
            raw = json.dumps(body).encode("utf-8")
            c_type = "application/json"
        else:
            raw = body.encode("utf-8")
            c_type = "text/plain"

        self.send_response(code)
        self.send_header("Content-Type", c_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("fake-email: %s %s\n" % (self.command, self.path))

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._respond(200, {"ok": True})
        elif self.path == "/__count":
            self._respond(200, {"count": len(get_emails())})
        elif self.path == "/__emails" or self.path == "/__records":
            self._respond(200, {"emails": get_emails(), "records": get_emails()})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length) if length else b""

        if self.path == "/__reset":
            reset_emails()
            self._respond(200, {"ok": True})
            return

        try:
            req_data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            req_data = {"raw": raw_body.decode("utf-8", errors="replace")}

        msg_id = bump_email_id()
        record_entry = {
            "path": self.path,
            "headers": dict(self.headers),
            "payload": req_data,
            "email_id": msg_id,
            "received_at": time.time(),
        }
        add_email(record_entry)

        self._respond(200, {
            "ok": True,
            "id": msg_id,
            "status": "delivered",
            "to": req_data.get("to") or req_data.get("email_to"),
            "subject": req_data.get("subject", ""),
        })


def main() -> None:
    port = int(os.environ.get("KEEL_FAKE_EMAIL_PORT", "8799"))
    server = ThreadingHTTPServer(("127.0.0.1", port), FakeEmailHandler)
    sys.stderr.write(f"fake email server listening on 127.0.0.1:{port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
