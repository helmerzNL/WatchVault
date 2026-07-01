-- 0020 — Consolidate language/variant genre duplicates into one canonical row
--
-- Providers report genres in different languages: Jellyfin localizes to its
-- server language (Dutch -> "Misdaad", "Komedie") while TMDB/Trakt return
-- canonical English ("Crime", "Comedy"). The genres table therefore holds
-- several rows for the same concept, so the Search genre dropdown lists e.g.
-- both "Misdaad" and "Crime".
--
-- The code fix (app.genres.canonical_genre, used by catalog.upsert_genre) maps
-- every known alias onto a single canonical English name so future ingests
-- converge. This migration reconciles rows already split in the database, using
-- the exact same alias->canonical mapping:
--   1. For each genre row whose name is a known alias of a *different* canonical
--      name, ensure the canonical row exists (rename in place if it is the only
--      one), re-point its title_genres onto the canonical genre_id (dedup), then
--      delete the now-orphaned alias row.
-- title_genres has PK (title_id, genre_id) so re-pointed links dedupe via
-- ON CONFLICT DO NOTHING; media stays findable because every link moves to the
-- surviving canonical row.
--
-- Unknown/custom provider genres (not in the map) are left untouched.

CREATE OR REPLACE FUNCTION wv_consolidate_genres()
RETURNS integer AS $$
DECLARE
    m        RECORD;
    canon_id integer;
    merged   integer := 0;
BEGIN
    CREATE TEMP TABLE _genre_alias (
        alias_lower text PRIMARY KEY,
        canonical   text NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO _genre_alias (alias_lower, canonical) VALUES
        ('abenteuer', 'Adventure'),
        ('acción', 'Action'),
        ('acción y aventura', 'Action & Adventure'),
        ('actie', 'Action'),
        ('actie & avontuur', 'Action & Adventure'),
        ('action', 'Action'),
        ('action & abenteuer', 'Action & Adventure'),
        ('action & adventure', 'Action & Adventure'),
        ('action & aventure', 'Action & Adventure'),
        ('actualités', 'News'),
        ('adventure', 'Adventure'),
        ('animación', 'Animation'),
        ('animatie', 'Animation'),
        ('animation', 'Animation'),
        ('animazione', 'Animation'),
        ('aventura', 'Adventure'),
        ('aventure', 'Adventure'),
        ('avontuur', 'Adventure'),
        ('avventura', 'Adventure'),
        ('azione', 'Action'),
        ('azione e avventura', 'Action & Adventure'),
        ('bambini', 'Kids'),
        ('bélica', 'War'),
        ('ciencia ficción', 'Science Fiction'),
        ('comedia', 'Comedy'),
        ('comedy', 'Comedy'),
        ('commedia', 'Comedy'),
        ('comédie', 'Comedy'),
        ('crime', 'Crime'),
        ('crimen', 'Crime'),
        ('crimine', 'Crime'),
        ('documentaire', 'Documentary'),
        ('documental', 'Documentary'),
        ('documentario', 'Documentary'),
        ('documentary', 'Documentary'),
        ('dokumentarfilm', 'Documentary'),
        ('drama', 'Drama'),
        ('drame', 'Drama'),
        ('dramma', 'Drama'),
        ('enfants', 'Kids'),
        ('famiglia', 'Family'),
        ('familia', 'Family'),
        ('familial', 'Family'),
        ('familie', 'Family'),
        ('family', 'Family'),
        ('fantascienza', 'Science Fiction'),
        ('fantastique', 'Fantasy'),
        ('fantasy', 'Fantasy'),
        ('fantasía', 'Fantasy'),
        ('feuilleton', 'Soap'),
        ('film tv', 'TV Movie'),
        ('guerra', 'War'),
        ('guerra e politica', 'War & Politics'),
        ('guerra y política', 'War & Politics'),
        ('guerre', 'War'),
        ('guerre & politique', 'War & Politics'),
        ('histoire', 'History'),
        ('historia', 'History'),
        ('historie', 'History'),
        ('historisch', 'History'),
        ('history', 'History'),
        ('horreur', 'Horror'),
        ('horror', 'Horror'),
        ('infantil', 'Kids'),
        ('kids', 'Kids'),
        ('kinder', 'Kids'),
        ('kinderen', 'Kids'),
        ('komedie', 'Comedy'),
        ('komödie', 'Comedy'),
        ('krieg', 'War'),
        ('krieg & politik', 'War & Politics'),
        ('krimi', 'Crime'),
        ('liebesfilm', 'Romance'),
        ('misdaad', 'Crime'),
        ('misterio', 'Mystery'),
        ('mistero', 'Mystery'),
        ('music', 'Music'),
        ('musica', 'Music'),
        ('musik', 'Music'),
        ('musique', 'Music'),
        ('muziek', 'Music'),
        ('mysterie', 'Mystery'),
        ('mystery', 'Mystery'),
        ('mystère', 'Mystery'),
        ('música', 'Music'),
        ('nachrichten', 'News'),
        ('news', 'News'),
        ('nieuws', 'News'),
        ('noticias', 'News'),
        ('notizie', 'News'),
        ('oorlog', 'War'),
        ('oorlog & politiek', 'War & Politics'),
        ('película de tv', 'TV Movie'),
        ('programa de entrevistas', 'Talk'),
        ('reality', 'Reality'),
        ('romance', 'Romance'),
        ('romantico', 'Romance'),
        ('romantiek', 'Romance'),
        ('sci-fi & fantastique', 'Sci-Fi & Fantasy'),
        ('sci-fi & fantasy', 'Sci-Fi & Fantasy'),
        ('sci-fi e fantasy', 'Sci-Fi & Fantasy'),
        ('sci-fi y fantasía', 'Sci-Fi & Fantasy'),
        ('science fiction', 'Science Fiction'),
        ('science-fiction', 'Science Fiction'),
        ('sciencefiction', 'Science Fiction'),
        ('seifenoper', 'Soap'),
        ('soap', 'Soap'),
        ('storia', 'History'),
        ('suspense', 'Thriller'),
        ('talk', 'Talk'),
        ('talk show', 'Talk'),
        ('talk-show', 'Talk'),
        ('talkshow', 'Talk'),
        ('telenovela', 'Soap'),
        ('terror', 'Horror'),
        ('thriller', 'Thriller'),
        ('tv movie', 'TV Movie'),
        ('tv-film', 'TV Movie'),
        ('téléfilm', 'TV Movie'),
        ('téléréalité', 'Reality'),
        ('war', 'War'),
        ('war & politics', 'War & Politics'),
        ('western', 'Western')
    ON CONFLICT (alias_lower) DO NOTHING;

    FOR m IN
        SELECT g.id, g.name, a.canonical
        FROM genres g
        JOIN _genre_alias a ON a.alias_lower = lower(btrim(g.name))
        WHERE btrim(g.name) <> a.canonical
    LOOP
        SELECT id INTO canon_id FROM genres WHERE name = m.canonical;

        IF canon_id IS NULL THEN
            -- No canonical row yet: rename this alias row in place.
            UPDATE genres SET name = m.canonical WHERE id = m.id;
            merged := merged + 1;
            CONTINUE;
        END IF;

        IF canon_id = m.id THEN
            CONTINUE;
        END IF;

        -- Re-point links onto the canonical row, dropping duplicates.
        INSERT INTO title_genres (title_id, genre_id)
        SELECT title_id, canon_id FROM title_genres WHERE genre_id = m.id
        ON CONFLICT DO NOTHING;
        DELETE FROM title_genres WHERE genre_id = m.id;

        -- Keep a tmdb_id on the canonical if it lacked one.
        UPDATE genres c SET tmdb_id = COALESCE(c.tmdb_id, d.tmdb_id)
        FROM genres d WHERE c.id = canon_id AND d.id = m.id;

        DELETE FROM genres WHERE id = m.id;
        merged := merged + 1;
    END LOOP;

    RETURN merged;
END;
$$ LANGUAGE plpgsql;

SELECT wv_consolidate_genres();

DROP FUNCTION wv_consolidate_genres();
