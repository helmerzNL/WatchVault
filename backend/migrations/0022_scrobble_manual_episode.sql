-- 0022 — Manual season/episode override for live scrobble sessions
-- Some providers (SkyShowtime, Videoland via the generic Home Assistant push)
-- send only a show title with no season/episode. A household member can then
-- long-press the Now-playing card and pick the season + episode by hand. That
-- pick must survive the next progress tick (which would otherwise overwrite the
-- season/episode/title from the raw payload) and must be the value committed to
-- watch_events. A per-session flag marks such a locked, hand-picked session.
ALTER TABLE scrobble_sessions
    ADD COLUMN IF NOT EXISTS manual_episode boolean NOT NULL DEFAULT false;
