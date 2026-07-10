-- 0026 — Manual category (kind) override on titles
-- A household member can change a title's category by hand between Film, Series
-- and the new "TV Kijken" (live-TV watching) bucket. Once the category is set by
-- hand it is locked: TMDB/Trakt enrichment must not flip it back. The manual_kind
-- flag marks a hand-set category so the enrichment path (plugins.enrich) leaves
-- both the kind and the derived Unknown rule alone. 'tv' titles are skipped by
-- enrichment entirely and only surface a watch count + total watch time.
ALTER TABLE titles
    ADD COLUMN IF NOT EXISTS manual_kind boolean NOT NULL DEFAULT false;
