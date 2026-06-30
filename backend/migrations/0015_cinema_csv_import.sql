-- 0015 — Cinema as a CSV import source
--
-- The Cinema (Bioscoop) provider was a manual/override-only target. Make it a
-- selectable file-import provider so a household can bulk-import cinema visits
-- from a simple 'date, film title' CSV. It gets its own dedicated adapter
-- ('cinema') that parses that headerless format into movie watch events.
--
-- ingest_type 'csv' (not 'api') keeps the sync scheduler from touching it, and
-- it still works as a platform-override target. Idempotent.
UPDATE providers
   SET ingest_type = 'csv', adapter = 'cinema'
 WHERE key = 'cinema';
