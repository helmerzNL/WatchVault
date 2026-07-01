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
from .progress import recompute_title_progress


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
            recompute_title_progress(cur, user_id, title_id)
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
            recompute_title_progress(cur, user_id, str(ep["title_id"]))
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
            recompute_title_progress(cur, user_id, title_id)
        return {"status": "ok", "inserted": added, "total": len(eps)}


def remove_watch_date(user_ids: list[str], *, watched_date: dt.date,
                      match_sql: str, match_params: list,
                      title_id: str | None = None) -> dict:
    """Delete every watch event for the matched item on ``watched_date`` for the
    given household members, regardless of source.

    Synced/imported events (Plex, Trakt, Netflix, …) are *tombstoned*: the row is
    kept with ``deleted_at`` set so it vanishes from every view and aggregate, but
    its unique ``dedup_hash`` stays in place — so the next sync hits
    ``ON CONFLICT (dedup_hash) DO NOTHING`` and never re-adds it. Hand-entered
    ``manual`` events are hard-deleted so the same date can be added again later.

    Returns ``{"removed": n}``."""
    ids = [str(u) for u in (user_ids or [])]
    if not ids:
        return {"removed": 0}
    with connection() as conn, conn.cursor() as cur:
        pairs: set = set()
        removed = 0
        # Tombstone synced events (keep the row + dedup_hash so resync skips it).
        cur.execute(
            "UPDATE watch_events we SET deleted_at = now() FROM providers p "
            "WHERE we.provider_id = p.id AND p.key <> 'manual' "
            "AND we.deleted_at IS NULL AND we.user_id = ANY(%s::uuid[]) "
            "AND we.watched_date = %s AND " + match_sql +
            " RETURNING we.user_id, we.provider_id",
            [ids, watched_date] + match_params,
        )
        for r in cur.fetchall():
            pairs.add((str(r["user_id"]), str(r["provider_id"])))
            removed += 1
        # Hard-delete manual events so the same date can be re-entered.
        cur.execute(
            "DELETE FROM watch_events we USING providers p "
            "WHERE we.provider_id = p.id AND p.key = 'manual' "
            "AND we.user_id = ANY(%s::uuid[]) AND we.watched_date = %s AND " + match_sql +
            " RETURNING we.user_id, we.provider_id",
            [ids, watched_date] + match_params,
        )
        for r in cur.fetchall():
            pairs.add((str(r["user_id"]), str(r["provider_id"])))
            removed += 1
        for uid, pid in pairs:
            _recompute(cur, uid, pid, [watched_date])
        # Removing a watch can flip a title back to in-progress (or off the list).
        if title_id:
            for uid in {u for u, _ in pairs}:
                recompute_title_progress(cur, uid, title_id)
        return {"removed": removed}


def delete_episode_watch(user_ids: list[str], episode_id: str,
                         watched_date: dt.date) -> dict:
    """Remove one episode's watch on ``watched_date`` (all sources, all matched
    household members). Matches events linked by episode id or by season/episode
    number so provider rows that never resolved an episode id are caught too."""
    with connection() as conn, conn.cursor() as cur:
        ep = _one(cur, "SELECT title_id, season, episode FROM title_episodes "
                       "WHERE id = %s", (episode_id,))
    if not ep:
        return {"status": "no_episode", "removed": 0}
    match = ("(we.episode_id = %s OR (we.title_id = %s "
             "AND COALESCE(we.season, 0) = %s AND we.episode = %s))")
    params = [str(episode_id), str(ep["title_id"]), ep["season"] or 0, ep["episode"]]
    res = remove_watch_date(user_ids, watched_date=watched_date,
                            match_sql=match, match_params=params,
                            title_id=str(ep["title_id"]))
    return {"status": "ok", **res}


def delete_movie_watch(user_ids: list[str], title_id: str,
                       watched_date: dt.date) -> dict:
    """Remove a movie's watch on ``watched_date`` (all sources, all matched
    household members)."""
    match = "(we.title_id = %s AND we.episode_id IS NULL)"
    res = remove_watch_date(user_ids, watched_date=watched_date,
                            match_sql=match, match_params=[str(title_id)],
                            title_id=str(title_id))
    return {"status": "ok", **res}


def _one(cur, sql: str, params: tuple):
    cur.execute(sql, params)
    return cur.fetchone()


def delete_title(title_id: str) -> dict:
    """Hard-delete a whole title (movie or series) from the catalog and every
    watch event that references it, then rebuild the affected daily aggregates.

    Episodes, cast/crew links, genres and attribution rows cascade off the
    ``titles`` row automatically; ``watch_events.title_id`` is ``ON DELETE SET
    NULL`` so those events are removed explicitly here (otherwise they'd linger
    as orphaned, title-less rows that still count toward watch time). Live
    ``scrobble_sessions`` keep their row but lose the link (SET NULL).

    Returns ``{"status": "ok", "title": <name>, "removed_events": n}`` or
    ``{"status": "no_title"}`` when the id doesn't exist."""
    with connection() as conn, conn.cursor() as cur:
        t = _one(cur, "SELECT id, title FROM titles WHERE id = %s", (title_id,))
        if not t:
            return {"status": "no_title", "removed_events": 0}
        # Capture (user, provider, date) tuples before deleting so we can rebuild
        # the precomputed daily aggregates for exactly the affected days.
        cur.execute(
            "SELECT DISTINCT user_id, provider_id, watched_date "
            "FROM watch_events WHERE title_id = %s",
            (str(title_id),),
        )
        affected: dict[tuple[str, str], list[dt.date]] = {}
        for r in cur.fetchall():
            key = (str(r["user_id"]), str(r["provider_id"]))
            affected.setdefault(key, []).append(r["watched_date"])
        cur.execute("DELETE FROM watch_events WHERE title_id = %s RETURNING id",
                    (str(title_id),))
        removed = len(cur.fetchall())
        # Drop the catalog row last; episodes/people/genres/attribution cascade.
        cur.execute("DELETE FROM titles WHERE id = %s", (str(title_id),))
        for (uid, pid), dates in affected.items():
            _recompute(cur, uid, pid, dates)
        return {"status": "ok", "title": t["title"], "removed_events": removed}
