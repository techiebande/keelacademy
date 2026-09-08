#!/usr/bin/env python3
"""intake/server.py — GitHub-style push webhook receiver (S1.2).

Stdlib only. POST /webhook/github with an X-Hub-Signature-256 header:
    sha256= + hex(HMAC-SHA256(KEEL_WEBHOOK_SECRET, raw_body))
The signature is verified against the RAW body bytes BEFORE any JSON parsing;
bad or missing signature -> 401 and no database writes.

Database access is a command (env KEEL_DB_CMD, shlex-split) that behaves like
psql: reads SQL on stdin, prints results, honors -v ON_ERROR_STOP-style
failure via non-zero exit. Each HTTP request uses exactly one such session
wrapped in BEGIN/COMMIT, so submission + event writes are one transaction.
"""

import hashlib
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Add parent dir to sys.path to import shared db module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import db_cmd, db_sql, sql_str

UNIT_RE = None  # compiled lazily; see unit_from_repo()


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
        # Keep logging minimal; never log headers (they carry the signature)
        # or bodies (they may carry student emails we haven't validated).
        sys.stderr.write("intake: %s %s\n" % (self.command, self.path))

    def do_POST(self):
        if self.path != "/webhook/github":
            self._respond(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        # --- signature check FIRST, over raw bytes, before any parsing ---
        secret = os.environ.get("KEEL_WEBHOOK_SECRET", "")
        if not secret:
            self._respond(500, {"error": "server misconfigured"})
            return
        sig = self.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            secret.encode(), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            self._respond(401, {"error": "invalid signature"})
            return

        # --- parse payload ---
        try:
            payload = json.loads(raw)
        except ValueError:
            self._respond(400, {"error": "invalid JSON"})
            return

        head = (payload.get("head_commit") or {}).get("id")
        repo = payload.get("repository") or {}
        full_name = repo.get("full_name") or ""
        clone_url = repo.get("clone_url")
        pusher = payload.get("pusher") or {}
        pusher_email = pusher.get("email")

        if not head or not full_name or not pusher_email:
            self._respond(422, {"error": "missing head_commit.id, repository.full_name, or pusher.email"})
            return

        unit_id = unit_from_repo(full_name)
        if unit_id is None:
            self._respond(422, {"error": "cannot derive unit id from repo name", "repo": full_name})
            return

        # --- resolve pusher ---
        rows = db_sql(
            "BEGIN;\n"
            "SELECT id FROM students WHERE email = '%s';\n"
            "COMMIT;\n" % pusher_email.replace("'", "''")
        )
        if not rows:
            # Unknown pusher: 200 (so GitHub doesn't retry), event only.
            db_sql(
                "BEGIN;\n"
                "INSERT INTO events (type, payload) VALUES ("
                "'intake.unknown_pusher',"
                "jsonb_build_object('email', %s, 'repo', %s::text,"
                " 'commit_sha', %s::text));\n"
                "COMMIT;\n" % (
                    sql_str(pusher_email), sql_str(full_name), sql_str(head),
                ),
                want_rows=False,
            )
            self._respond(200, {"ok": True, "known_pusher": False})
            return

        student_id = rows[0][0]

        # --- one transaction: idempotent submission + event on new insert ---
        sql = """BEGIN;
WITH ins AS (
    INSERT INTO submissions
        (student_id, unit_id, commit_sha, repo_url, pusher_email, status)
    VALUES (%s, %s, %s, %s, %s, 'queued')
    ON CONFLICT (student_id, unit_id, commit_sha) DO NOTHING
    RETURNING id
), sid AS (
    SELECT id FROM ins
    UNION ALL
    SELECT s.id FROM submissions s
    WHERE s.student_id = %s AND s.unit_id = %s AND s.commit_sha = %s
      AND NOT EXISTS (SELECT 1 FROM ins)
    LIMIT 1
), ev AS (
    INSERT INTO events (type, payload)
    SELECT 'submission.created',
           jsonb_build_object('submission_id', id, 'student_id', %s,
                              'unit_id', %s::text, 'commit_sha', %s::text,
                              'repo', %s::text, 'pusher_email', %s)
    FROM sid
    WHERE EXISTS (SELECT 1 FROM ins)
    RETURNING id
)
SELECT (SELECT id FROM sid), EXISTS (SELECT 1 FROM ins);
COMMIT;
""" % (
            student_id, sql_str(unit_id), sql_str(head), sql_str(clone_url),
            sql_str(pusher_email),
            student_id, sql_str(unit_id), sql_str(head),
            student_id, sql_str(unit_id), sql_str(head), sql_str(clone_url),
            sql_str(pusher_email),
        )
        try:
            out = db_sql(sql)
        except RuntimeError:
            self._respond(500, {"error": "database error"})
            return
        submission_id, newly = out[0]
        self._respond(200, {
            "ok": True,
            "known_pusher": True,
            "submission_id": int(submission_id),
            "newly_inserted": newly == "t",
        })


def unit_from_repo(full_name):
    """owner/keel-<unit-id>-<anything> -> unit id, else None.

    The repo name (after the last '/') must start with 'keel-'; the segment
    between that prefix and the next '-' must match ^\\d+\\.\\d+\\.\\d+$.
    """
    name = full_name.rsplit("/", 1)[-1]
    if not name.startswith("keel-"):
        return None
    rest = name[len("keel-"):]
    candidate = rest.split("-", 1)[0]
    import re
    global UNIT_RE
    if UNIT_RE is None:
        UNIT_RE = re.compile(r"^\d+\.\d+\.\d+$")
    return candidate if UNIT_RE.match(candidate) else None


def main():
    port = int(os.environ.get("KEEL_INTAKE_PORT", "8787"))
    if not os.environ.get("KEEL_WEBHOOK_SECRET"):
        sys.stderr.write("refusing to start: KEEL_WEBHOOK_SECRET not set\n")
        sys.exit(1)
    # Fail fast on a bad KEEL_DB_CMD.
    db_sql("BEGIN;\nSELECT 1;\nROLLBACK;\n", want_rows=False)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write("intake listening on 127.0.0.1:%d\n" % port)
    server.serve_forever()


if __name__ == "__main__":
    main()
