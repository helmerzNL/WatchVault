"""Normalize provider events into the central model: resolve/create titles &
episodes, deduplicate, write watch events, and maintain the daily aggregate."""
from __future__ import annotations

from typing import Iterable

from ..db import connection, query_one
from ..util import dedup_hash, normalize_text, title_key
from ..catalog import apply_title_details
from .models import NormalizedEvent
from .progress import recompute_title_progress


def _resolve_title(cur, kind: str, title: str, year: int | None,
                   tmdb_id: int | None, external_ids: dict) -> tuple[str, bool]:
    norm = title_key(title, kind)
    if tmdb_id:
        cur.execute("SELECT id FROM titles WHERE tmdb_id = %s", (tmdb_id,))
        row = cur.fetchone()
        if row:
            return row["id"], False
    cur.execute("SELECT id FROM titles WHERE kind = %s AND normalized_key = %s",
                (kind, norm))
    row = cur.fetchone()
    if row:
        return row["id"], False
    cur.execute(
        "INSERT INTO titles (kind, title, year, tmdb_id, external_ids, normalized_key) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (kind, title.strip(), year, tmdb_id,
         _jsonb(external_ids), norm),
    )
    return cur.fetchone()["id"], True


def _resolve_episode(cur, title_id: str, season: int | None, episode: int | None,
                     name: str | None) -> str | None:
    # Only materialize an episode entity when we have a real episode number.
    # Providers like Netflix often give only an episode *name*, which is kept
    # on the watch_event (raw_title) and used for dedup instead.
    if episode is None:
        return None
    s = season if season is not None else 0
    e = episode
    cur.execute(
        "SELECT id FROM title_episodes WHERE title_id = %s AND season = %s AND episode = %s",
        (title_id, s, e),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    cur.execute(
        "INSERT INTO title_episodes (title_id, season, episode, name, normalized_key) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (title_id, season, episode) DO UPDATE SET name = COALESCE(title_episodes.name, EXCLUDED.name) "
        "RETURNING id",
        (title_id, s, e, name, normalize_text(name or "")),
    )
    return cur.fetchone()["id"]


def _jsonb(value: dict):
    import json
    return json.dumps(value or {})


def _apply_source_metadata(cur, title_id: str, ev: NormalizedEvent) -> None:
    """Merge a provider's own metadata (overview/genres/cast/crew/runtime) into
    the title, filling gaps only. Source stays authoritative because ingest runs
    before the TMDB enrich job."""
    md = ev.metadata or {}
    source = ev.raw.get("source") or "import"
    runtime_minutes = md.get("runtime_minutes")
    if runtime_minutes is None and ev.duration_seconds:
        runtime_minutes = round(ev.duration_seconds / 60) or None
    details = {
        "original_title": md.get("original_title"),
        "year": ev.year,
        "overview": md.get("overview"),
        "runtime_minutes": runtime_minutes,
        "tmdb_id": ev.tmdb_id,
        "external_ids": ev.external_ids,
        "genres": md.get("genres") or [],
        "cast": md.get("cast") or [],
        "crew": md.get("crew") or [],
    }
    apply_title_details(cur, title_id, details, source)


def ingest_events(user_id: str, provider_id: str, source_connection_id: str | None,
                  events: Iterable[NormalizedEvent], cur=None) -> dict:
    """Insert normalized events with dedup; returns a summary and new title ids.

    When ``cur`` is None (file import, sync scheduler) a fresh transactional
    connection is opened and committed here. When the caller passes an already-open
    cursor, all SQL runs on it and nothing is committed — the caller owns the
    transaction. The scrobble commit path uses this so the title INSERT happens on
    the same connection that already holds the uncommitted title-lock, instead of a
    second pooled connection that would block forever on it (a self-deadlock the
    Postgres deadlock detector can't see)."""
    if cur is not None:
        return _ingest_events(user_id, provider_id, source_connection_id, events, cur)
    with connection() as conn, conn.cursor() as cur:
        return _ingest_events(user_id, provider_id, source_connection_id, events, cur)


def _ingest_events(user_id: str, provider_id: str, source_connection_id: str | None,
                   events: Iterable[NormalizedEvent], cur) -> dict:
    """Core ingest logic, run on a caller-owned cursor (no connection/commit here)."""
    inserted = 0
    duplicates = 0
    titles_created: list[str] = []
    touched_titles: set[str] = set()
    progressed_titles: set[str] = set()
    series_titles: set[str] = set()
    meta_applied: set[str] = set()
    affected_dates: set = set()

    for ev in events:
        clean = (ev.clean_title or ev.raw_title or "").strip()
        if not clean:
            continue
        title_id, created = _resolve_title(
            cur, ev.title_kind, clean, ev.year, ev.tmdb_id, ev.external_ids
        )
        if created:
            titles_created.append(title_id)
        touched_titles.add(title_id)
        if ev.title_kind == "series":
            series_titles.add(title_id)
        # Capture source-native metadata once per title per ingest run.
        if ev.metadata and title_id not in meta_applied:
            meta_applied.add(title_id)
            _apply_source_metadata(cur, title_id, ev)
        episode_id = _resolve_episode(
            cur, title_id, ev.season, ev.episode, ev.episode_name
        )
        watched_date = ev.watched_at.date()
        ep_token = ev.episode if ev.episode is not None else normalize_text(ev.episode_name or "")
        dh = dedup_hash(user_id, provider_id, normalize_text(clean),
                        ev.season, ep_token, watched_date)
        cur.execute(
            "INSERT INTO watch_events "
            "(user_id, provider_id, source_connection_id, title_id, episode_id, "
            " item_kind, raw_title, season, episode, watched_at, watched_date, "
            " duration_seconds, progress_percent, completed, raw, dedup_hash) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (dedup_hash) DO NOTHING RETURNING id",
            (user_id, provider_id, source_connection_id, title_id, episode_id,
             ev.item_kind, ev.raw_title, ev.season, ev.episode, ev.watched_at,
             watched_date, ev.duration_seconds, ev.progress_percent, ev.completed,
             _jsonb(ev.raw), dh),
        )
        if cur.fetchone():
            inserted += 1
            affected_dates.add(watched_date)
            progressed_titles.add(title_id)
        else:
            duplicates += 1

    # Roll up the affected days with a runtime-aware total (real duration,
    # else episode/title runtime) so sources without a per-event duration
    # (Netflix CSV, Plex history) still contribute watch hours.
    if affected_dates:
        cur.execute("SELECT wv_recompute_agg_days(%s, %s, %s)",
                    (user_id, provider_id, list(affected_dates)))

    # Refresh the precomputed "finished / in-progress" status for titles that
    # gained a watch this run (idempotent; skips pure-duplicate re-imports).
    for tid in progressed_titles:
        recompute_title_progress(cur, user_id, tid)

    # queue enrichment for newly created titles
    for tid in titles_created:
        cur.execute(
            "INSERT INTO background_jobs (kind, payload) VALUES ('enrich_title', %s)",
            (_jsonb({"title_id": str(tid)}),),
        )

    return {
        "inserted": inserted,
        "duplicates": duplicates,
        "titles_created": len(titles_created),
        "titles_touched": len(touched_titles),
        # Series titles that gained at least one event this run — used to enqueue
        # per-title Trakt cross-syncs after a self-hosted (Plex/Jellyfin) sync.
        "series_title_ids": [str(t) for t in series_titles],
    }


def clear_connection_events(source_connection_id: str | None) -> int:
    """Remove every watch event imported by one connection (the 'wipe this source'
    action). Hard-deletes the rows and rebuilds the daily aggregate. The connection
    and its cursor are left intact, so the cleared history is not re-pulled on the
    next sync — only genuinely new watches are added going forward. Returns the count."""
    if not source_connection_id:
        return 0
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM watch_events WHERE source_connection_id = %s RETURNING id",
            (source_connection_id,),
        )
        removed = len(cur.fetchall())
        if removed:
            cur.execute("SELECT wv_rebuild_daily_agg()")
    return removed


def reset_all_data(reset_cursors: bool = True) -> dict:
    """Factory-reset the watch database: delete every watch event and the entire
    catalog built from imports (titles, episodes, people, genres and their
    metadata), then rebuild the (now empty) daily aggregate.

    Source connections themselves are kept so the user does not have to
    reconfigure credentials. When ``reset_cursors`` is True their sync cursors and
    status are cleared, so the next sync re-imports the full history from scratch.

    Returns a dict of how many rows were removed per entity."""
    with connection() as conn, conn.cursor() as cur:
        # Pending enrichment/sync jobs reference entities we are about to remove.
        cur.execute("DELETE FROM background_jobs "
                    "WHERE kind IN ('enrich_title','enrich_person','sync_connection')")
        cur.execute("DELETE FROM watch_events RETURNING id")
        events = len(cur.fetchall())
        # Deleting a title cascades to its episodes, cast/crew links and genres links.
        cur.execute("DELETE FROM titles RETURNING id")
        titles = len(cur.fetchall())
        cur.execute("DELETE FROM people RETURNING id")
        people = len(cur.fetchall())
        cur.execute("DELETE FROM genres RETURNING id")
        genres = len(cur.fetchall())
        cur.execute("DELETE FROM metadata_provenance")
        # Empties watch_daily_agg (no events left to roll up).
        cur.execute("SELECT wv_rebuild_daily_agg()")
        if reset_cursors:
            cur.execute("UPDATE source_connections "
                        "SET cursor = '{}'::jsonb, last_sync_at = NULL, last_status = NULL")
    return {"events": events, "titles": titles, "people": people, "genres": genres}


def prune_connection_libraries(source_connection_id: str | None, raw_key: str,
                               selected: set[str] | list[str]) -> int:
    """Remove a connection's watch events that came from libraries no longer in the
    selected subset. Each adapter tags an event's source library under ``raw[raw_key]``;
    events whose tag is not in ``selected`` are hard-deleted so they can be re-synced if
    the library is re-selected. Rebuilds the daily aggregate when anything is removed.
    Returns the number of pruned events. A no-op when no subset is selected."""
    selected = [str(s) for s in (selected or [])]
    if not source_connection_id or not selected:
        return 0
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM watch_events WHERE source_connection_id = %s "
            "AND raw->>%s IS NOT NULL AND NOT (raw->>%s = ANY(%s)) RETURNING id",
            (source_connection_id, raw_key, raw_key, selected),
        )
        removed = len(cur.fetchall())
        if removed:
            cur.execute("SELECT wv_rebuild_daily_agg()")
    return removed
