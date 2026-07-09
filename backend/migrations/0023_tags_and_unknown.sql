-- 0023 — Household media tags + the derived "Unknown" category helper.
--
-- Tags are shared per household (everyone in a household sees/uses the same
-- tags). They can be attached to titles (films/series), to individual episodes,
-- and to a whole season (there is no season entity, so a season tag is keyed by
-- the (title_id, season) pair). Titles are a global catalogue shared across
-- households; the household scoping lives on the `tags` row, so joining only the
-- current household's tags naturally scopes the per-title links too.
--
-- The "Unknown" category is purely derived (no stored kind): a series-kind title
-- for which no season/episode was ever recognised — no materialised episode rows
-- and no watch event carrying a season/episode number. Such rows are really
-- one-off TV programmes, not trackable series, so the app groups them under
-- "Unknown" and excludes them from the "still to watch" tracker.

-- ── Tags (per household) ───────────────────────────────────────────────────
CREATE TABLE tags (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id  uuid NOT NULL REFERENCES households(id) ON DELETE CASCADE,
    name          text NOT NULL,
    color         text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
-- Case-insensitive uniqueness of the tag name within a household.
CREATE UNIQUE INDEX idx_tags_household_name ON tags(household_id, lower(name));
CREATE INDEX idx_tags_household ON tags(household_id);

-- ── Tag ↔ title / episode / season links ───────────────────────────────────
CREATE TABLE title_tags (
    title_id  uuid NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    tag_id    uuid NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (title_id, tag_id)
);
CREATE INDEX idx_title_tags_tag ON title_tags(tag_id);

CREATE TABLE episode_tags (
    episode_id  uuid NOT NULL REFERENCES title_episodes(id) ON DELETE CASCADE,
    tag_id      uuid NOT NULL REFERENCES tags(id)           ON DELETE CASCADE,
    PRIMARY KEY (episode_id, tag_id)
);
CREATE INDEX idx_episode_tags_tag ON episode_tags(tag_id);

-- Season tag: no season entity exists, so key it by (title_id, season).
CREATE TABLE season_tags (
    title_id  uuid NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    season    integer NOT NULL,
    tag_id    uuid NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (title_id, season, tag_id)
);
CREATE INDEX idx_season_tags_tag ON season_tags(tag_id);

-- ── Derived "Unknown" category helper ──────────────────────────────────────
-- A single source of truth shared by every query (search, stats, unfinished).
-- STABLE + reads only indexed columns (title_episodes.title_id, watch_events.title_id).
CREATE OR REPLACE FUNCTION wv_title_is_unknown(p_title_id uuid)
RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1 FROM titles t
        WHERE t.id = p_title_id AND t.kind = 'series'
    )
    AND NOT EXISTS (
        SELECT 1 FROM title_episodes te WHERE te.title_id = p_title_id
    )
    AND NOT EXISTS (
        SELECT 1 FROM watch_events we
        WHERE we.title_id = p_title_id
          AND (we.season IS NOT NULL OR we.episode IS NOT NULL)
    );
$$;
