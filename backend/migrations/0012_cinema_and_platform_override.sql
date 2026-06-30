-- 0012 — Cinema platform + per-title platform override
--
-- (a) "Cinema" (Bioscoop) provider: a place to attribute films you saw in the
--     cinema, which have no streaming source. Like the other non-API placeholders
--     it uses the generic adapter; ingest_type 'manual' keeps the sync scheduler
--     (which only schedules ingest_type='api') from ever touching it. It is purely
--     a manual / override target, not an import source. Idempotent.
--
-- (b) titles.platform_override_provider_id: lets a household force the platform
--     for a whole title. When set, the re-attribution moves the title's "soft"
--     events (Trakt + manual) onto this provider instead of the TMDB-network
--     guess. Real digital syncs (Plex/Jellyfin/Netflix CSV/generic imports) are
--     never moved. NULL means "Auto" (network resolution).
INSERT INTO providers (key, name, ingest_type, adapter, color, is_system) VALUES
    ('cinema', 'Cinema', 'manual', 'generic', '#B23A48', true)
ON CONFLICT (key) DO NOTHING;

ALTER TABLE titles
    ADD COLUMN IF NOT EXISTS platform_override_provider_id uuid
        REFERENCES providers(id);
