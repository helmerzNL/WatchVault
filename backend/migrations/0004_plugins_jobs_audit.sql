-- 0004 — Plugins, API tokens, background jobs & audit
-- Built-ins are registered as (non-deletable) system plugins for one
-- consistent management surface. Secrets live in jsonb, never in code.

CREATE TABLE plugins (
    id            text PRIMARY KEY,            -- manifest id, e.g. 'tmdb'
    name          text NOT NULL,
    version       text NOT NULL DEFAULT '0.0.0',
    kind          text NOT NULL DEFAULT 'provider',
    enabled       boolean NOT NULL DEFAULT true,
    is_system     boolean NOT NULL DEFAULT false,
    capabilities  jsonb NOT NULL DEFAULT '[]'::jsonb,
    manifest      jsonb NOT NULL DEFAULT '{}'::jsonb,
    settings      jsonb NOT NULL DEFAULT '{}'::jsonb,
    secrets       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- API keys etc.
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Per-field provenance: which plugin contributed which field.
CREATE TABLE metadata_provenance (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type  text NOT NULL,              -- 'title' | 'person'
    entity_id    uuid NOT NULL,
    field        text NOT NULL,
    source       text NOT NULL,              -- plugin id
    value        jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (entity_type, entity_id, field)
);

-- ── Per-user API tokens (hashed, readable prefix) ──────────────────────────
CREATE TABLE api_clients (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name          text NOT NULL,
    token_prefix  text NOT NULL,             -- non-secret, for display
    token_hash    text NOT NULL,
    salt          text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_used_at  timestamptz,
    revoked_at    timestamptz
);
CREATE INDEX idx_api_clients_user ON api_clients(user_id);
CREATE INDEX idx_api_clients_prefix ON api_clients(token_prefix);

-- ── Background jobs (FOR UPDATE SKIP LOCKED queue) ─────────────────────────
CREATE TABLE background_jobs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind          text NOT NULL,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    status        text NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    run_after     timestamptz NOT NULL DEFAULT now(),
    attempts      integer NOT NULL DEFAULT 0,
    max_attempts  integer NOT NULL DEFAULT 5,
    last_error    text,
    result        jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_jobs_pending ON background_jobs(status, run_after);

-- ── Audit & domain events ──────────────────────────────────────────────────
CREATE TABLE domain_events (
    id           bigserial PRIMARY KEY,
    type         text NOT NULL,
    entity_type  text,
    entity_id    uuid,
    data         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
    id          bigserial PRIMARY KEY,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    action      text NOT NULL,
    target      text,
    data        jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip          text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Register the TMDB plugin row (settings/secrets are filled at runtime).
INSERT INTO plugins (id, name, version, kind, is_system, capabilities, manifest)
VALUES (
    'tmdb', 'TMDB', '1.0.0', 'metadata-provider', false,
    '["search","movie_details","tv_details","person_details"]'::jsonb,
    '{"description":"The Movie Database metadata enrichment"}'::jsonb
) ON CONFLICT (id) DO NOTHING;
