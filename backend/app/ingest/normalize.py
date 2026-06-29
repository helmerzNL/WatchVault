"""Normalize provider events into the central model: resolve/create titles &
episodes, deduplicate, write watch events, and maintain the daily aggregate."""
from __future__ import annotations

from typing import Iterable

from ..db import connection, query_one
from ..util import dedup_hash, normalize_text
from .models import NormalizedEvent


def _resolve_title(cur, kind: str, title: str, year: int | None,
                   tmdb_id: int | None, external_ids: dict) -> tuple[str, bool]:
    norm = normalize_text(title)
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


def ingest_events(user_id: str, provider_id: str, source_connection_id: str | None,
                  events: Iterable[NormalizedEvent]) -> dict:
    """Insert normalized events with dedup; returns a summary and new title ids."""
    inserted = 0
    duplicates = 0
    titles_created: list[str] = []
    touched_titles: set[str] = set()

    with connection() as conn, conn.cursor() as cur:
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
                _bump_agg(cur, user_id, provider_id, watched_date, ev.item_kind,
                          ev.duration_seconds or 0)
            else:
                duplicates += 1

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
    }


def _bump_agg(cur, user_id, provider_id, watched_date, item_kind, seconds: int) -> None:
    movies = 1 if item_kind == "movie" else 0
    episodes = 1 if item_kind == "episode" else 0
    cur.execute(
        "INSERT INTO watch_daily_agg "
        "(user_id, provider_id, watched_date, movies_count, episodes_count, events_count, total_seconds) "
        "VALUES (%s,%s,%s,%s,%s,1,%s) "
        "ON CONFLICT (user_id, provider_id, watched_date) DO UPDATE SET "
        "  movies_count   = watch_daily_agg.movies_count + EXCLUDED.movies_count, "
        "  episodes_count = watch_daily_agg.episodes_count + EXCLUDED.episodes_count, "
        "  events_count   = watch_daily_agg.events_count + 1, "
        "  total_seconds  = watch_daily_agg.total_seconds + EXCLUDED.total_seconds",
        (user_id, provider_id, watched_date, movies, episodes, seconds),
    )
