"""Full search over watched titles — combinable filters on name, genre, actor,
platform and year, scoped to a profile or the whole household."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import query_all, query_one
from ..auth.sessions import require_perm
from ._common import EFF_SECONDS, poster_url, scope_user_ids

bp = Blueprint("search", __name__, url_prefix="/api/search")


@bp.get("")
@require_perm("catalog.read")
def search():
    ids = [str(i) for i in scope_user_ids()]
    if not ids:
        return jsonify({"results": [], "total": 0})

    q = (request.args.get("q") or "").strip()
    genre = (request.args.get("genre") or "").strip()
    actor = (request.args.get("actor") or "").strip()
    platform = (request.args.get("platform") or "").strip()
    year = request.args.get("year")
    kind = (request.args.get("kind") or "").strip()
    lang = (request.args.get("lang") or "en").strip()[:2]
    limit = min(int(request.args.get("limit", 60)), 200)
    offset = max(int(request.args.get("offset", 0)), 0)

    where = ["we.user_id = ANY(%s::uuid[])", "we.deleted_at IS NULL"]
    params: list = [ids]

    if q:
        where.append(
            "(t.title ILIKE %s OR EXISTS ("
            "  SELECT 1 FROM title_people tp JOIN people pe ON pe.id = tp.person_id "
            "  WHERE tp.title_id = t.id AND pe.name ILIKE %s) "
            " OR EXISTS ("
            "  SELECT 1 FROM title_genres tg JOIN genres g ON g.id = tg.genre_id "
            "  WHERE tg.title_id = t.id AND g.name ILIKE %s))"
        )
        like = f"%{q}%"
        params += [like, like, like]
    if genre:
        where.append("EXISTS (SELECT 1 FROM title_genres tg JOIN genres g ON g.id = tg.genre_id "
                     "WHERE tg.title_id = t.id AND g.name ILIKE %s)")
        params.append(f"%{genre}%")
    if actor:
        where.append("EXISTS (SELECT 1 FROM title_people tp JOIN people pe ON pe.id = tp.person_id "
                     "WHERE tp.title_id = t.id AND pe.name ILIKE %s)")
        params.append(f"%{actor}%")
    if platform:
        where.append("we.provider_id IN (SELECT id FROM providers WHERE key = %s OR name ILIKE %s)")
        params += [platform, f"%{platform}%"]
    if year:
        where.append("t.year = %s")
        params.append(int(year))
    if kind:
        where.append("t.kind = %s")
        params.append(kind)

    clause = " AND ".join(where)
    rows = query_all(
        f"SELECT t.id, t.title, t.kind, t.year, t.poster_path, t.overview, t.overviews, "
        f"  count(*) AS events, max(we.watched_date) AS last_watched, "
        f"  COALESCE(sum({EFF_SECONDS}),0) AS seconds, "
        f"  array_agg(DISTINCT p.name) AS platforms "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"JOIN providers p ON p.id = we.provider_id "
        f"WHERE {clause} "
        f"GROUP BY t.id ORDER BY last_watched DESC LIMIT %s OFFSET %s",
        params + [limit, offset],
    )
    total_row = query_all(
        f"SELECT count(DISTINCT t.id) AS n "
        f"FROM watch_events we JOIN titles t ON t.id = we.title_id "
        f"WHERE {clause}",
        params,
    )
    total = total_row[0]["n"] if total_row else 0

    return jsonify({
        "total": int(total),
        "results": [
            {"id": str(r["id"]), "title": r["title"], "kind": r["kind"], "year": r["year"],
             "poster": poster_url(r["poster_path"]),
             "overview": (r["overviews"] or {}).get(lang) or r["overview"],
             "events": int(r["events"]), "last_watched": r["last_watched"].isoformat(),
             "hours": round((r["seconds"] or 0) / 3600, 2),
             "platforms": [p for p in r["platforms"] if p]}
            for r in rows
        ],
    })


@bp.get("/title/<title_id>")
@require_perm("catalog.read")
def title_detail(title_id: str):
    ids = [str(i) for i in scope_user_ids()]
    lang = (request.args.get("lang") or "en").strip()[:2]

    t = query_one("SELECT * FROM titles WHERE id = %s", (title_id,))
    if not t:
        return jsonify({"error": "not found"}), 404

    # Lazy enrichment on open: fetch metadata the first time a title is viewed.
    if t.get("enriched_at") is None:
        try:
            from ..plugins import enrich_title, runtime
            detail_cap = "tv_details" if t["kind"] == "series" else "movie_details"
            if runtime.capability_providers(detail_cap):
                enrich_title(title_id)
                t = query_one("SELECT * FROM titles WHERE id = %s", (title_id,)) or t
        except Exception:  # noqa: BLE001 — enrichment is best-effort
            pass

    genres = query_all(
        "SELECT g.name FROM title_genres tg JOIN genres g ON g.id = tg.genre_id "
        "WHERE tg.title_id = %s ORDER BY g.name", (title_id,))
    cast = query_all(
        "SELECT pe.id, pe.name, pe.profile_path, tp.character FROM title_people tp "
        "JOIN people pe ON pe.id = tp.person_id WHERE tp.title_id = %s AND tp.role='cast' "
        "ORDER BY tp.ord LIMIT 20", (title_id,))
    crew = query_all(
        "SELECT pe.id, pe.name, pe.profile_path, tp.job FROM title_people tp "
        "JOIN people pe ON pe.id = tp.person_id "
        "WHERE tp.title_id = %s AND tp.role='crew' ORDER BY tp.ord", (title_id,))
    events = query_all(
        f"SELECT we.watched_date, we.item_kind, we.season, we.episode, we.raw_title, "
        f"  p.name AS platform, u.display_name AS who "
        f"FROM watch_events we JOIN providers p ON p.id = we.provider_id "
        f"JOIN users u ON u.id = we.user_id "
        f"WHERE we.title_id = %s AND we.user_id = ANY(%s::uuid[]) AND we.deleted_at IS NULL "
        f"ORDER BY we.watched_date DESC LIMIT 200",
        (title_id, ids))

    seasons = _series_seasons(title_id, t, ids) if t["kind"] == "series" else []

    overviews = t.get("overviews") or {}
    overview = overviews.get(lang) or t["overview"] or overviews.get("en")
    return jsonify({
        "id": str(t["id"]), "title": t["title"], "kind": t["kind"], "year": t["year"],
        "overview": overview, "overviews": overviews,
        "poster": poster_url(t["poster_path"]),
        "backdrop": poster_url(t["backdrop_path"], "w780"),
        "runtime_minutes": t["runtime_minutes"], "tmdb_id": t["tmdb_id"],
        "external_ids": t["external_ids"],
        "genres": [g["name"] for g in genres],
        "seasons": seasons,
        "cast": [{"id": str(c["id"]), "name": c["name"], "character": c["character"],
                  "profile": poster_url(c["profile_path"], "w185")} for c in cast],
        "crew": [{"id": str(c["id"]), "name": c["name"], "job": c["job"],
                  "profile": poster_url(c["profile_path"], "w185")} for c in crew],
        "events": [
            {"date": e["watched_date"].isoformat(), "kind": e["item_kind"],
             "season": e["season"], "episode": e["episode"], "raw_title": e["raw_title"],
             "platform": e["platform"], "who": e["who"]}
            for e in events
        ],
    })


def _series_seasons(title_id: str, t: dict, ids: list[str]) -> list[dict]:
    """Build the full season → episode tree with per-episode watched state for the
    scoped users. Queues a one-off background backfill if the series has a TMDB id
    but its episodes haven't been fetched yet (e.g. enriched before this feature)."""
    eps = query_all(
        "SELECT id, season, episode, name, overview, air_date, runtime_minutes, still_path "
        "FROM title_episodes WHERE title_id = %s ORDER BY season, episode", (title_id,))

    has_meta = any(e["still_path"] or e["overview"] or e["air_date"] for e in eps)
    if t.get("tmdb_id") and (not eps or not has_meta):
        _queue_episode_backfill(title_id)

    watched = query_all(
        "SELECT episode_id, season, episode, max(watched_date) AS last "
        "FROM watch_events WHERE title_id = %s AND user_id = ANY(%s::uuid[]) "
        "AND deleted_at IS NULL AND item_kind = 'episode' "
        "GROUP BY episode_id, season, episode", (title_id, ids))
    watched_ids: dict[str, str] = {}
    watched_se: dict[tuple, str] = {}
    for w in watched:
        last = w["last"].isoformat() if w["last"] else None
        if w["episode_id"]:
            watched_ids[str(w["episode_id"])] = last
        if w["episode"] is not None:
            watched_se[(w["season"] or 0, w["episode"])] = last

    by_season: dict[int, list] = {}
    for e in eps:
        last = watched_ids.get(str(e["id"])) or watched_se.get((e["season"] or 0, e["episode"]))
        by_season.setdefault(e["season"] or 0, []).append({
            "id": str(e["id"]), "episode": e["episode"], "name": e["name"],
            "overview": e["overview"],
            "air_date": e["air_date"].isoformat() if e["air_date"] else None,
            "runtime_minutes": e["runtime_minutes"],
            "still": poster_url(e["still_path"], "w300"),
            "watched": last is not None, "last_watched": last,
        })

    seasons = []
    for s in sorted(by_season):
        items = by_season[s]
        watched_n = sum(1 for i in items if i["watched"])
        seasons.append({
            "season": s, "episodes": items,
            "episode_count": len(items), "watched_count": watched_n,
        })
    return seasons


def _queue_episode_backfill(title_id: str) -> None:
    from ..db import connection
    import json as _json
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO background_jobs (kind, payload) "
                "SELECT 'enrich_title', %s::jsonb WHERE NOT EXISTS ("
                "  SELECT 1 FROM background_jobs WHERE kind = 'enrich_title' "
                "  AND payload->>'title_id' = %s AND status = 'pending')",
                (_json.dumps({"title_id": str(title_id)}), str(title_id)))
    except Exception:  # noqa: BLE001 — backfill is best-effort
        pass
