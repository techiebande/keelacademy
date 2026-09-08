"""Self-owned auth for the enroll service (0015): email+password, Google and
GitHub OAuth identities, opaque sessions, reset-by-email.

Design notes (the constraints the code can't say by itself):

- Passwords: scrypt (hashlib.scrypt n=2^14 r=8 p=1, 16-byte salt, 64-byte
  key), stored as "scrypt$N$r$p$salt_b64$hash_b64". Verification is
  constant-time. OAuth-only accounts have password_hash NULL.
- Sessions and reset tokens are 256-bit urlsafe randoms; the database stores
  only sha256(token), so a DB leak yields no usable credentials.
- /auth/reset/request answers 200 whether or not the email exists (no user
  enumeration); the email is sent through Resend's REST API with the key from
  env, and a send failure is logged but never changes the response.
- The identity anchor stays the students table: every successful signup,
  oauth login, or reset creates/claims a students row via bridge_student()
  with external_id "keelu_<auth_users.id>".
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import db_sql, sql_str  # noqa: E402

SESSION_TTL_S = 7 * 24 * 60 * 60
RESET_TTL_S = 30 * 60
PASSWORD_MIN = 10
PASSWORD_MAX = 200
SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN = 16384, 8, 1, 64


class AuthError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


# --- passwords --------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return "scrypt$%d$%d$%d$%s$%s" % (
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        # OAuth-only account: no password to check. Burn comparable time so a
        # missing hash is not distinguishable by latency.
        hashlib.scrypt(password.encode(), salt=b"keel-timing-pad", n=SCRYPT_N,
                       r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r),
                                p=int(p), dklen=len(expected))
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


# --- tokens -----------------------------------------------------------------

def new_token() -> str:
    return secrets.token_urlsafe(32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- students bridge ----------------------------------------------------------

def bridge_student(external_id: str, email: str, name: str | None):
    """Same resolution order as the original /auth/bridge: by
    external_auth_id; else claim by email when unlinked; else insert.
    Returns (student_id | None, email_taken_by_other)."""
    sql = """BEGIN;
WITH existing AS (
    SELECT id FROM students WHERE external_auth_id = %s
), claimed AS (
    UPDATE students SET external_auth_id = %s
    WHERE email = %s AND external_auth_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM existing)
    RETURNING id
), inserted AS (
    INSERT INTO students (email, display_name, external_auth_id)
    SELECT %s, %s, %s
    WHERE NOT EXISTS (SELECT 1 FROM existing)
      AND NOT EXISTS (SELECT 1 FROM claimed)
      AND NOT EXISTS (SELECT 1 FROM students WHERE email = %s AND external_auth_id IS NOT NULL)
    RETURNING id
), renamed AS (
    UPDATE students SET display_name = COALESCE(%s, display_name)
    WHERE id IN (SELECT id FROM existing UNION SELECT id FROM claimed
                 UNION SELECT id FROM inserted)
      AND %s IS NOT NULL
    RETURNING id
)
SELECT COALESCE((SELECT id FROM existing), (SELECT id FROM claimed),
                (SELECT id FROM inserted)),
       EXISTS (SELECT 1 FROM students WHERE email = %s
               AND external_auth_id IS NOT NULL
               AND external_auth_id <> %s);
COMMIT;
""" % (
        sql_str(external_id), sql_str(external_id), sql_str(email),
        sql_str(email), sql_str(name), sql_str(external_id), sql_str(email),
        sql_str(name), sql_str(name),
        sql_str(email), sql_str(external_id),
    )
    rows = db_sql(sql)
    sid, taken = rows[0]
    return (int(sid) if sid not in (None, "") else None), taken in ("t", "true", "True")


# --- sessions -----------------------------------------------------------------

def create_session(user_id: int) -> str:
    token = new_token()
    db_sql(
        "BEGIN;\n"
        "INSERT INTO auth_sessions (token_hash, user_id, expires_at)\n"
        "VALUES (%s, %d, now() + interval '%d seconds');\n"
        "COMMIT;\n" % (sql_str(_token_hash(token)), user_id, SESSION_TTL_S),
        want_rows=False,
    )
    return token


def session_user(token: str):
    """Validate an opaque session token; returns the user payload or None."""
    if not token or len(token) > 128:
        return None
    rows = db_sql(
        "BEGIN;\n"
        "SELECT u.id, u.email, u.display_name, s.token_hash IS NOT NULL\n"
        "FROM auth_sessions s JOIN auth_users u ON u.id = s.user_id\n"
        "WHERE s.token_hash = %s AND s.revoked_at IS NULL\n"
        "  AND s.expires_at > now();\n"
        "ROLLBACK;\n" % sql_str(_token_hash(token)),
    )
    if not rows:
        return None
    uid, email, name, _ = rows[0]
    return _user_payload(int(uid), email, name)


def revoke_session(token: str) -> None:
    db_sql(
        "BEGIN;\n"
        "UPDATE auth_sessions SET revoked_at = now()\n"
        "WHERE token_hash = %s AND revoked_at IS NULL;\n"
        "COMMIT;\n" % sql_str(_token_hash(token)),
        want_rows=False,
    )


def revoke_all_sessions(user_id: int) -> None:
    db_sql(
        "BEGIN;\n"
        "UPDATE auth_sessions SET revoked_at = now()\n"
        "WHERE user_id = %d AND revoked_at IS NULL;\n"
        "COMMIT;\n" % user_id,
        want_rows=False,
    )


def _user_payload(uid: int, email: str, name) -> dict:
    eid = "keelu_%d" % uid
    return {
        "external_id": eid,
        "externalId": eid,
        "email": email,
        "name": name if isinstance(name, str) and name.strip() else None,
    }


def _bridge_and_payload(uid: int, email: str, name) -> dict:
    payload = _user_payload(uid, email, name)
    student_id, taken = bridge_student(payload["external_id"], email, payload["name"])
    if not student_id:
        raise AuthError(409, "email_linked_to_other_account")
    payload["student_id"] = student_id
    return payload


# --- signup / login / oauth -----------------------------------------------------

def signup(email: str, password: str, name) -> dict:
    email = email.strip().lower()
    if "@" not in email or len(email) > 320:
        raise AuthError(422, "invalid_email")
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        raise AuthError(422, "password_length")
    rows = db_sql(
        "BEGIN;\n"
        "INSERT INTO auth_users (email, password_hash, display_name)\n"
        "VALUES (%s, %s, %s) RETURNING id;\n"
        "COMMIT;\n" % (sql_str(email), sql_str(hash_password(password)), sql_str(name)),
    )
    uid = int(rows[0][0])
    payload = _bridge_and_payload(uid, email, name)
    payload["session_token"] = create_session(uid)
    _event("auth.user_created", {"user_id": uid})
    return payload


# crude in-process login throttle: 10 failures per email per 15 minutes
_login_fails: dict[str, list[float]] = {}
_FAIL_LIMIT, _FAIL_WINDOW_S = 10, 15 * 60


def login(email: str, password: str) -> dict:
    email = email.strip().lower()
    now = time.monotonic()
    recent = [t for t in _login_fails.get(email, []) if now - t < _FAIL_WINDOW_S]
    if len(recent) >= _FAIL_LIMIT:
        raise AuthError(429, "too_many_attempts")
    rows = db_sql(
        "BEGIN;\n"
        "SELECT id, password_hash, display_name FROM auth_users WHERE email = %s;\n"
        "ROLLBACK;\n" % sql_str(email),
    )
    if not rows or not verify_password(password, rows[0][1]):
        recent.append(now)
        _login_fails[email] = recent[-_FAIL_LIMIT * 2:]
        raise AuthError(401, "invalid_credentials")
    _login_fails.pop(email, None)
    uid = int(rows[0][0])
    payload = _bridge_and_payload(uid, email, rows[0][2])
    payload["session_token"] = create_session(uid)
    _event("auth.session_started", {"user_id": uid, "method": "password"})
    return payload


def oauth_login(provider: str, subject: str, email: str, name) -> dict:
    email = email.strip().lower()
    if provider not in ("google", "github") or not subject or "@" not in email:
        raise AuthError(422, "invalid_oauth_identity")
    sql = """BEGIN;
WITH ident AS (
    SELECT user_id FROM auth_identities
    WHERE provider = %s AND subject = %s
), byemail AS (
    SELECT id FROM auth_users WHERE email = %s
), newuser AS (
    INSERT INTO auth_users (email, display_name)
    SELECT %s, %s
    WHERE NOT EXISTS (SELECT 1 FROM ident) AND NOT EXISTS (SELECT 1 FROM byemail)
    RETURNING id
), link AS (
    INSERT INTO auth_identities (user_id, provider, subject, email_at_provider)
    SELECT COALESCE((SELECT user_id FROM ident), (SELECT id FROM byemail),
                    (SELECT id FROM newuser)), %s, %s, %s
    WHERE NOT EXISTS (SELECT 1 FROM ident)
    RETURNING user_id
)
SELECT COALESCE((SELECT user_id FROM ident), (SELECT user_id FROM link),
                (SELECT id FROM byemail), (SELECT id FROM newuser)),
       (SELECT display_name FROM auth_users WHERE id =
           COALESCE((SELECT user_id FROM ident), (SELECT user_id FROM link),
                    (SELECT id FROM byemail), (SELECT id FROM newuser)));
COMMIT;
""" % (sql_str(provider), sql_str(subject), sql_str(email),
       sql_str(email), sql_str(name), sql_str(provider), sql_str(subject), sql_str(email))
    rows = db_sql(sql)
    uid, display = rows[0]
    if uid in (None, ""):
        raise AuthError(500, "oauth_link_failed")
    uid = int(uid)
    payload = _bridge_and_payload(uid, email, display if isinstance(display, str) else name)
    payload["session_token"] = create_session(uid)
    _event("auth.session_started", {"user_id": uid, "method": provider})
    return payload


# --- password reset ---------------------------------------------------------------

def request_reset(email: str) -> None:
    """Always succeeds silently; sends the email only when the user exists."""
    email = email.strip().lower()
    rows = db_sql(
        "BEGIN;\n"
        "SELECT id FROM auth_users WHERE email = %s;\n"
        "ROLLBACK;\n" % sql_str(email),
    )
    if not rows:
        return
    uid = int(rows[0][0])
    token = new_token()
    db_sql(
        "BEGIN;\n"
        "UPDATE auth_reset_tokens SET used_at = now()\n"
        "WHERE user_id = %d AND used_at IS NULL;\n"
        "INSERT INTO auth_reset_tokens (token_hash, user_id, expires_at)\n"
        "VALUES (%s, %d, now() + interval '%d seconds');\n"
        "COMMIT;\n" % (uid, sql_str(_token_hash(token)), uid, RESET_TTL_S),
        want_rows=False,
    )
    send_reset_email(email, token)


def confirm_reset(token: str, password: str) -> None:
    if not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        raise AuthError(422, "password_length")
    rows = db_sql(
        "BEGIN;\n"
        "UPDATE auth_reset_tokens SET used_at = now()\n"
        "WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()\n"
        "RETURNING user_id;\n"
        "COMMIT;\n" % sql_str(_token_hash(token)),
    )
    if not rows:
        raise AuthError(400, "invalid_or_expired_token")
    uid = int(rows[0][0])
    db_sql(
        "BEGIN;\n"
        "UPDATE auth_users SET password_hash = %s, updated_at = now() WHERE id = %d;\n"
        "COMMIT;\n" % (sql_str(hash_password(password)), uid),
        want_rows=False,
    )
    revoke_all_sessions(uid)
    _event("auth.password_reset", {"user_id": uid})


def send_reset_email(email: str, token: str) -> None:
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        print("[auth] RESEND_API_KEY not set; reset email not sent", file=sys.stderr)
        return
    sender = os.environ.get("KEEL_AUTH_FROM_EMAIL", "Keel Academy <onboarding@resend.dev>")
    base = os.environ.get("KEEL_APP_URL", "http://localhost:3000")
    body = (
        "Someone asked to reset the password for your Keel Academy account.\n"
        "This link works once and expires in 30 minutes:\n\n"
        f"{base}/reset-password/confirm?token={token}\n\n"
        "If this was not you, ignore this email."
    )
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({
            "from": sender,
            "to": [email],
            "subject": "Reset your Keel Academy password",
            "text": body,
        }).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except (urllib.error.URLError, OSError) as exc:
        print(f"[auth] reset email send failed for {email[:3]}***: {exc}", file=sys.stderr)


def _event(event_type: str, payload: dict) -> None:
    try:
        db_sql(
            "BEGIN;\n"
            "INSERT INTO events (type, payload) VALUES (%s, %s::jsonb);\n"
            "COMMIT;\n" % (sql_str(event_type), sql_str(json.dumps(payload))),
            want_rows=False,
        )
    except RuntimeError:
        pass  # audit events never break the auth flow
