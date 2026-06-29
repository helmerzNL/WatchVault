-- 0001 — Extensions, identity & authentication
-- Households, users, passkeys, recovery codes, sessions, WebAuthn challenges,
-- and the OAuth2 + PKCE mobile bridge.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- A monotonically increasing revision used by the offline sync spine.
CREATE SEQUENCE IF NOT EXISTS wv_revision_seq;

CREATE OR REPLACE FUNCTION wv_set_revision() RETURNS trigger AS $$
BEGIN
    NEW.revision := nextval('wv_revision_seq');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── Households ────────────────────────────────────────────────────────────
CREATE TABLE households (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL DEFAULT 'My Household',
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── Users (each household member is a passkey login user) ──────────────────
CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    display_name  text NOT NULL,
    email         text UNIQUE,
    avatar_path   text,
    accent_color  text,
    is_admin      boolean NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz,
    revision      bigint NOT NULL DEFAULT 0,
    deleted_at    timestamptz
);
CREATE INDEX idx_users_household ON users(household_id);
CREATE INDEX idx_users_revision  ON users(revision);
CREATE TRIGGER trg_users_revision BEFORE INSERT OR UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION wv_set_revision();

-- ── WebAuthn / passkey credentials ─────────────────────────────────────────
CREATE TABLE webauthn_credentials (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credential_id  bytea NOT NULL UNIQUE,
    public_key     bytea NOT NULL,
    sign_count     bigint NOT NULL DEFAULT 0,
    transports     text[] NOT NULL DEFAULT '{}',
    name           text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    last_used_at   timestamptz
);
CREATE INDEX idx_webauthn_user ON webauthn_credentials(user_id);

-- ── One-time recovery codes (salted SHA-256 hashes at rest) ────────────────
CREATE TABLE recovery_codes (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash   text NOT NULL,
    salt        text NOT NULL,
    used_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_recovery_user ON recovery_codes(user_id);

-- ── Sessions (JWT jti registry, enables revocation) ────────────────────────
CREATE TABLE sessions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti         text NOT NULL UNIQUE,
    user_agent  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz
);
CREATE INDEX idx_sessions_user ON sessions(user_id);

-- ── In-flight WebAuthn challenges (register/login ceremonies) ──────────────
CREATE TABLE webauthn_challenges (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose     text NOT NULL,           -- 'register' | 'login'
    user_id     uuid REFERENCES users(id) ON DELETE CASCADE,
    challenge   text NOT NULL,
    data        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);

-- ── OAuth2 + PKCE mobile bridge (authorization codes) ──────────────────────
CREATE TABLE oauth_authorizations (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code_hash              text NOT NULL UNIQUE,
    user_id                uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id              text NOT NULL,
    redirect_uri           text NOT NULL,
    code_challenge         text NOT NULL,
    code_challenge_method  text NOT NULL DEFAULT 'S256',
    scope                  text,
    consumed_at            timestamptz,
    created_at             timestamptz NOT NULL DEFAULT now(),
    expires_at             timestamptz NOT NULL
);
