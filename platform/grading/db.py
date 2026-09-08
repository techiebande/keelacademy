"""platform/grading/db.py — Shared database access helper (stdlib only).

Provides psql-compatible database execution via subprocess.
The command is configured via the KEEL_DB_CMD environment variable
(e.g., 'docker exec -i <container> psql -U smoke -d grading').
"""

import os
import shlex
import subprocess
import sys


def db_cmd():
    """Retrieve and shlex-split the KEEL_DB_CMD environment variable."""
    cmd = os.environ.get("KEEL_DB_CMD")
    if not cmd:
        raise RuntimeError("KEEL_DB_CMD not set (psql-compatible command)")
    return shlex.split(cmd)


def db_sql(sql, want_rows=True):
    """Run one SQL script in one psql session. Returns list of row tuples.

    The script itself manages transactions (BEGIN/COMMIT); on any statement
    error psql with ON_ERROR_STOP exits non-zero and we raise — nothing
    partial is committed because the whole script is one session.
    """
    # -q suppresses command tags (BEGIN/COMMIT/INSERT 0 1) that psql prints
    # even in tuple-only mode, so stdout carries only query rows.
    proc = subprocess.run(
        db_cmd() + ["-v", "ON_ERROR_STOP=1", "-q", "-tA", "-F", "\t"],
        input=sql.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        sys.stderr.write("db error: %s\n" % proc.stderr.decode(errors="replace"))
        raise RuntimeError("database error: %s" % proc.stderr.decode(errors="replace"))
    if not want_rows:
        return []
    rows = []
    for line in proc.stdout.decode("utf-8").splitlines():
        if line.strip():
            rows.append(tuple(line.split("\t")))
    return rows


def sql_str(value):
    """Format a Python value as a safely-escaped SQL string literal or NULL."""
    if value is None:
        return "NULL"
    return "'%s'" % str(value).replace("'", "''")
