-- 0016 — Live scrobbling receiver (Plex / AppleTV / Home Assistant)
-- A push ingestion path: real-time playback progress lands in a now-playing
-- table (scrobble_sessions) and is only committed to watch_events when a play
-- completes (>= threshold or an explicit Plex `scrobble`/stop event). Incoming
-- account labels are mapped to household profiles via scrobble_account_map.

-- ── Home Assistant provider (generic JSON push hub for HA / AppleTV) ─────────
INSERT INTO providers (key, name, ingest_type, adapter, color, is_system) VALUES
    ('homeassistant', 'Home Assistant', 'json', 'generic', '#18BCF2', true)
ON CONFLICT (key) DO NOTHING;

-- ── Now-playing sessions (live, ephemeral until committed) ──────────────────
CREATE TABLE scrobble_sessions (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id      uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    user_id           uuid REFERENCES users(id) ON DELETE SET NULL,  -- resolved profile (null until mapped)
    provider_id       uuid REFERENCES providers(id),                 -- attributed platform
    source            text NOT NULL,                                 -- 'plex'|'homeassistant'|'appletv'|'generic'
    account_label     text NOT NULL DEFAULT '',                      -- incoming account name (Plex/HA user)
    platform_key      text,                                          -- payload-supplied platform (e.g. 'netflix')
    title_id          uuid REFERENCES titles(id) ON DELETE SET NULL,
    episode_id        uuid REFERENCES title_episodes(id) ON DELETE SET NULL,
    raw_title         text NOT NULL,
    kind              text NOT NULL DEFAULT 'movie',                 -- 'movie' | 'series'
    season            integer,
    episode           integer,
    episode_name      text,
    year              integer,
    tmdb_id           integer,
    progress_percent  numeric(5,2) NOT NULL DEFAULT 0,
    position_seconds  integer,
    duration_seconds  integer,
    state             text NOT NULL DEFAULT 'playing',               -- 'playing'|'paused'|'stopped'
    dedup_key         text NOT NULL,                                 -- stable per-playback key
    started_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    committed_at      timestamptz,                                   -- set once written to watch_events
    raw               jsonb NOT NULL DEFAULT '{}'::jsonb
);
-- One live session per playback: repeated progress events UPSERT instead of
-- piling up duplicate rows.
CREATE UNIQUE INDEX idx_scrobble_sessions_key
    ON scrobble_sessions(household_id, source, account_label, dedup_key);
CREATE INDEX idx_scrobble_sessions_household ON scrobble_sessions(household_id);
CREATE INDEX idx_scrobble_sessions_updated ON scrobble_sessions(updated_at);

-- ── Account → profile mapping (per household) ───────────────────────────────
CREATE TABLE scrobble_account_map (
    household_id   uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    source         text NOT NULL,
    account_label  text NOT NULL,
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (household_id, source, account_label)
);

-- Commit threshold lives in the single-row app_settings blob (default 90%).
UPDATE app_settings
   SET data = jsonb_set(data, '{scrobble_commit_threshold}', '90'::jsonb, true)
 WHERE id = 1 AND NOT (data ? 'scrobble_commit_threshold');
