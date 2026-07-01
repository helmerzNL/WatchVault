-- 0018 — Collapse series split by a provider "(YYYY)" title suffix
--
-- Some providers suffix a *series* title with its release year (Plex sends
-- "Show Name (2023)") while others don't (SkyShowtime / generic CSV send
-- "Show Name"). They normalize to different keys ("show name 2023" vs
-- "show name") so ingest never merges them, leaving two cards for one show and
-- breaking cross-provider episode tracking.
--
-- The code fix (util.title_key) strips a trailing parenthetical year before
-- building a *series* normalized_key, so future ingests converge. This migration
-- reconciles rows already split in the database:
--   1. Extends wv_merge_titles to also repoint the newer scrobble_sessions and
--      title_progress children (added in 0016/0017) onto the canonical.
--   2. wv_dedupe_series_year_variants() — for every series whose display title
--      ends in "(YYYY)", merges it into its year-less sibling (canonical), or,
--      when no sibling exists yet, rewrites its key to the stripped form so a
--      future clean import matches it.
--   3. Recomputes the precomputed title_progress for each merged canonical.
--
-- Movies are deliberately untouched: their year disambiguates same-name films of
-- different years, so it stays part of the key.

-- 1. Superset of the 0014 merge: additionally repoint scrobble_sessions and
--    title_progress (their FKs are SET NULL / CASCADE, so they must be moved
--    before the dup title is deleted or the data is lost).
CREATE OR REPLACE FUNCTION wv_merge_titles(p_canonical uuid, p_dup uuid)
RETURNS void AS $$
BEGIN
    IF p_canonical = p_dup OR p_canonical IS NULL OR p_dup IS NULL THEN
        RETURN;
    END IF;

    -- 1. Ensure canonical owns every (season, episode) the dup has.
    INSERT INTO title_episodes
        (title_id, season, episode, name, overview, air_date, runtime_minutes,
         still_path, tmdb_id, normalized_key)
    SELECT p_canonical, season, episode, name, overview, air_date,
           runtime_minutes, still_path, tmdb_id, normalized_key
    FROM title_episodes WHERE title_id = p_dup
    ON CONFLICT (title_id, season, episode) DO NOTHING;

    -- 2. Repoint watch events onto the matching canonical episode, then title.
    UPDATE watch_events we
       SET episode_id = ce.id
      FROM title_episodes de
      JOIN title_episodes ce
        ON ce.title_id = p_canonical
       AND ce.season = de.season
       AND ce.episode = de.episode
     WHERE de.title_id = p_dup
       AND we.episode_id = de.id;
    UPDATE watch_events SET title_id = p_canonical WHERE title_id = p_dup;

    -- 2b. Repoint live scrobble sessions the same way (episode then title). Its
    --     title_id FK is ON DELETE SET NULL, so it must move before the delete.
    UPDATE scrobble_sessions ss
       SET episode_id = ce.id
      FROM title_episodes de
      JOIN title_episodes ce
        ON ce.title_id = p_canonical
       AND ce.season = de.season
       AND ce.episode = de.episode
     WHERE de.title_id = p_dup
       AND ss.episode_id = de.id;
    UPDATE scrobble_sessions SET title_id = p_canonical WHERE title_id = p_dup;

    -- 2c. Repoint precomputed progress where the canonical has no row for that
    --     user; the remaining dup rows cascade away with the dup delete. Counts
    --     are refreshed by the caller (wv_recompute_series_progress_title).
    UPDATE title_progress tp SET title_id = p_canonical
     WHERE tp.title_id = p_dup
       AND NOT EXISTS (
           SELECT 1 FROM title_progress c
           WHERE c.user_id = tp.user_id AND c.title_id = p_canonical);
    DELETE FROM title_progress WHERE title_id = p_dup;

    -- 3. Additive child rows: people/genres the dup had that canonical lacks.
    INSERT INTO title_people (title_id, person_id, role, character, job, ord)
    SELECT p_canonical, person_id, role, character, job, ord
    FROM title_people WHERE title_id = p_dup
    ON CONFLICT (title_id, person_id, role) DO NOTHING;

    INSERT INTO title_genres (title_id, genre_id)
    SELECT p_canonical, genre_id FROM title_genres WHERE title_id = p_dup
    ON CONFLICT DO NOTHING;

    -- 4. Provenance: keep dup entries for fields the canonical has none for.
    UPDATE metadata_provenance mp
       SET entity_id = p_canonical
     WHERE mp.entity_type = 'title' AND mp.entity_id = p_dup
       AND NOT EXISTS (
           SELECT 1 FROM metadata_provenance c
           WHERE c.entity_type = 'title' AND c.entity_id = p_canonical
             AND c.field = mp.field);
    DELETE FROM metadata_provenance
     WHERE entity_type = 'title' AND entity_id = p_dup;

    -- 5. Fill any empty scalar on the canonical from the dup.
    UPDATE titles c SET
        tmdb_id         = COALESCE(c.tmdb_id, d.tmdb_id),
        imdb_id         = COALESCE(c.imdb_id, d.imdb_id),
        year            = COALESCE(c.year, d.year),
        original_title  = COALESCE(c.original_title, d.original_title),
        overview        = COALESCE(NULLIF(c.overview, ''), d.overview),
        overviews       = d.overviews || c.overviews,
        runtime_minutes = COALESCE(c.runtime_minutes, d.runtime_minutes),
        poster_path     = COALESCE(c.poster_path, d.poster_path),
        backdrop_path   = COALESCE(c.backdrop_path, d.backdrop_path),
        external_ids    = d.external_ids || c.external_ids,
        metadata        = d.metadata || c.metadata,
        platform_override_provider_id =
            COALESCE(c.platform_override_provider_id, d.platform_override_provider_id),
        enriched_at     = COALESCE(c.enriched_at, d.enriched_at),
        updated_at      = now()
    FROM titles d
    WHERE c.id = p_canonical AND d.id = p_dup;

    -- 6. Drop the dup; its remaining children cascade away.
    DELETE FROM titles WHERE id = p_dup;

    -- 7. The canonical's runtime/episode set changed — re-roll its daily agg.
    PERFORM wv_recompute_agg_for_title(p_canonical);
END;
$$ LANGUAGE plpgsql;


-- Recompute the precomputed title_progress rows for one *series*, mirroring
-- app.ingest.progress.recompute_title_progress exactly (finished once every
-- known episode is watched; in_progress while any episode is watched or a live
-- uncommitted session exists; no row otherwise).
CREATE OR REPLACE FUNCTION wv_recompute_series_progress_title(p_title uuid)
RETURNS void AS $$
BEGIN
    DELETE FROM title_progress WHERE title_id = p_title;

    INSERT INTO title_progress
        (user_id, title_id, status, watched_episodes, total_episodes,
         last_activity_at, updated_at)
    SELECT u.user_id, p_title,
           CASE WHEN tot.total > 0 AND COALESCE(w.n, 0) >= tot.total
                THEN 'finished' ELSE 'in_progress' END,
           COALESCE(w.n, 0), tot.total,
           GREATEST(w.last_event, l.last_live), now()
    FROM (
        SELECT user_id FROM watch_events
         WHERE title_id = p_title AND deleted_at IS NULL
           AND item_kind = 'episode' AND episode IS NOT NULL AND user_id IS NOT NULL
        UNION
        SELECT user_id FROM scrobble_sessions
         WHERE title_id = p_title AND committed_at IS NULL AND user_id IS NOT NULL
    ) u
    CROSS JOIN (
        SELECT count(*) AS total FROM title_episodes WHERE title_id = p_title
    ) tot
    LEFT JOIN LATERAL (
        SELECT count(DISTINCT (COALESCE(season, 0), episode)) AS n,
               max(watched_at) AS last_event
        FROM watch_events
        WHERE title_id = p_title AND user_id = u.user_id AND deleted_at IS NULL
          AND item_kind = 'episode' AND episode IS NOT NULL
    ) w ON true
    LEFT JOIN LATERAL (
        SELECT max(updated_at) AS last_live FROM scrobble_sessions
        WHERE title_id = p_title AND user_id = u.user_id AND committed_at IS NULL
    ) l ON true
    WHERE COALESCE(w.n, 0) > 0 OR l.last_live IS NOT NULL;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION wv_dedupe_series_year_variants()
RETURNS integer AS $$
DECLARE
    v        RECORD;
    canon    uuid;
    stripped text;
    merged   integer := 0;
BEGIN
    FOR v IN
        SELECT id,
               regexp_replace(normalized_key, '\s+\d{4}$', '') AS stripped_key
        FROM titles
        WHERE kind = 'series'
          AND title ~ '\(\s*\d{4}\s*\)\s*$'   -- display title carries a paren-year
          AND normalized_key ~ '\s+\d{4}$'     -- and the key ends in that year
    LOOP
        stripped := v.stripped_key;
        IF stripped IS NULL OR stripped = '' THEN
            CONTINUE;
        END IF;
        -- Prefer a year-less sibling as canonical; tie-break oldest.
        SELECT id INTO canon FROM titles
        WHERE kind = 'series' AND normalized_key = stripped AND id <> v.id
        ORDER BY (title ~ '\(\s*\d{4}\s*\)\s*$'), created_at, id
        LIMIT 1;

        IF canon IS NOT NULL THEN
            PERFORM wv_merge_titles(canon, v.id);
            PERFORM wv_recompute_series_progress_title(canon);
            merged := merged + 1;
        ELSE
            -- No sibling yet: rewrite the key so a future clean import matches.
            UPDATE titles SET normalized_key = stripped, updated_at = now()
            WHERE id = v.id
              AND NOT EXISTS (
                  SELECT 1 FROM titles x
                  WHERE x.kind = 'series' AND x.normalized_key = stripped
                    AND x.id <> v.id);
        END IF;
    END LOOP;
    RETURN merged;
END;
$$ LANGUAGE plpgsql;


SELECT wv_dedupe_series_year_variants();
