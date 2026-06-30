-- 0013 — Trakt attribution log
--
-- Makes the network re-attribution decision visible per title: why a Trakt/
-- manual ("soft") title ends up on a real streaming service or on the generic
-- "Other" provider. ``attribution_log`` keeps the latest decision (one row per
-- title); ``attribution_log_history`` keeps a trail of changes over time. Both
-- are written from app.networks.reattribute_title_events (best-effort; logging
-- never blocks attribution). Reason codes:
--   override          — a manual platform override forced the provider
--   network_matched   — a TMDB network mapped to a configured provider
--   network_unmapped  — TMDB networks present but none are in the household list
--   movie_no_networks — a movie (TMDB exposes no networks for films) -> Other
--   not_enriched      — the series is not enriched yet / networks not fetched
--   no_networks       — the series is enriched but TMDB lists no networks
CREATE TABLE IF NOT EXISTS attribution_log (
    title_id     uuid PRIMARY KEY REFERENCES titles(id) ON DELETE CASCADE,
    title        text NOT NULL DEFAULT '',
    kind         text,
    provider_key text,
    reason       text NOT NULL,
    networks     jsonb NOT NULL DEFAULT '[]'::jsonb,
    events       integer NOT NULL DEFAULT 0,
    moved        integer NOT NULL DEFAULT 0,
    collapsed    integer NOT NULL DEFAULT 0,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attribution_log_reason  ON attribution_log(reason);
CREATE INDEX IF NOT EXISTS idx_attribution_log_updated ON attribution_log(updated_at DESC);

CREATE TABLE IF NOT EXISTS attribution_log_history (
    id           bigserial PRIMARY KEY,
    title_id     uuid REFERENCES titles(id) ON DELETE CASCADE,
    provider_key text,
    reason       text NOT NULL,
    networks     jsonb NOT NULL DEFAULT '[]'::jsonb,
    moved        integer NOT NULL DEFAULT 0,
    collapsed    integer NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attr_hist_title ON attribution_log_history(title_id, created_at DESC);
