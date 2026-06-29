-- 0006 — Trakt provider
-- Trakt.tv exposes an official REST API with watch history, synced via the
-- trakt_api adapter. Idempotent so re-applying is safe.

INSERT INTO providers (key, name, ingest_type, adapter, color) VALUES
    ('trakt', 'Trakt', 'api', 'trakt_api', '#ED1C24')
ON CONFLICT (key) DO NOTHING;
