-- 0003 — Core domain model
-- Providers (platform catalog) + configured source connections, the central
-- Title/Episode/Person/Genre entities, and normalized WatchEvents with a
-- dedup hash. external_ids keeps the door open for future cross-system links
-- (e.g. a disc in DiscVault/MovieVault) without a hard dependency.

-- ── Providers: catalog of supported platforms ─────────────────────────────
CREATE TABLE providers (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key          text NOT NULL UNIQUE,         -- 'netflix','plex','jellyfin',...
    name         text NOT NULL,
    ingest_type  text NOT NULL,                -- 'api' | 'csv' | 'json'
    adapter      text NOT NULL,                -- adapter id (registry key)
    color        text,                         -- brand color for charts
    is_system    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

INSERT INTO providers (key, name, ingest_type, adapter, color) VALUES
    ('netflix',    'Netflix',     'csv',  'netflix_csv',  '#E50914'),
    ('plex',       'Plex',        'api',  'plex_api',     '#E5A00D'),
    ('jellyfin',   'Jellyfin',    'api',  'jellyfin_api', '#00A4DC'),
    ('hbomax',     'HBO Max',     'csv',  'generic',      '#7B2BF9'),
    ('skyshowtime','SkyShowtime', 'csv',  'generic',      '#1A0E45'),
    ('videoland',  'Videoland',   'csv',  'generic',      '#FF3C5F'),
    ('nlziet',     'NLZiet',      'csv',  'generic',      '#FF6B00'),
    ('disney',     'Disney+',     'csv',  'generic',      '#113CCF'),
    ('prime',      'Prime Video', 'csv',  'generic',      '#00A8E1'),
    ('generic',    'Other',       'json', 'generic',      '#8E8E93');

-- ── Configured source connections (per household; holds API creds/config) ──
CREATE TABLE source_connections (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    provider_id   uuid NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name          text NOT NULL,
    config        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- base_url, token, etc.
    enabled       boolean NOT NULL DEFAULT true,
    cursor        jsonb NOT NULL DEFAULT '{}'::jsonb,    -- sync high-water mark
    last_sync_at  timestamptz,
    last_status   text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_source_conn_household ON source_connections(household_id);

-- ── Genres & people ────────────────────────────────────────────────────────
CREATE TABLE genres (
    id       serial PRIMARY KEY,
    name     text NOT NULL UNIQUE,
    tmdb_id  integer
);

CREATE TABLE people (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    normalized_key  text NOT NULL,
    tmdb_id         integer UNIQUE,
    profile_path    text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_people_normkey ON people(normalized_key);

-- ── Titles (movie or series) ───────────────────────────────────────────────
CREATE TABLE titles (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind            text NOT NULL,             -- 'movie' | 'series'
    title           text NOT NULL,
    original_title  text,
    year            integer,
    overview        text,
    runtime_minutes integer,
    poster_path     text,
    backdrop_path   text,
    tmdb_id         integer,
    imdb_id         text,
    external_ids    jsonb NOT NULL DEFAULT '{}'::jsonb,  -- future cross-system links
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    normalized_key  text NOT NULL,
    enriched_at     timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    revision        bigint NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX idx_titles_normkey ON titles(kind, normalized_key);
CREATE INDEX idx_titles_tmdb ON titles(tmdb_id) WHERE tmdb_id IS NOT NULL;
CREATE INDEX idx_titles_revision ON titles(revision);
CREATE TRIGGER trg_titles_revision BEFORE INSERT OR UPDATE ON titles
    FOR EACH ROW EXECUTE FUNCTION wv_set_revision();

-- ── Episodes (sub-entities of a series) ────────────────────────────────────
CREATE TABLE title_episodes (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title_id        uuid NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    season          integer NOT NULL DEFAULT 0,
    episode         integer NOT NULL DEFAULT 0,
    name            text,
    overview        text,
    air_date        date,
    runtime_minutes integer,
    still_path      text,
    tmdb_id         integer,
    normalized_key  text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (title_id, season, episode)
);
CREATE INDEX idx_episodes_title ON title_episodes(title_id);

-- ── Title ↔ people / genres ────────────────────────────────────────────────
CREATE TABLE title_people (
    title_id    uuid NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    person_id   uuid NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    role        text NOT NULL DEFAULT 'cast',   -- 'cast' | 'crew'
    character   text,
    job         text,
    ord         integer NOT NULL DEFAULT 0,
    PRIMARY KEY (title_id, person_id, role)
);
CREATE INDEX idx_title_people_person ON title_people(person_id);

CREATE TABLE title_genres (
    title_id  uuid NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    genre_id  integer NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (title_id, genre_id)
);
CREATE INDEX idx_title_genres_genre ON title_genres(genre_id);

-- ── Watch events (normalized, deduplicated) ────────────────────────────────
CREATE TABLE watch_events (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id         uuid NOT NULL REFERENCES providers(id),
    source_connection_id uuid REFERENCES source_connections(id) ON DELETE SET NULL,
    title_id            uuid REFERENCES titles(id) ON DELETE SET NULL,
    episode_id          uuid REFERENCES title_episodes(id) ON DELETE SET NULL,
    item_kind           text NOT NULL DEFAULT 'movie',  -- 'movie' | 'episode'
    raw_title           text NOT NULL,
    season              integer,
    episode             integer,
    watched_at          timestamptz NOT NULL,
    watched_date        date NOT NULL,
    duration_seconds    integer,
    progress_percent    numeric(5,2),
    completed           boolean NOT NULL DEFAULT false,
    raw                 jsonb NOT NULL DEFAULT '{}'::jsonb,
    dedup_hash          text NOT NULL UNIQUE,
    created_at          timestamptz NOT NULL DEFAULT now(),
    revision            bigint NOT NULL DEFAULT 0,
    deleted_at          timestamptz
);
CREATE INDEX idx_we_user_date  ON watch_events(user_id, watched_date);
CREATE INDEX idx_we_provider   ON watch_events(provider_id);
CREATE INDEX idx_we_title      ON watch_events(title_id);
CREATE INDEX idx_we_date       ON watch_events(watched_date);
CREATE INDEX idx_we_revision   ON watch_events(revision);
CREATE TRIGGER trg_we_revision BEFORE INSERT OR UPDATE ON watch_events
    FOR EACH ROW EXECUTE FUNCTION wv_set_revision();
