-- 0024 — Manual title & poster overrides on titles
-- A household member can rename a film/series (including "Unknown" ones) and
-- upload a custom poster. Once a field is overridden it must NOT be replaced by
-- TMDB/Trakt enrichment; only when the user removes the override does metadata
-- enrichment take over again. Two lock flags mark which fields are hand-set; the
-- pre-override values are stashed in metadata->'manual_orig' so removing an
-- override can restore the enriched value (and re-enable future enrichment).
ALTER TABLE titles
    ADD COLUMN IF NOT EXISTS manual_title  boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS manual_poster boolean NOT NULL DEFAULT false;
