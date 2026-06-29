-- 0005 — Pre-computed aggregates for fast overviews
-- Daily rollup per (user, provider, kind) so trend/heatmap/per-platform
-- overviews never scan the raw events table. Maintained by the ingest layer
-- after each import/sync, and rebuildable from scratch.

CREATE TABLE watch_daily_agg (
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id     uuid NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    watched_date    date NOT NULL,
    movies_count    integer NOT NULL DEFAULT 0,
    episodes_count  integer NOT NULL DEFAULT 0,
    events_count    integer NOT NULL DEFAULT 0,
    total_seconds   bigint  NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, provider_id, watched_date)
);
CREATE INDEX idx_agg_date ON watch_daily_agg(watched_date);
CREATE INDEX idx_agg_user ON watch_daily_agg(user_id);

-- Rebuild the whole aggregate table from raw events (idempotent).
CREATE OR REPLACE FUNCTION wv_rebuild_daily_agg() RETURNS void AS $$
BEGIN
    TRUNCATE watch_daily_agg;
    INSERT INTO watch_daily_agg
        (user_id, provider_id, watched_date, movies_count, episodes_count, events_count, total_seconds)
    SELECT
        user_id,
        provider_id,
        watched_date,
        count(*) FILTER (WHERE item_kind = 'movie'),
        count(*) FILTER (WHERE item_kind = 'episode'),
        count(*),
        COALESCE(sum(duration_seconds), 0)
    FROM watch_events
    WHERE deleted_at IS NULL
    GROUP BY user_id, provider_id, watched_date;
END;
$$ LANGUAGE plpgsql;
