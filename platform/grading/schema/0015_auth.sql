-- 0015_auth.sql — self-owned auth: passwords, OAuth identities, sessions.
-- Replaces the Clerk dependency (owner direction 2026-09-07): email+password
-- plus Google and GitHub OAuth, all enforced by the enroll service and stored
-- here. Students rows stay the identity anchor: auth users bridge to them via
-- the existing external_auth_id mechanism (/auth/bridge).
--
-- Passwords are scrypt hashes (hashlib.scrypt, n=2^14 r=8 p=1, per-user salt),
-- stored as "scrypt$16384$8$1$<salt_b64>$<hash_b64>" — never plaintext, never
-- reversible. OAuth-only accounts have password_hash NULL.
-- Session tokens are 256-bit urlsafe randoms; only their sha256 hex is stored,
-- so a database leak does not yield usable sessions.

CREATE TABLE auth_users (
    id              bigserial PRIMARY KEY,
    email           text        NOT NULL UNIQUE,          -- lowercased
    password_hash   text,                                  -- NULL for OAuth-only
    display_name    text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_identities (
    id              bigserial PRIMARY KEY,
    user_id         bigint      NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    provider        text        NOT NULL CHECK (provider IN ('google', 'github')),
    subject         text        NOT NULL,                  -- stable id at the provider
    email_at_provider text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, subject)
);

CREATE TABLE auth_sessions (
    token_hash      text        PRIMARY KEY,               -- sha256 hex of the opaque token
    user_id         bigint      NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    revoked_at      timestamptz
);
CREATE INDEX auth_sessions_user_idx ON auth_sessions (user_id);

CREATE TABLE auth_reset_tokens (
    token_hash      text        PRIMARY KEY,               -- sha256 hex of the opaque token
    user_id         bigint      NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    used_at         timestamptz
);

-- Events for audit (same spine as everything else).
COMMENT ON TABLE auth_users IS 'credential store for self-owned auth (0015)';
COMMENT ON TABLE auth_sessions IS 'opaque session tokens, hashed at rest';
