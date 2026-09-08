#!/usr/bin/env python3
"""smoke-intake-checks.py — the five S1.2 proof checks (stdlib only).

Env (set by smoke-intake.sh):
  INTAKE_PORT, INTAKE_SECRET, INTAKE_DOCKER, INTAKE_CONTAINER,
  INTAKE_DB_USER, INTAKE_DB_NAME
Prints PASS/FAIL per check; exits non-zero on any failure.
"""

import hashlib
import hmac
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

PORT = int(os.environ["INTAKE_PORT"])
SECRET = os.environ["INTAKE_SECRET"].encode()
DOCKER = os.environ["INTAKE_DOCKER"]
CONTAINER = os.environ["INTAKE_CONTAINER"]
DB_USER = os.environ["INTAKE_DB_USER"]
DB_NAME = os.environ["INTAKE_DB_NAME"]

SHA = "a" * 40
REPO_URL = "https://github.com/keel-academy/keel-3.2.1-alice.git"

failures = []


def post(body: bytes, signature: str):
    req = urllib.request.Request(
        "http://127.0.0.1:%d/webhook/github" % PORT,
        data=body,
        headers={"X-Hub-Signature-256": signature,
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def payload(email="alice@keel.test", sha=SHA, repo=REPO_URL,
            full_name="keel-academy/keel-3.2.1-alice"):
    return json.dumps({
        "repository": {"full_name": full_name, "clone_url": repo},
        "pusher": {"name": email.split("@")[0], "email": email},
        "head_commit": {"id": sha},
    }).encode()


def psql(sql):
    out = subprocess.run(
        [DOCKER, "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME,
         "-tA", "-F", "\t", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return out.stdout.decode().strip()


def check(letter, desc, ok, detail=""):
    print("%s %s: %s%s" % ("PASS" if ok else "FAIL", letter, desc,
                           (" — " + detail) if detail else ""))
    if not ok:
        failures.append(letter)


# (a) valid signed push from the seeded student
body = payload()
code, resp = post(body, sign(body))
rows = psql(
    "SELECT count(*), min(status), min(unit_id), min(commit_sha),"
    " min(pusher_email) FROM submissions;")
n, status, unit, sha, email = rows.split("\t")
ev = psql("SELECT payload->>'submission_id' FROM events"
          " WHERE type = 'submission.created';")
ok = (code == 200 and n == "1" and status == "queued" and unit == "3.2.1"
      and sha == SHA and email == "alice@keel.test"
      and ev == psql("SELECT id FROM submissions;"))
check("a", "signed push -> 1 queued submission + 1 submission.created", ok,
      "http=%s submissions[count=%s status=%s unit=%s sha=%s pusher=%s] event.submission_id=%s"
      % (code, n, status, unit, sha, email, ev))

# (b) exact redelivery of the same payload
code, resp = post(body, sign(body))
sub_n = psql("SELECT count(*) FROM submissions;")
ev_n = psql("SELECT count(*) FROM events WHERE type = 'submission.created';")
check("b", "redelivery -> still 1 submission, 1 event", 
      code == 200 and sub_n == "1" and ev_n == "1",
      "http=%s submissions=%s submission.created=%s" % (code, sub_n, ev_n))

# (c) valid signature over a tampered body
tampered = body + b" "
code, resp = post(tampered, sign(body))
sub_n = psql("SELECT count(*) FROM submissions;")
ev_n = psql("SELECT count(*) FROM events;")
check("c", "tampered body -> 4xx, zero DB changes",
      400 <= code < 500 and sub_n == "1" and ev_n == "1",
      "http=%s body=%r submissions=%s events=%s" % (code, resp, sub_n, ev_n))

# (d) push from an unregistered email
body_d = payload(email="stranger@nowhere.test")
code, resp = post(body_d, sign(body_d))
sub_n = psql("SELECT count(*) FROM submissions;")
unk = psql("SELECT count(*), min(payload->>'email'), min(payload->>'repo'),"
           " min(payload->>'commit_sha') FROM events"
           " WHERE type = 'intake.unknown_pusher';")
u_n, u_email, u_repo, u_sha = unk.split("\t")
check("d", "unknown pusher -> 200, no submission, 1 unknown_pusher event",
      code == 200 and sub_n == "1" and u_n == "1"
      and u_email == "stranger@nowhere.test" and u_sha == SHA,
      "http=%s submissions=%s unknown_pusher[count=%s email=%s sha=%s]"
      % (code, sub_n, u_n, u_email, u_sha))

# (e) second seeded student, same unit + same commit sha
psql("INSERT INTO students (email, display_name)"
     " VALUES ('bob@keel.test', 'Bob');")
body_e = payload(email="bob@keel.test",
                 repo="https://github.com/keel-academy/keel-3.2.1-bob.git",
                 full_name="keel-academy/keel-3.2.1-bob")
code, resp = post(body_e, sign(body_e))
sub_n = psql("SELECT count(*) FROM submissions;")
ev_n = psql("SELECT count(*) FROM events WHERE type = 'submission.created';")
check("e", "second student, same unit+sha -> accepted (unique key is triple)",
      code == 200 and sub_n == "2" and ev_n == "2",
      "http=%s submissions=%s submission.created=%s" % (code, sub_n, ev_n))

if failures:
    print("FAILED: %s" % ", ".join(failures))
    sys.exit(1)
