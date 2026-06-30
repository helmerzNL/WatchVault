-- 0014 — Collapse duplicate titles that share the same TMDB id
--
-- A film/series can end up as two title rows when it arrives from two sources
-- with different title notations (e.g. Netflix CSV "The Office (US)" vs Trakt
-- "The Office"). They start with different normalized_keys so ingest doesn't
-- merge them; enrichment then assigns BOTH the same tmdb_id, leaving two cards
-- for one show.
--
-- This migration:
--   1. wv_merge_titles(canonical, dup) — repoints all children of `dup` onto
--      `canonical` (episodes remapped by season/episode so watch_events keep a
--      valid episode_id), fills any empty scalar on canonical from dup, then
--      deletes dup.
--   2. wv_dedupe_titles() — backfills: merges every existing (kind, tmdb_id)
--      group into its oldest member.
--   3. A partial UNIQUE index on (kind, tmdb_id) so a duplicate can never be
--      created again. TMDB movie and tv id namespaces are independent, so the
--      guarantee must be on (kind, tmdb_id), never tmdb_id alone.
--
-- The merge MUST run before the unique index is created (same transaction) or
-- the index would fail on the still-present duplicates.

CREATE OR REPLACE FUNCTION wv_merge_titles(p_canonical uuid, p_dup uuid)
RETURNS void AS $$
BEGIN
    IF p_canonical = p_dup OR p_canonical IS NULL OR p_dup IS NULL THEN
        RETURN;
    END IF;

    -- 1. Ensure canonical owns every (season, episode) the dup has, so each
    --    dup episode has a counterpart to repoint watch_events onto.
    INSERT INTO title_episodes
        (title_id, season, episode, name, overview, air_date, runtime_minutes,
         still_path, tmdb_id, normalized_key)
    SELECT p_canonical, season, episode, name, overview, air_date,
           runtime_minutes, still_path, tmdb_id, normalized_key
    FROM title_episodes WHERE title_id = p_dup
    ON CONFLICT (title_id, season, episode) DO NOTHING;

    -- 2. Repoint watch events that referenced a dup episode onto the matching
    --    canonical episode (by season/episode), then onto the canonical title.
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

    -- 3. Additive child rows: keep any people/genres the dup had that the
    --    canonical lacks; duplicates are dropped by the dup delete cascade.
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

    -- 5. Fill any empty scalar on the canonical from the dup. Crucially this is
    --    how the (older, possibly source-only) canonical inherits the tmdb_id
    --    and artwork discovered on the dup.
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

    -- 6. Drop the dup. Its episodes/people/genres/attribution rows cascade away;
    --    its (now repointed) watch events stay on the canonical.
    DELETE FROM titles WHERE id = p_dup;

    -- 7. The canonical's runtime/episode set changed — re-roll its daily agg.
    PERFORM wv_recompute_agg_for_title(p_canonical);
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION wv_dedupe_titles()
RETURNS integer AS $$
DECLARE
    grp     RECORD;
    canon   uuid;
    dup     uuid;
    merged  integer := 0;
BEGIN
    FOR grp IN
        SELECT kind, tmdb_id
        FROM titles
        WHERE tmdb_id IS NOT NULL
        GROUP BY kind, tmdb_id
        HAVING count(*) > 1
    LOOP
        SELECT id INTO canon FROM titles
        WHERE kind = grp.kind AND tmdb_id = grp.tmdb_id
        ORDER BY created_at, id LIMIT 1;

        FOR dup IN
            SELECT id FROM titles
            WHERE kind = grp.kind AND tmdb_id = grp.tmdb_id AND id <> canon
        LOOP
            PERFORM wv_merge_titles(canon, dup);
            merged := merged + 1;
        END LOOP;
    END LOOP;
    RETURN merged;
END;
$$ LANGUAGE plpgsql;


-- Backfill existing duplicates before enforcing uniqueness.
SELECT wv_dedupe_titles();

-- Now that the data is clean, prevent it from happening again.
CREATE UNIQUE INDEX IF NOT EXISTS idx_titles_kind_tmdb_unique
    ON titles(kind, tmdb_id) WHERE tmdb_id IS NOT NULL;
