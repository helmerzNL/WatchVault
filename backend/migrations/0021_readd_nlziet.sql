-- 0021 — Re-add the NLZiet provider
-- NLZiet was seeded in 0003 and later dropped in 0008. It's back on the bundled
-- provider list by request. Like the other non-API placeholders (HBO Max,
-- Videoland, Prime Video, Disney+) it uses the generic adapter and a csv ingest
-- type, so the sync scheduler (which only schedules ingest_type='api') never
-- tries to sync it. The `nlziet` network alias in networks.py already resolves
-- to this key once the provider row exists. Idempotent.
INSERT INTO providers (key, name, ingest_type, adapter, color, is_system) VALUES
    ('nlziet', 'NLZiet', 'csv', 'generic', '#FF6B00', true)
ON CONFLICT (key) DO NOTHING;
