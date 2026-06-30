-- 0008 — Remove the NLZiet provider
-- NLZiet is dropped from the bundled provider list. It is only deleted when no
-- connection or watch event still references it, so any existing data is never
-- silently lost (clean those up first, then this becomes a no-op on next start).
-- Idempotent.
DELETE FROM providers p
 WHERE p.key = 'nlziet'
   AND NOT EXISTS (SELECT 1 FROM source_connections sc WHERE sc.provider_id = p.id)
   AND NOT EXISTS (SELECT 1 FROM watch_events we WHERE we.provider_id = p.id);
