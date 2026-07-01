"""Statistics & overview endpoints — the mandatory dashboards.

All endpoints accept ?profile=<user_id|all> and use the pre-computed
watch_daily_agg rollup where possible so they stay fast over years of history.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import query_all, query_one
from ..auth.sessions import require_perm
from ._common import EFF_SECONDS, poster_url, scope_user_ids

bp = Blueprint("stats", __name__, url_prefix="/api/stats")


def _ids():
    ids = scope_user_ids()
    return [str(i) for i in ids]


def _hours(seconds, ndigits: int = 2) -> float:
    """Watch hours as a JSON ``float``.

    Aggregate sums over ``bigint`` columns come back as Postgres ``numeric`` →
    Python ``Decimal``, which Flask's JSON provider serialises as a *string*.
    Casting to ``float`` keeps the wire value a number so the frontend can do
    arithmetic/formatting on it without crashing."""
    return round(float(seconds or 0) / 3600, ndigits)


_RANGE_TRUNC = {"week": "week", "month": "month", "year": "year"}


def _range_clause(range_arg: str | None, col: str) -> str:
    """SQL fragment limiting ``col`` to the current week/month/year.

    Whitelisted: only ``week``/``month``/``year`` produce a clause; anything
    else (incl. ``all``/``None``) means no date filter. ``col`` is a trusted
    column name supplied by the caller, never user input — so the returned
    fragment carries no SQL-injection surface."""
    trunc = _RANGE_TRUNC.get((range_arg or "").lower())
    if not trunc:
        return ""
    return f" AND {col} >= date_trunc('{trunc}', now())"


# Plex + Jellyfin are folded into one synthetic "Digital Library" platform in the
# per-platform breakdowns. The frontend localises the label via the key.
_DIGITAL_LIBRARY_KEYS = ("plex", "jellyfin")
_DIGITAL_LIBRARY = {"key": "digital_library", "name": "Digital Library",
                    "color": "#7C5CBF"}


def _fold_digital_library(rows: list[dict], group_fields: tuple,
                          sum_fields: tuple) -> list[dict]:
    """Combine ``plex`` + ``jellyfin`` rows into one ``digital_library`` entry.

    ``group_fields`` are dict keys identifying a bucket besides the provider
    (e.g. ``()`` for the summary list, ``("period",)`` for the time series);
    ``sum_fields`` are the numeric fields added together. Order is preserved with
    the merged entry taking the position of its first contributor."""
    out: list[dict] = []
    index: dict[tuple, dict] = {}
    for r in rows:
        if r["key"] in _DIGITAL_LIBRARY_KEYS:
            r = {**r, **_DIGITAL_LIBRARY}
        bucket = tuple(r[g] for g in group_fields) + (r["key"],)
        existing = index.get(bucket)
        if existing is None:
            nr = dict(r)
            index[bucket] = nr
            out.append(nr)
        else:
            for f in sum_fields:
                existing[f] = existing[f] + r[f]
    return out


@bp.get("/summary")
@require_perm("catalog.read")
def summary():
    ids = _ids()
    if not ids:
        return jsonify({"empty": True})

    totals = query_one(
        f"SELECT count(*) AS events, "
        f"  count(*) FILTER (WHERE we.item_kind='movie') AS movies, "
        f"  count(*) FILTER (WHERE we.item_kind='episode') AS episodes, "
        f"  count(DISTINCT we.title_id) AS titles, "
        f"  COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we LEFT JOIN titles t ON t.id = we.title_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL",
        (ids,),
    )
    month = query_one(
        f"SELECT count(*) AS events, COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we LEFT JOIN titles t ON t.id = we.title_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL "
        f"AND we.watched_date >= date_trunc('month', now())",
        (ids,),
    )
    providers = query_all(
        "SELECT p.key, p.name, p.color, sum(a.events_count) AS events, "
        "  sum(a.total_seconds) AS seconds "
        "FROM watch_daily_agg a JOIN providers p ON p.id = a.provider_id "
        "WHERE a.user_id = ANY(%s::uuid[]) "
        "GROUP BY p.key, p.name, p.color ORDER BY events DESC",
        (ids,),
    )
    recent = query_all(
        "SELECT a.watched_date AS date, sum(a.events_count) AS count "
        "FROM watch_daily_agg a WHERE a.user_id = ANY(%s::uuid[]) "
        "AND a.watched_date >= current_date - interval '29 days' "
        "GROUP BY a.watched_date ORDER BY a.watched_date",
        (ids,),
    )
    unfinished = [_unfinished_row(r) for r in _unfinished_query(ids)]
    remaining_minutes = sum(u["remaining_minutes"] or 0 for u in unfinished)
    return jsonify({
        "totals": {
            "events": totals["events"], "movies": totals["movies"],
            "episodes": totals["episodes"], "titles": totals["titles"],
            "hours": _hours(totals["seconds"], 1),
            "remaining_minutes": remaining_minutes,
            "remaining_items": len(unfinished),
        },
        "this_month": {
            "events": month["events"],
            "hours": _hours(month["seconds"], 1),
        },
        "providers": [
            {"key": r["key"], "name": r["name"], "color": r["color"],
             "events": r["events"], "hours": round(r["seconds"] / 3600, 1)}
            for r in sorted(
                _fold_digital_library(
                    [{"key": p["key"], "name": p["name"], "color": p["color"],
                      "events": int(p["events"] or 0), "seconds": float(p["seconds"] or 0)}
                     for p in providers],
                    (), ("events", "seconds")),
                key=lambda x: x["events"], reverse=True)
        ],
        "recent": [{"date": r["date"].isoformat(), "count": int(r["count"])} for r in recent],
    })


@bp.get("/providers")
@require_perm("catalog.read")
def providers_breakdown():
    """Provider distribution (events + hours), optionally limited to the current
    week/month/year. Powers the dashboard 'per platform' card."""
    ids = _ids()
    if not ids:
        return jsonify([])
    rng = _range_clause(request.args.get("range"), "a.watched_date")
    rows = query_all(
        "SELECT p.key, p.name, p.color, sum(a.events_count) AS events, "
        "  sum(a.total_seconds) AS seconds "
        "FROM watch_daily_agg a JOIN providers p ON p.id = a.provider_id "
        "WHERE a.user_id = ANY(%s::uuid[])" + rng +
        " GROUP BY p.key, p.name, p.color ORDER BY events DESC",
        (ids,),
    )
    return jsonify(sorted(
        [{"key": r["key"], "name": r["name"], "color": r["color"],
          "events": r["events"], "hours": round(r["seconds"] / 3600, 1)}
         for r in _fold_digital_library(
             [{"key": p["key"], "name": p["name"], "color": p["color"],
               "events": int(p["events"] or 0), "seconds": float(p["seconds"] or 0)}
              for p in rows],
             (), ("events", "seconds"))],
        key=lambda x: x["events"], reverse=True))


@bp.get("/recent")
@require_perm("catalog.read")
def recent_activity():
    """Activity time-series for the dashboard sparkline.

    ``range`` selects the window and granularity:
    ``week`` → last 7 days (daily), ``month`` → last 30 days (daily, default),
    ``year`` → last 12 months (monthly). Returns ``[{date, count}]`` where
    ``date`` is the day or the first-of-month for the bucket."""
    ids = _ids()
    if not ids:
        return jsonify([])
    rng = (request.args.get("range") or "month").lower()
    if rng == "week":
        rows = query_all(
            "SELECT a.watched_date AS date, sum(a.events_count) AS count "
            "FROM watch_daily_agg a WHERE a.user_id = ANY(%s::uuid[]) "
            "AND a.watched_date >= current_date - interval '6 days' "
            "GROUP BY a.watched_date ORDER BY a.watched_date",
            (ids,),
        )
    elif rng == "year":
        rows = query_all(
            "SELECT date_trunc('month', a.watched_date)::date AS date, "
            "  sum(a.events_count) AS count "
            "FROM watch_daily_agg a WHERE a.user_id = ANY(%s::uuid[]) "
            "AND a.watched_date >= date_trunc('month', now()) - interval '11 months' "
            "GROUP BY date ORDER BY date",
            (ids,),
        )
    else:
        rows = query_all(
            "SELECT a.watched_date AS date, sum(a.events_count) AS count "
            "FROM watch_daily_agg a WHERE a.user_id = ANY(%s::uuid[]) "
            "AND a.watched_date >= current_date - interval '29 days' "
            "GROUP BY a.watched_date ORDER BY a.watched_date",
            (ids,),
        )
    return jsonify([
        {"date": r["date"].isoformat(), "count": int(r["count"])} for r in rows
    ])


@bp.get("/heatmap")
@require_perm("catalog.read")
def heatmap():
    """Per-day activity for a calendar heatmap."""
    ids = _ids()
    year = request.args.get("year")
    where = "a.user_id = ANY(%s::uuid[])"
    params: list = [ids]
    if year:
        where += " AND extract(year FROM a.watched_date) = %s"
        params.append(int(year))
    rows = query_all(
        f"SELECT a.watched_date AS date, sum(a.events_count) AS count, "
        f"  sum(a.movies_count) AS movies, sum(a.episodes_count) AS episodes, "
        f"  sum(a.total_seconds) AS seconds "
        f"FROM watch_daily_agg a WHERE {where} "
        f"GROUP BY a.watched_date ORDER BY a.watched_date",
        params,
    )
    return jsonify([
        {"date": r["date"].isoformat(), "count": int(r["count"]),
         "movies": int(r["movies"]), "episodes": int(r["episodes"]),
         "hours": _hours(r["seconds"])}
        for r in rows
    ])


@bp.get("/years")
@require_perm("catalog.read")
def years():
    """Distinct years that have activity for the scope (newest first), so the
    daily-activity view can offer every year with data instead of a fixed window."""
    ids = _ids()
    rows = query_all(
        "SELECT DISTINCT extract(year FROM a.watched_date)::int AS year "
        "FROM watch_daily_agg a WHERE a.user_id = ANY(%s::uuid[]) "
        "ORDER BY year DESC",
        [ids],
    )
    return jsonify([r["year"] for r in rows])


@bp.get("/trend")
@require_perm("catalog.read")
def trend():
    """Hours and events per day/week/month."""
    ids = _ids()
    gran = request.args.get("granularity", "month")
    trunc = {"day": "day", "week": "week", "month": "month"}.get(gran, "month")
    where = "a.user_id = ANY(%s::uuid[])"
    params: list = [ids]
    for key, op in (("from", ">="), ("to", "<=")):
        v = request.args.get(key)
        if v:
            where += f" AND a.watched_date {op} %s"
            params.append(v)
    rows = query_all(
        f"SELECT date_trunc('{trunc}', a.watched_date)::date AS period, "
        f"  sum(a.events_count) AS events, sum(a.movies_count) AS movies, "
        f"  sum(a.episodes_count) AS episodes, sum(a.total_seconds) AS seconds "
        f"FROM watch_daily_agg a WHERE {where} "
        f"GROUP BY period ORDER BY period",
        params,
    )
    return jsonify([
        {"period": r["period"].isoformat(), "events": int(r["events"]),
         "movies": int(r["movies"]), "episodes": int(r["episodes"]),
         "hours": _hours(r["seconds"])}
        for r in rows
    ])


@bp.get("/by-platform")
@require_perm("catalog.read")
def by_platform():
    """Events/movies/episodes per platform per month or year (stacked chart)."""
    ids = _ids()
    period = request.args.get("period", "month")
    trunc = "year" if period == "year" else "month"
    rows = query_all(
        f"SELECT date_trunc('{trunc}', a.watched_date)::date AS period, "
        f"  p.key, p.name, p.color, sum(a.events_count) AS events, "
        f"  sum(a.movies_count) AS movies, sum(a.episodes_count) AS episodes, "
        f"  sum(a.total_seconds) AS seconds "
        f"FROM watch_daily_agg a JOIN providers p ON p.id = a.provider_id "
        f"WHERE a.user_id = ANY(%s::uuid[]) "
        f"GROUP BY period, p.key, p.name, p.color ORDER BY period",
        (ids,),
    )
    return jsonify([
        {"period": r["period"], "key": r["key"], "name": r["name"],
         "color": r["color"], "events": r["events"], "movies": r["movies"],
         "episodes": r["episodes"], "hours": round(r["seconds"] / 3600, 2)}
        for r in _fold_digital_library(
            [{"period": r["period"].isoformat(), "key": r["key"], "name": r["name"],
              "color": r["color"], "events": int(r["events"]), "movies": int(r["movies"]),
              "episodes": int(r["episodes"]), "seconds": float(r["seconds"] or 0)}
             for r in rows],
            ("period",), ("events", "movies", "episodes", "seconds"))
    ])


@bp.get("/month")
@require_perm("catalog.read")
def month_titles():
    """Titles watched in a given month (YYYY-MM), grouped per title."""
    ids = _ids()
    month = request.args.get("month")  # 'YYYY-MM'
    if not month:
        return jsonify({"error": "month=YYYY-MM required"}), 400
    rows = query_all(
        f"SELECT t.id, t.title, t.kind, t.year, t.poster_path, "
        f"  count(*) AS events, "
        f"  count(*) FILTER (WHERE we.item_kind='episode') AS episodes, "
        f"  max(we.watched_date) AS last_watched, "
        f"  COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL "
        f"AND to_char(we.watched_date, 'YYYY-MM') = %s "
        f"GROUP BY t.id ORDER BY events DESC, last_watched DESC",
        (ids, month),
    )
    return jsonify([
        {"id": str(r["id"]), "title": r["title"], "kind": r["kind"], "year": r["year"],
         "poster": poster_url(r["poster_path"]), "events": int(r["events"]),
         "episodes": int(r["episodes"]), "last_watched": r["last_watched"].isoformat(),
         "hours": _hours(r["seconds"])}
        for r in rows
    ])


@bp.get("/day")
@require_perm("catalog.read")
def day_titles():
    """Titles watched on a given day (YYYY-MM-DD), grouped per title."""
    ids = _ids()
    date = request.args.get("date")  # 'YYYY-MM-DD'
    if not date:
        return jsonify({"error": "date=YYYY-MM-DD required"}), 400
    rows = query_all(
        f"SELECT t.id, t.title, t.kind, t.year, t.poster_path, "
        f"  count(*) AS events, "
        f"  count(*) FILTER (WHERE we.item_kind='episode') AS episodes, "
        f"  COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL "
        f"AND we.watched_date = %s "
        f"GROUP BY t.id ORDER BY events DESC, t.title",
        (ids, date),
    )
    return jsonify([
        {"id": str(r["id"]), "title": r["title"], "kind": r["kind"], "year": r["year"],
         "poster": poster_url(r["poster_path"]), "events": int(r["events"]),
         "episodes": int(r["episodes"]),
         "hours": _hours(r["seconds"])}
        for r in rows
    ])


@bp.get("/by-genre")
@require_perm("catalog.read")
def by_genre():
    """Time spent per genre, optionally limited to the current week/month/year."""
    ids = _ids()
    rng = _range_clause(request.args.get("range"), "we.watched_date")
    rows = query_all(
        f"SELECT g.id, g.name, count(*) AS events, COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"JOIN title_genres tg ON tg.title_id = t.id "
        f"JOIN genres g ON g.id = tg.genre_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL" + rng +
        " GROUP BY g.id, g.name ORDER BY seconds DESC",
        (ids,),
    )
    return jsonify([
        {"genre_id": str(r["id"]), "genre": r["name"], "events": int(r["events"]),
         "hours": _hours(r["seconds"])}
        for r in rows
    ])


@bp.get("/by-actor")
@require_perm("catalog.read")
def by_actor():
    """Time spent per actor (cast), optionally limited to current week/month/year."""
    ids = _ids()
    limit = min(int(request.args.get("limit", 30)), 100)
    rng = _range_clause(request.args.get("range"), "we.watched_date")
    rows = query_all(
        f"SELECT pe.id, pe.name, pe.profile_path, count(*) AS events, "
        f"  COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"JOIN title_people tp ON tp.title_id = t.id AND tp.role = 'cast' "
        f"JOIN people pe ON pe.id = tp.person_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL" + rng +
        " GROUP BY pe.id ORDER BY seconds DESC LIMIT %s",
        (ids, limit),
    )
    return jsonify([
        {"id": str(r["id"]), "name": r["name"],
         "profile": poster_url(r["profile_path"], "w185"),
         "events": int(r["events"]), "hours": _hours(r["seconds"])}
        for r in rows
    ])


@bp.get("/genre-titles")
@require_perm("catalog.read")
def genre_titles():
    """All watched titles in a genre (poster grid), grouped per title."""
    ids = _ids()
    genre_id = request.args.get("genre")
    if not genre_id:
        return jsonify({"error": "genre=<id> required"}), 400
    rng = _range_clause(request.args.get("range"), "we.watched_date")
    g = query_one("SELECT name FROM genres WHERE id = %s::uuid", (genre_id,))
    rows = query_all(
        f"SELECT t.id, t.title, t.kind, t.year, t.poster_path, "
        f"  count(*) AS events, "
        f"  count(*) FILTER (WHERE we.item_kind='episode') AS episodes, "
        f"  max(we.watched_date) AS last_watched, "
        f"  COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"JOIN title_genres tg ON tg.title_id = t.id AND tg.genre_id = %s::uuid "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL" + rng +
        " GROUP BY t.id ORDER BY events DESC, last_watched DESC",
        (genre_id, ids),
    )
    return jsonify({
        "genre": g["name"] if g else None,
        "titles": [
            {"id": str(r["id"]), "title": r["title"], "kind": r["kind"], "year": r["year"],
             "poster": poster_url(r["poster_path"]), "events": int(r["events"]),
             "episodes": int(r["episodes"]), "hours": _hours(r["seconds"])}
            for r in rows
        ],
    })


@bp.get("/unfinished")
@require_perm("catalog.read")
def unfinished_titles():
    """Titles the scoped profile(s) have started but not finished — the
    precomputed "not yet finished" tracker. Series report watched/total episodes;
    sorted by most-recent activity. Reads the ``title_progress`` rollup so this
    stays fast without live-aggregating raw events."""
    ids = _ids()
    return jsonify([_unfinished_row(r) for r in _unfinished_query(ids)])


def _unfinished_query(ids):
    """Raw ``title_progress`` rows for the scoped profile(s), enriched with the
    runtime metadata needed to work out what's still left to watch. Shared by the
    ``/unfinished`` list and the summary "still to watch" tiles."""
    if not ids:
        return []
    return query_all(
        "SELECT t.id, t.title, t.kind, t.year, t.poster_path, "
        "  t.runtime_minutes AS title_runtime, "
        "  max(tp.watched_episodes) AS watched_episodes, "
        "  max(tp.total_episodes) AS total_episodes, "
        "  max(tp.last_activity_at) AS last_activity_at, "
        "  (SELECT avg(te.runtime_minutes) FROM title_episodes te "
        "     WHERE te.title_id = t.id AND te.runtime_minutes IS NOT NULL) AS avg_ep_runtime, "
        "  (SELECT max(ss.progress_percent) FROM scrobble_sessions ss "
        "     WHERE ss.title_id = t.id AND ss.user_id = ANY(%s::uuid[]) "
        "       AND ss.committed_at IS NULL) AS live_progress "
        "FROM title_progress tp JOIN titles t ON t.id = tp.title_id "
        "WHERE tp.user_id = ANY(%s::uuid[]) AND tp.status = 'in_progress' "
        "GROUP BY t.id ORDER BY max(tp.last_activity_at) DESC NULLS LAST, t.title",
        (ids, ids),
    )


def _unfinished_row(r) -> dict:
    """Shape one "still watching" row, computing what's left to watch:

    * **series** — remaining episodes (``total − watched``) and the time that
      represents (remaining × average episode runtime, falling back to the title
      runtime); percent = watched / total episodes.
    * **movie** — percent comes from the live (uncommitted) scrobble session; the
      minutes left are the title runtime scaled by the unwatched fraction.

    ``remaining_minutes`` is ``None`` when no runtime metadata is known yet, so
    the UI can omit it rather than show a misleading ``0``."""
    kind = r["kind"]
    watched = int(r["watched_episodes"] or 0)
    total = int(r["total_episodes"] or 0)
    title_rt = float(r["title_runtime"]) if r["title_runtime"] else None
    avg_ep = float(r["avg_ep_runtime"]) if r["avg_ep_runtime"] is not None else None

    if kind == "series":
        remaining_eps = max(0, total - watched)
        per_ep = avg_ep if avg_ep is not None else title_rt
        remaining_minutes = int(round(remaining_eps * per_ep)) if per_ep else None
        progress = int(round(watched / total * 100)) if total else 0
    else:  # movie
        prog = min(100.0, max(0.0, float(r["live_progress"] or 0)))
        progress = int(round(prog))
        remaining_eps = 0
        remaining_minutes = int(round(title_rt * (1 - prog / 100))) if title_rt else None

    return {
        "id": str(r["id"]), "title": r["title"], "kind": kind, "year": r["year"],
        "poster": poster_url(r["poster_path"]),
        "watched_episodes": watched, "total_episodes": total,
        "remaining_episodes": remaining_eps, "remaining_minutes": remaining_minutes,
        "progress": progress,
        "last_activity": r["last_activity_at"].isoformat() if r["last_activity_at"] else None,
    }
