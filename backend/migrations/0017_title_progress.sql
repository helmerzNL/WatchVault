-- 0017 — Per-user title completion tracking ("not yet finished" tracker).
-- Precomputed status so the dashboard "unfinished" block and title pages don't
-- have to live-aggregate raw events. One row per (user, title); maintained by
-- recompute_title_progress() on every write path that can change completion:
-- ingest, enrichment (episode totals become known), expert delete, and the
-- live scrobble commit.
CREATE TABLE title_progress (
    user_id           uuid NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    title_id          uuid NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    status            text NOT NULL,                       -- 'in_progress' | 'finished'
    watched_episodes  integer NOT NULL DEFAULT 0,          -- series: distinct episodes seen
    total_episodes    integer NOT NULL DEFAULT 0,          -- series: COUNT(title_episodes); 0 for movies
    last_activity_at  timestamptz,                         -- max(watched_at, live session updated_at)
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, title_id)
);
CREATE INDEX idx_title_progress_user_status ON title_progress(user_id, status);
CREATE INDEX idx_title_progress_title       ON title_progress(title_id);
