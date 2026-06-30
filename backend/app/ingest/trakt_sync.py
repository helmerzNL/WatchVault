"""Per-title cross-sync against Trakt.

When a self-hosted source (Plex/Jellyfin) only knows about some episodes of a
series, Trakt usually has the rest. This module fetches the full Trakt watch
history for a single title and feeds it through the normal ingest pipeline, so
dedup, the daily aggregate and per-episode watched status all follow for free —
no separate status table needed.

Two entry points:
  * ``ingest_title_from_trakt`` — pull one title now (manual button / worker job).
  * ``enqueue_trakt_title_syncs`` — queue per-series jobs after a non-Trakt sync.
"""
from __future__ import annotations

import json

from ..db import connection, execute, query_one
from .adapters import get_adapter
from .normalize import ingest_events

TRAKT_ADAPTER = "trakt_api"


def find_trakt_connection(household_id: str) -> dict | None:
    """Return the household's enabled, authorized Trakt connection (or None).

    Per-title history is read from Trakt's authenticated ``/sync/history``
    endpoint, so a stored OAuth access token is required."""
    return query_one(
        "SELECT sc.id, sc.config, sc.household_id, p.id AS provider_id, p.adapter "
        "FROM source_connections sc JOIN providers p ON p.id = sc.provider_id "
        "WHERE sc.household_id = %s AND sc.enabled AND p.adapter = %s "
        "AND COALESCE(sc.config->>'access_token', '') <> '' "
        "ORDER BY sc.created_at LIMIT 1",
        (household_id, TRAKT_ADAPTER),
    )


def trakt_configured(household_id: str) -> bool:
    """True when the household has an authorized Trakt connection."""
    return find_trakt_connection(household_id) is not None


def ingest_title_from_trakt(target_user_id: str, household_id: str,
                            title_id: str) -> dict:
    """Pull one title's full Trakt history and ingest it for ``target_user_id``.

    Returns a status dict. Dedup means already-synced Trakt events are skipped;
    only genuinely new watches (e.g. episodes Plex never saw) are added."""
    conn = find_trakt_connection(household_id)
    if not conn:
        return {"status": "no_trakt"}
    title = query_one(
        "SELECT id, kind, tmdb_id, external_ids FROM titles WHERE id = %s", (title_id,))
    if not title:
        return {"status": "no_title"}

    adapter = get_adapter(conn["adapter"])
    config = conn["config"] or {}
    new_config, changed = adapter.prepare_config(config)
    if changed:
        execute("UPDATE source_connections SET config = %s WHERE id = %s",
                (json.dumps(new_config), conn["id"]))
        config = new_config

    title_ref = {
        "kind": title["kind"],
        "tmdb_id": title["tmdb_id"],
        "external_ids": title["external_ids"] or {},
    }
    events = adapter.fetch_title_history(config, title_ref)
    if not events:
        return {"status": "ok", "fetched": 0, "inserted": 0, "duplicates": 0}
    summary = ingest_events(target_user_id, str(conn["provider_id"]),
                            str(conn["id"]), events)
    return {"status": "ok", "fetched": len(events), **summary}


def enqueue_trakt_title_syncs(household_id: str, target_user_id: str,
                              series_title_ids) -> int:
    """Queue a ``trakt_title_sync`` job per series title, deduped against any
    pending/running job for the same title+user. No-op when Trakt isn't set up.
    Returns the number of jobs enqueued."""
    ids = [str(t) for t in (series_title_ids or [])]
    if not ids or not trakt_configured(household_id):
        return 0
    enqueued = 0
    with connection() as conn, conn.cursor() as cur:
        for tid in ids:
            payload = json.dumps({"title_id": tid, "user_id": str(target_user_id),
                                  "household_id": str(household_id)})
            cur.execute(
                "INSERT INTO background_jobs (kind, payload) "
                "SELECT 'trakt_title_sync', %s WHERE NOT EXISTS ("
                "  SELECT 1 FROM background_jobs WHERE kind='trakt_title_sync' "
                "  AND payload->>'title_id' = %s AND payload->>'user_id' = %s "
                "  AND status IN ('pending','running')) RETURNING id",
                (payload, tid, str(target_user_id)),
            )
            if cur.fetchone():
                enqueued += 1
    return enqueued
