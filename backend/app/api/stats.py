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
    return jsonify({
        "totals": {
            "events": totals["events"], "movies": totals["movies"],
            "episodes": totals["episodes"], "titles": totals["titles"],
            "hours": _hours(totals["seconds"], 1),
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
    """Time spent per genre."""
    ids = _ids()
    rows = query_all(
        f"SELECT g.name, count(*) AS events, COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"JOIN title_genres tg ON tg.title_id = t.id "
        f"JOIN genres g ON g.id = tg.genre_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL "
        f"GROUP BY g.name ORDER BY seconds DESC",
        (ids,),
    )
    return jsonify([
        {"genre": r["name"], "events": int(r["events"]),
         "hours": _hours(r["seconds"])}
        for r in rows
    ])


@bp.get("/by-actor")
@require_perm("catalog.read")
def by_actor():
    """Time spent per actor (cast)."""
    ids = _ids()
    limit = min(int(request.args.get("limit", 30)), 100)
    rows = query_all(
        f"SELECT pe.id, pe.name, pe.profile_path, count(*) AS events, "
        f"  COALESCE(sum({EFF_SECONDS}),0) AS seconds "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"JOIN title_people tp ON tp.title_id = t.id AND tp.role = 'cast' "
        f"JOIN people pe ON pe.id = tp.person_id "
        f"WHERE we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL "
        f"GROUP BY pe.id ORDER BY seconds DESC LIMIT %s",
        (ids, limit),
    )
    return jsonify([
        {"id": str(r["id"]), "name": r["name"],
         "profile": poster_url(r["profile_path"], "w185"),
         "events": int(r["events"]), "hours": _hours(r["seconds"])}
        for r in rows
    ])
