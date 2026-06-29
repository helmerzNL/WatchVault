-- 0007 — Multilingual metadata + richer people (bios across languages).
--
-- Titles gain a per-language overview map; the scalar `overview` stays as the
-- primary/fallback. People gain biography fields (incl. a per-language map),
-- birth/death info and an enrichment timestamp so the lazy enricher can skip
-- already-resolved people.

ALTER TABLE titles
    ADD COLUMN overviews jsonb NOT NULL DEFAULT '{}'::jsonb;   -- {lang: overview}

ALTER TABLE title_episodes
    ADD COLUMN overviews jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE people
    ADD COLUMN biography      text,
    ADD COLUMN biographies    jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {lang: biography}
    ADD COLUMN birthday       date,
    ADD COLUMN deathday       date,
    ADD COLUMN place_of_birth text,
    ADD COLUMN known_for      text,
    ADD COLUMN also_known_as  jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN enriched_at    timestamptz;

-- Lazy person enrichment queue lookup (un-enriched people first).
CREATE INDEX idx_people_enriched ON people(enriched_at);
