-- 0010 — Manual watch source
-- Lets a household mark a movie, a whole season, or a single episode as watched
-- (or add an extra watch date) by hand, independent of any import/sync. Manual
-- entries are normal watch_events attributed to this provider; it is not an API
-- connection, so the sync scheduler never touches it and synced sources never
-- overwrite hand-entered watches.

INSERT INTO providers (key, name, ingest_type, adapter, color, is_system) VALUES
    ('manual', 'Handmatig', 'manual', 'manual', '#8E8E93', true)
ON CONFLICT (key) DO NOTHING;
