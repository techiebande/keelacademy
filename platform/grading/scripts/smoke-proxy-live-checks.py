#!/usr/bin/env python3
"""smoke-proxy-live-checks.py — the gated LIVE S1.5 check (f) (stdlib only).

One real gpt-4o-mini call for alice through a proxy pointed at the real
upstream; asserts 200 and that budgets.tokens_used increased. Cost < $0.01.
Env: PROXY_PORT, LIVE_DOCKER, LIVE_CONTAINER.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

PORT = int(os.environ["PROXY_PORT"])
DOCKER = os.environ["LIVE_DOCKER"]
CONTAINER = os.environ["LIVE_CONTAINER"]


def psql(sql):
    out = subprocess.run(
        [DOCKER, "exec", CONTAINER, "psql", "-U", "smoke", "-d", "grading",
         "-tA", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return out.stdout.decode().strip()


alice = psql("SELECT id FROM students WHERE email = 'alice@keel.test';")
before = int(psql("SELECT tokens_used FROM budgets WHERE student_id = %s;"
                  % alice))

body = json.dumps({
    "model": "gpt-4o-mini",
    "messages": [{"role": "user",
                  "content": "Reply with the single word: ok"}],
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:%d/v1/chat/completions" % PORT,
    data=body,
    headers={"Content-Type": "application/json",
             "X-Keel-Student-Id": alice},
    method="POST")
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        code, raw = resp.status, resp.read().decode()
except urllib.error.HTTPError as e:
    code, raw = e.code, e.read().decode()

after = int(psql("SELECT tokens_used FROM budgets WHERE student_id = %s;"
                 % alice))
try:
    usage = json.loads(raw).get("usage") or {}
    usage_str = "prompt=%s completion=%s" % (
        usage.get("prompt_tokens"), usage.get("completion_tokens"))
    shaped = "choices" in json.loads(raw)
except ValueError:
    usage_str, shaped = "unparseable", False

ok = code == 200 and after > before and shaped
print("%s f: LIVE gpt-4o-mini call -> 200, tokens_used increased — "
      "http=%s used %d->%d %s"
      % ("PASS" if ok else "FAIL", code, before, after, usage_str))
sys.exit(0 if ok else 1)
