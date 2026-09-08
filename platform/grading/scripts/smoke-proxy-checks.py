#!/usr/bin/env python3
"""smoke-proxy-checks.py — the S1.5 proof checks (a)-(e) (stdlib only).

Env (set by smoke-proxy.sh):
  PROXY_PORT, FAKE_PORT, PROXY_DOCKER, PROXY_CONTAINER,
  PROXY_DB_USER, PROXY_DB_NAME
Prints PASS/FAIL per check; exits non-zero on any failure.
"""

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request

PORT = int(os.environ["PROXY_PORT"])
FAKE_PORT = int(os.environ["FAKE_PORT"])
DOCKER = os.environ["PROXY_DOCKER"]
CONTAINER = os.environ["PROXY_CONTAINER"]
DB_USER = os.environ["PROXY_DB_USER"]
DB_NAME = os.environ["PROXY_DB_NAME"]

failures = []


def psql(sql):
    out = subprocess.run(
        [DOCKER, "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
         "-tA", "-F", "\t", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return out.stdout.decode().strip()


def student_id(email):
    return psql("SELECT id FROM students WHERE email = '%s';" % email)


def used(student):
    return int(psql("SELECT tokens_used FROM budgets WHERE student_id = %s;"
                    % student_id(student)))


def fake_count():
    with urllib.request.urlopen(
            "http://127.0.0.1:%d/__count" % FAKE_PORT, timeout=10) as r:
        return int(r.read().decode().strip())


def chat(student, model="gpt-4o-mini", content="hello"):
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": content}]}
                      ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % PORT,
        data=body,
        headers={"Content-Type": "application/json",
                 "X-Keel-Student-Id": str(student)},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def check(letter, desc, ok, detail=""):
    print("%s %s: %s%s" % ("PASS" if ok else "FAIL", letter, desc,
                           (" — " + detail) if detail else ""))
    if not ok:
        failures.append(letter)


alice = student_id("alice@keel.test")
bob = student_id("bob@keel.test")
carol = student_id("carol@keel.test")

# ---- (a) alice: 200, OpenAI-shaped body, tokens_used == fake usage ----
code, body = chat(alice)
try:
    j = json.loads(body)
    usage_total = (j["usage"]["prompt_tokens"]
                   + j["usage"]["completion_tokens"])
    shaped = (isinstance(j.get("choices"), list) and len(j["choices"]) > 0
              and j["choices"][0]["message"]["role"] == "assistant"
              and "usage" in j)
except (ValueError, KeyError, TypeError):
    j, usage_total, shaped = {}, -1, False
db_used = used("alice@keel.test")
check("a", "alice -> 200, OpenAI-shaped body, tokens_used == fake usage",
      code == 200 and shaped and db_used == usage_total,
      "http=%s usage_total=%s budgets.tokens_used=%s"
      % (code, usage_total, db_used))

# ---- (b) bob: first call accepted, second cut off + flagged ----
code1, _ = chat(bob)
used1 = used("bob@keel.test")
before = fake_count()  # window brackets ONLY the second (cut-off) call
code2, body2 = chat(bob)
after = fake_count()
try:
    err_code = json.loads(body2)["error"]["code"]
except (ValueError, KeyError, TypeError):
    err_code = None
ev_row = psql(
    "SELECT count(*), min(payload->>'student_id'), min(payload->>'model'),"
    " min(payload->>'tokens_used'), min(payload->>'tokens_cap')"
    " FROM events WHERE type = 'proxy.budget_exceeded'"
    " AND payload->>'student_id' = '%s';" % bob)
ev_n, ev_sid, ev_model, ev_used, ev_cap = ev_row.split("\t")
check("b", "bob: 1st accepted, 2nd 429 budget_exceeded, no forward, 1 event",
      code1 == 200 and used1 == 300 and code2 == 429
      and err_code == "budget_exceeded" and after == before
      and ev_n == "1" and ev_model == "gpt-4o-mini" and ev_used == "300"
      and ev_cap == "300" and used("bob@keel.test") == 300,
      "http=%s/%s err=%s /__count %d->%d events=%s used=%s"
      % (code1, code2, err_code, before, after, ev_n,
         used("bob@keel.test")))

# ---- (c) unknown student -> 404, no event, no upstream call ----
ev_total = psql("SELECT count(*) FROM events;")
cnt = fake_count()
code, body = chat(999999)
check("c", "unknown student -> 404, no event, no upstream call",
      code == 404 and psql("SELECT count(*) FROM events;") == ev_total
      and fake_count() == cnt,
      "http=%s events %s->%s /__count %d->%d"
      % (code, ev_total, psql("SELECT count(*) FROM events;"), cnt,
         fake_count()))

# ---- (d) disallowed model -> 400, no upstream call ----
cnt = fake_count()
ev_total = psql("SELECT count(*) FROM events;")
code, body = chat(alice, model="gpt-4-turbo")
check("d", "disallowed model -> 400, no upstream call",
      code == 400 and fake_count() == cnt
      and psql("SELECT count(*) FROM events;") == ev_total,
      "http=%s /__count %d->%d" % (code, cnt, fake_count()))

# ---- (e) concurrency burst: 5 simultaneous calls for carol ----
results = []
results_lock = threading.Lock()


def carol_call():
    c, b = chat(carol)
    with results_lock:
        results.append((c, b))


threads = [threading.Thread(target=carol_call) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
codes = sorted(c for c, _ in results)
n200 = codes.count(200)
n429 = codes.count(429)
final_used = used("carol@keel.test")
carol_ev = psql(
    "SELECT count(*) FROM events WHERE type = 'proxy.budget_exceeded'"
    " AND payload->>'student_id' = '%s';" % carol)
forwarded = fake_count() - cnt  # since check (d) captured the count
check("e", "burst: >=1 200 and >=1 429, used <= cap+300, events == 429s,"
           " /__count == 200s",
      n200 >= 1 and n429 >= 1 and final_used <= 400 + 300
      and n429 == int(carol_ev) and forwarded == n200,
      "codes=%s used=%d (cap 400, bound 700) budget_exceeded=%s"
      " /__count delta=%d" % (codes, final_used, carol_ev, forwarded))

if failures:
    print("FAILED: %s" % ", ".join(failures))
    sys.exit(1)
