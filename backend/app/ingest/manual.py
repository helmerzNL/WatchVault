"""Manual watch entries: mark a movie, a whole season, or a single episode as
watched (or add an extra watch date) by hand. These are normal watch_events
attributed to the built-in ``manual`` provider, so they flow through every
aggregate, overview and search just like imported watches — but no sync ever
creates or removes them.

The dedup hash mirrors the import path (see normalize.ingest_events): for an
episode it keys on the *series* title + season + episode number, for a movie on
the title. Marking the same thing watched on the same date twice is therefore a
no-op. Watch time still rolls up runtime-aware via the daily aggregate, because
manual events carry no explicit duration."""
from __future__ import annotations

import datetime as dt
import json

from ..db import connection
from ..util import dedup_hash, normalize_text


def _provider_id(cur) -> str | None:
    cur.execute("SELECT id FROM providers WHERE key = 'manual'")
    row = cur.fetchone()
    return row["id"] if row else None


def _insert_event(cur, provider_id: str, user_id: str, title_id: str,
                  episode_id: str | None, item_kind: str, dedup_title: str,
                  raw_title: str, season: int | None, episode: int | None,
                  watched_date: dt.date) -> str | None:
    """Insert one manual watch event with dedup; returns the new id or None when
    an identical entry already exists."""
    watched_at = dt.datetime.combine(watched_date, dt.time(12, 0),
                                     tzinfo=dt.timezone.utc)
    ep_token = episode if episode is not None else ""
    dh = dedup_hash(user_id, provider_id, normalize_text(dedup_title),
                    season, ep_token, watched_date)
    cur.execute(
        "INSERT INTO watch_events "
        "(user_id, provider_id, source_connection_id, title_id, episode_id, "
        " item_kind, raw_title, season, episode, watched_at, watched_date, "
        " completed, raw, dedup_hash) "
        "VALUES (%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s) "
        "ON CONFLICT (dedup_hash) DO NOTHING RETURNING id",
        (user_id, provider_id, title_id, episode_id, item_kind, raw_title,
         season, episode, watched_at, watched_date,
         json.dumps({"source": "manual"}), dh),
    )
    row = cur.fetchone()
    return str(row["id"]) if row else None


def _recompute(cur, user_id: str, provider_id: str, dates: list[dt.date]) -> None:
    if dates:
        cur.execute("SELECT wv_recompute_agg_days(%s, %s, %s)",
                    (user_id, provider_id, dates))


def add_manual_movie(user_id: str, title_id: str, watched_date: dt.date) -> dict:
    """Mark a movie watched on ``watched_date``. Returns a status dict."""
    with connection() as conn, conn.cursor() as cur:
        pid = _provider_id(cur)
        if not pid:
            return {"status": "no_provider"}
        t = _one(cur, "SELECT id, title, kind FROM titles WHERE id = %s", (title_id,))
        if not t:
            return {"status": "no_title"}
        if t["kind"] != "movie":
            return {"status": "not_movie"}
        eid = _insert_event(cur, pid, user_id, title_id, None, "movie",
                            t["title"], t["title"], None, None, watched_date)
        if eid:
            _recompute(cur, user_id, pid, [watched_date])
        return {"status": "ok", "inserted": 1 if eid else 0, "id": eid}


def add_manual_episode(user_id: str, episode_id: str, watched_date: dt.date) -> dict:
    """Mark a single episode watched on ``watched_date``."""
    with connection() as conn, conn.cursor() as cur:
        pid = _provider_id(cur)
        if not pid:
            return {"status": "no_provider"}
        ep = _one(
            cur,
            "SELECT te.id, te.season, te.episode, te.name, te.title_id, t.title "
            "FROM title_episodes te JOIN titles t ON t.id = te.title_id "
            "WHERE te.id = %s",
            (episode_id,),
        )
        if not ep:
            return {"status": "no_episode"}
        raw = ep["name"] or f"S{ep['season']}E{ep['episode']}"
        eid = _insert_event(cur, pid, user_id, str(ep["title_id"]), str(ep["id"]),
                            "episode", ep["title"], raw, ep["season"], ep["episode"],
                            watched_date)
        if eid:
            _recompute(cur, user_id, pid, [watched_date])
        return {"status": "ok", "inserted": 1 if eid else 0, "id": eid}


def add_manual_season(user_id: str, title_id: str, season: int,
                      watched_date: dt.date) -> dict:
    """Mark every episode of one season watched on ``watched_date``. Episodes
    already marked for that date are skipped (dedup)."""
    with connection() as conn, conn.cursor() as cur:
        pid = _provider_id(cur)
        if not pid:
            return {"status": "no_provider"}
        t = _one(cur, "SELECT id, title FROM titles WHERE id = %s", (title_id,))
        if not t:
            return {"status": "no_title"}
        cur.execute(
            "SELECT id, season, episode, name FROM title_episodes "
            "WHERE title_id = %s AND season = %s ORDER BY episode",
            (title_id, season),
        )
        eps = cur.fetchall()
        if not eps:
            return {"status": "no_episodes"}
        added = 0
        for ep in eps:
            raw = ep["name"] or f"S{ep['season']}E{ep['episode']}"
            eid = _insert_event(cur, pid, user_id, title_id, str(ep["id"]),
                                "episode", t["title"], raw, ep["season"],
                                ep["episode"], watched_date)
            if eid:
                added += 1
        if added:
            _recompute(cur, user_id, pid, [watched_date])
        return {"status": "ok", "inserted": added, "total": len(eps)}


def remove_manual_watch(user_ids: list[str], event_id: str) -> bool:
    """Delete one hand-entered watch event (only ``manual`` events owned by the
    given household members can be removed). Rebuilds the affected aggregate day.
    Returns True when a row was removed."""
    ids = [str(u) for u in (user_ids or [])]
    if not ids:
        return False
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM watch_events we USING providers p "
            "WHERE we.id = %s AND we.provider_id = p.id AND p.key = 'manual' "
            "AND we.user_id = ANY(%s::uuid[]) "
            "RETURNING we.user_id, we.provider_id, we.watched_date",
            (event_id, ids),
        )
        row = cur.fetchone()
        if not row:
            return False
        _recompute(cur, str(row["user_id"]), str(row["provider_id"]),
                   [row["watched_date"]])
        return True


def _one(cur, sql: str, params: tuple):
    cur.execute(sql, params)
    return cur.fetchone()
