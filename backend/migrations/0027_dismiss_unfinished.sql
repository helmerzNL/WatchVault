-- 0027 — Dismiss ("hide") a title from the "not yet finished" tracker
-- A household member can long-press a title in the dashboard "still to watch"
-- block and hide it. Hiding stamps dismissed_at; the tracker then omits the
-- title until a *new* watch session pushes last_activity_at past that stamp, at
-- which point an unfinished title reappears. dismissed_at is intentionally NOT
-- touched by recompute_title_progress, so the hidden state survives rollup
-- refreshes and is only superseded by genuinely newer activity.
ALTER TABLE title_progress
    ADD COLUMN IF NOT EXISTS dismissed_at timestamptz;
