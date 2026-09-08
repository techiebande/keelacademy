#!/usr/bin/env python3
"""proxy/fake_upstream.py — deterministic offline fake OpenAI (S1.5).

Project convention: offline deterministic fakes for tests, so every proof is
deterministic and zero-cost. Echoes a canned assistant message; usage comes
from env KEEL_FAKE_PROMPT_TOKENS (default 50) and
KEEL_FAKE_COMPLETION_TOKENS (default 250). Counts requests and exposes
GET /__count so proofs can show exactly how many calls were forwarded.
Stdlib only.
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROMPT_TOKENS = int(os.environ.get("KEEL_FAKE_PROMPT_TOKENS", "50"))
COMPLETION_TOKENS = int(os.environ.get("KEEL_FAKE_COMPLETION_TOKENS", "250"))
# S1.8: the wiring harness points the judge at this fake, so the reply content
# must be the canned judge verdict JSON the rubric expects (KEEL_FAKE_CONTENT),
# and KEEL_FAKE_DELAY_S holds a call in flight so kill-mid-judge is testable.
CONTENT = os.environ.get("KEEL_FAKE_CONTENT", "keel fake upstream reply #%d")
DELAY_S = float(os.environ.get("KEEL_FAKE_DELAY_S", "0"))

_count_lock = threading.Lock()
_count = 0


def bump():
    global _count
    with _count_lock:
        _count += 1
        return _count


def count():
    with _count_lock:
        return _count


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, code, body):
        raw = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        sys.stderr.write("fake-upstream: %s %s\n" % (self.command, self.path))

    def do_GET(self):
        if self.path == "/__count":
            self._respond(200, str(count()))
        else:
            self._respond(404, "{}")

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self._respond(404, "{}")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        n = bump()
        if DELAY_S > 0:
            time.sleep(DELAY_S)
        self._respond(200, json.dumps({
            "id": "chatcmpl-fake-%d" % n,
            "object": "chat.completion",
            "created": 0,
            "model": "fake-openai",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant",
                            "content": CONTENT % n if "%d" in CONTENT else CONTENT},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": PROMPT_TOKENS,
                "completion_tokens": COMPLETION_TOKENS,
                "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
            },
        }))


def main():
    port = int(os.environ.get("KEEL_FAKE_PORT", "8790"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write("fake upstream listening on 127.0.0.1:%d "
                     "(prompt=%d completion=%d)\n"
                     % (port, PROMPT_TOKENS, COMPLETION_TOKENS))
    server.serve_forever()


if __name__ == "__main__":
    main()
