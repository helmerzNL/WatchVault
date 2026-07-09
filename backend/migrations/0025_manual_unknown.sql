-- 0025 — Manual "Unknown" category override
-- The Unknown bucket is normally derived (a series with no recognized
-- season/episode). A household member can now also move any title into or out
-- of Unknown by hand via a long-press. A nullable tri-state override wins over
-- the derived rule: NULL = automatic, true = force Unknown, false = force known.
ALTER TABLE titles
    ADD COLUMN IF NOT EXISTS manual_unknown boolean;

CREATE OR REPLACE FUNCTION wv_title_is_unknown(p_title_id uuid)
RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN t.manual_unknown IS NOT NULL THEN t.manual_unknown
        ELSE (
            t.kind = 'series'
            AND NOT EXISTS (
                SELECT 1 FROM title_episodes te WHERE te.title_id = t.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM watch_events we
                WHERE we.title_id = t.id
                  AND (we.season IS NOT NULL OR we.episode IS NOT NULL)
            )
        )
    END
    FROM titles t
    WHERE t.id = p_title_id;
$$;
