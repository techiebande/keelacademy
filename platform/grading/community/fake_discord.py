#!/usr/bin/env python3
"""community/fake_discord.py — deterministic offline fake Discord API / Webhook upstream (S4.2).

Echoes and records Discord channel creations, role assignments, and webhook/channel message relays.
Exposes:
- POST /api/v10/channels (or webhook URLs /api/webhooks/...)
- POST /api/v10/channels/<id>/messages
- GET /__records (list of received deliveries)
- GET /__count (count of received deliveries)
- POST /__reset (clear recorded calls)

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
_records: list[dict[str, Any]] = []
_msg_counter = 0


def bump_message_id() -> str:
    global _msg_counter
    with _lock:
        _msg_counter += 1
        return f"disc_msg_{_msg_counter:06d}"


def add_record(rec: dict[str, Any]) -> None:
    with _lock:
        _records.append(rec)


def get_records() -> list[dict[str, Any]]:
    with _lock:
        return list(_records)


def reset_records() -> None:
    global _records, _msg_counter
    with _lock:
        _records = []
        _msg_counter = 0


class FakeDiscordHandler(BaseHTTPRequestHandler):
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
        sys.stderr.write("fake-discord: %s %s\n" % (self.command, self.path))

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._respond(200, {"ok": True})
        elif self.path == "/__count":
            self._respond(200, {"count": len(get_records())})
        elif self.path == "/__records":
            self._respond(200, {"records": get_records()})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length) if length else b""

        if self.path == "/__reset":
            reset_records()
            self._respond(200, {"ok": True})
            return

        try:
            req_data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception:
            req_data = {"raw": raw_body.decode("utf-8", errors="replace")}

        msg_id = bump_message_id()
        record_entry = {
            "path": self.path,
            "headers": dict(self.headers),
            "payload": req_data,
            "message_id": msg_id,
            "received_at": time.time(),
        }
        add_record(record_entry)

        # Handle channel provisioning
        if "/guilds/" in self.path and self.path.endswith("/channels"):
            chan_name = req_data.get("name", "pod-channel")
            chan_id = f"chan_{msg_id}"
            self._respond(201, {
                "id": chan_id,
                "name": chan_name,
                "type": 0,
                "guild_id": "guild_keel_main",
            })
            return

        # Handle message post / webhook relay
        self._respond(200, {
            "id": msg_id,
            "channel_id": req_data.get("channel_id", "chan_default"),
            "content": req_data.get("content", ""),
            "embeds": req_data.get("embeds", []),
            "author": {"id": "bot_keel", "username": "Keel Pod Bot"},
        })


def main() -> None:
    port = int(os.environ.get("KEEL_FAKE_DISCORD_PORT", "8798"))
    server = ThreadingHTTPServer(("127.0.0.1", port), FakeDiscordHandler)
    sys.stderr.write(f"fake discord listening on 127.0.0.1:{port}\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
