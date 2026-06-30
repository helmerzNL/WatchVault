-- 0009 — Runtime-aware watch-time aggregates
-- Sources like Netflix (CSV export) and Plex (history endpoint) do not report a
-- per-event duration, so watch_daily_agg.total_seconds stayed 0 and the dashboard
-- showed 0 hours for them — even after TMDB enrichment filled the title/episode
-- runtime. Make the rollup fall back to the episode runtime, then the title
-- runtime, when a watch event has no explicit duration (mirroring
-- _common.EFF_SECONDS used by the search/title views).

-- Effective seconds for a watch event:
--   real duration  ->  episode runtime  ->  title runtime  ->  0

CREATE OR REPLACE FUNCTION wv_rebuild_daily_agg() RETURNS void AS $$
BEGIN
    TRUNCATE watch_daily_agg;
    INSERT INTO watch_daily_agg
        (user_id, provider_id, watched_date, movies_count, episodes_count, events_count, total_seconds)
    SELECT
        we.user_id,
        we.provider_id,
        we.watched_date,
        count(*) FILTER (WHERE we.item_kind = 'movie'),
        count(*) FILTER (WHERE we.item_kind = 'episode'),
        count(*),
        COALESCE(sum(COALESCE(we.duration_seconds,
                              te.runtime_minutes * 60,
                              t.runtime_minutes * 60, 0)), 0)
    FROM watch_events we
    JOIN titles t ON t.id = we.title_id
    LEFT JOIN title_episodes te ON te.id = we.episode_id
    WHERE we.deleted_at IS NULL
    GROUP BY we.user_id, we.provider_id, we.watched_date;
END;
$$ LANGUAGE plpgsql;

-- Recompute only the rollup rows whose day was touched by a given title. Called
-- after enrichment fills a title's (or its episodes') runtime, so historical
-- hours appear for that title without a full table rebuild.
CREATE OR REPLACE FUNCTION wv_recompute_agg_for_title(p_title_id uuid) RETURNS void AS $$
BEGIN
    DELETE FROM watch_daily_agg a
    WHERE (a.user_id, a.provider_id, a.watched_date) IN (
        SELECT user_id, provider_id, watched_date
        FROM watch_events
        WHERE title_id = p_title_id AND deleted_at IS NULL
    );

    INSERT INTO watch_daily_agg
        (user_id, provider_id, watched_date, movies_count, episodes_count, events_count, total_seconds)
    SELECT
        we.user_id, we.provider_id, we.watched_date,
        count(*) FILTER (WHERE we.item_kind = 'movie'),
        count(*) FILTER (WHERE we.item_kind = 'episode'),
        count(*),
        COALESCE(sum(COALESCE(we.duration_seconds,
                              te.runtime_minutes * 60,
                              t.runtime_minutes * 60, 0)), 0)
    FROM watch_events we
    JOIN titles t ON t.id = we.title_id
    LEFT JOIN title_episodes te ON te.id = we.episode_id
    WHERE we.deleted_at IS NULL
      AND (we.user_id, we.provider_id, we.watched_date) IN (
          SELECT user_id, provider_id, watched_date
          FROM watch_events
          WHERE title_id = p_title_id AND deleted_at IS NULL
      )
    GROUP BY we.user_id, we.provider_id, we.watched_date;
END;
$$ LANGUAGE plpgsql;

-- Recompute the rollup for one user+provider over a set of days. Used by the
-- ingest path after an import/sync so the affected days reflect the runtime-aware
-- formula and counts stay consistent.
CREATE OR REPLACE FUNCTION wv_recompute_agg_days(p_user uuid, p_provider uuid, p_dates date[]) RETURNS void AS $$
BEGIN
    DELETE FROM watch_daily_agg
        WHERE user_id = p_user AND provider_id = p_provider AND watched_date = ANY(p_dates);

    INSERT INTO watch_daily_agg
        (user_id, provider_id, watched_date, movies_count, episodes_count, events_count, total_seconds)
    SELECT
        we.user_id, we.provider_id, we.watched_date,
        count(*) FILTER (WHERE we.item_kind = 'movie'),
        count(*) FILTER (WHERE we.item_kind = 'episode'),
        count(*),
        COALESCE(sum(COALESCE(we.duration_seconds,
                              te.runtime_minutes * 60,
                              t.runtime_minutes * 60, 0)), 0)
    FROM watch_events we
    JOIN titles t ON t.id = we.title_id
    LEFT JOIN title_episodes te ON te.id = we.episode_id
    WHERE we.deleted_at IS NULL
      AND we.user_id = p_user AND we.provider_id = p_provider
      AND we.watched_date = ANY(p_dates)
    GROUP BY we.user_id, we.provider_id, we.watched_date;
END;
$$ LANGUAGE plpgsql;

-- Backfill existing installs so already-imported, already-enriched Netflix/Plex
-- titles get their hours immediately on deploy.
SELECT wv_rebuild_daily_agg();
