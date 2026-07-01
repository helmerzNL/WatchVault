"""Precomputed per-user title completion status — the "not yet finished" tracker.

``recompute_title_progress(cur, user_id, title_id)`` is idempotent: it derives the
current completion status from committed watch data plus live (uncommitted)
scrobble sessions and UPSERTs (or removes) a single ``title_progress`` row. It is
called from every write path that can change whether a title is finished so the
dashboard "unfinished" block stays correct without live-aggregating raw events:

* ingest (``normalize.ingest_events``) — new/removed watches,
* enrichment (``plugins.enrich.enrich_title``) — episode totals become known,
* expert delete of a single watch date (``ingest.manual.remove_watch_date``),
* the live scrobble commit (``ingest.scrobble.handle_scrobble``) — movie/series
  in-progress and the transition to finished.

Deleting a whole title cascades ``title_progress`` off ``titles`` (FK ON DELETE
CASCADE), so ``delete_title`` needs no explicit recompute.

Completion rules (confirmed with the household):
* **Series** — finished once every TMDB-known episode is watched
  (``watched_episodes >= total_episodes`` and ``total_episodes > 0``). Until then
  it is ``in_progress`` while any episode is watched or a live session exists.
* **Movie** — finished once a committed watch event exists; ``in_progress`` while
  only a live (uncommitted) scrobble session carries partial progress.

Rows with no watch data and no live session are deleted (a title drops off the
list entirely).
"""
from __future__ import annotations


def recompute_title_progress(cur, user_id: str, title_id: str) -> str | None:
    """Recompute one ``(user, title)`` progress row on a caller-owned cursor.

    Returns the resulting status (``'finished'`` | ``'in_progress'``) or ``None``
    when the row was removed because no watch data / live session remains."""
    if not user_id or not title_id:
        return None
    cur.execute("SELECT kind FROM titles WHERE id = %s", (title_id,))
    t = cur.fetchone()
    if not t:
        cur.execute("DELETE FROM title_progress WHERE user_id = %s AND title_id = %s",
                    (user_id, title_id))
        return None
    kind = t["kind"]

    # Latest activity across committed events and live (uncommitted) sessions.
    cur.execute(
        "SELECT max(watched_at) AS last FROM watch_events "
        "WHERE user_id = %s AND title_id = %s AND deleted_at IS NULL",
        (user_id, title_id))
    last_event = cur.fetchone()["last"]
    cur.execute(
        "SELECT max(updated_at) AS last FROM scrobble_sessions "
        "WHERE user_id = %s AND title_id = %s AND committed_at IS NULL",
        (user_id, title_id))
    last_live = cur.fetchone()["last"]
    has_live = last_live is not None
    last_activity = max([d for d in (last_event, last_live) if d], default=None)

    if kind == "series":
        cur.execute("SELECT count(*) AS n FROM title_episodes WHERE title_id = %s",
                    (title_id,))
        total = cur.fetchone()["n"] or 0
        cur.execute(
            "SELECT count(*) AS n FROM ("
            "  SELECT DISTINCT COALESCE(season, 0) AS s, episode FROM watch_events "
            "  WHERE user_id = %s AND title_id = %s AND deleted_at IS NULL "
            "    AND item_kind = 'episode' AND episode IS NOT NULL"
            ") x",
            (user_id, title_id))
        watched = cur.fetchone()["n"] or 0
        if total > 0 and watched >= total:
            status = "finished"
        elif watched > 0 or has_live:
            status = "in_progress"
        else:
            cur.execute("DELETE FROM title_progress WHERE user_id = %s AND title_id = %s",
                        (user_id, title_id))
            return None
    else:  # movie
        cur.execute(
            "SELECT 1 FROM watch_events WHERE user_id = %s AND title_id = %s "
            "AND deleted_at IS NULL LIMIT 1", (user_id, title_id))
        has_event = cur.fetchone() is not None
        total, watched = 0, 0
        if has_event:
            status = "finished"
        elif has_live:
            status = "in_progress"
        else:
            cur.execute("DELETE FROM title_progress WHERE user_id = %s AND title_id = %s",
                        (user_id, title_id))
            return None

    cur.execute(
        "INSERT INTO title_progress "
        "(user_id, title_id, status, watched_episodes, total_episodes, "
        " last_activity_at, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s, now()) "
        "ON CONFLICT (user_id, title_id) DO UPDATE SET "
        "  status = EXCLUDED.status, watched_episodes = EXCLUDED.watched_episodes, "
        "  total_episodes = EXCLUDED.total_episodes, "
        "  last_activity_at = EXCLUDED.last_activity_at, updated_at = now()",
        (user_id, title_id, status, watched, total, last_activity))
    return status


def recompute_title_progress_all_users(cur, title_id: str) -> None:
    """Recompute progress for every user with watch data or a live session for
    this title. Used when the episode total changes (enrichment) so an already
    fully-watched series flips to ``finished`` once its episodes are known."""
    if not title_id:
        return
    cur.execute(
        "SELECT user_id FROM watch_events "
        "WHERE title_id = %s AND user_id IS NOT NULL "
        "UNION "
        "SELECT user_id FROM scrobble_sessions "
        "WHERE title_id = %s AND user_id IS NOT NULL",
        (title_id, title_id))
    for r in cur.fetchall():
        recompute_title_progress(cur, str(r["user_id"]), title_id)
