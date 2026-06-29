"""People (cast & crew): a person page with a localized biography and every
title in the household catalog they're credited on, across all sources."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import query_all, query_one
from ..auth.sessions import require_perm
from ._common import household_user_ids, poster_url

bp = Blueprint("people", __name__, url_prefix="/api")


@bp.get("/people/<person_id>")
@require_perm("catalog.read")
def person_detail(person_id: str):
    lang = (request.args.get("lang") or "en").strip()[:2]
    p = query_one("SELECT * FROM people WHERE id = %s", (person_id,))
    if not p:
        return jsonify({"error": "not found"}), 404

    # Lazy bio enrichment on first open.
    if p.get("enriched_at") is None:
        try:
            from ..plugins import enrich_person, runtime
            if runtime.capability_providers("person_details"):
                enrich_person(person_id)
                p = query_one("SELECT * FROM people WHERE id = %s", (person_id,)) or p
        except Exception:  # noqa: BLE001 — best-effort
            pass

    ids = [str(i) for i in household_user_ids()]
    titles = query_all(
        "SELECT t.id, t.title, t.kind, t.year, t.poster_path, "
        "  bool_or(tp.role = 'cast') AS is_cast, "
        "  string_agg(DISTINCT NULLIF(tp.character, ''), ', ') AS characters, "
        "  string_agg(DISTINCT NULLIF(tp.job, ''), ', ') AS jobs, "
        "  (SELECT count(*) FROM watch_events we "
        "     WHERE we.title_id = t.id AND we.user_id = ANY(%s::uuid[]) "
        "       AND we.deleted_at IS NULL) AS events "
        "FROM title_people tp JOIN titles t ON t.id = tp.title_id "
        "WHERE tp.person_id = %s "
        "GROUP BY t.id ORDER BY t.year DESC NULLS LAST, t.title",
        (ids, person_id))

    biographies = p.get("biographies") or {}
    bio = biographies.get(lang) or p.get("biography") or biographies.get("en")
    return jsonify({
        "id": str(p["id"]), "name": p["name"],
        "photo": poster_url(p.get("profile_path"), "w342"),
        "biography": bio, "biographies": biographies,
        "birthday": p["birthday"].isoformat() if p.get("birthday") else None,
        "deathday": p["deathday"].isoformat() if p.get("deathday") else None,
        "place_of_birth": p.get("place_of_birth"),
        "known_for": p.get("known_for"),
        "tmdb_id": p.get("tmdb_id"),
        "titles": [
            {"id": str(t["id"]), "title": t["title"], "kind": t["kind"], "year": t["year"],
             "poster": poster_url(t["poster_path"]),
             "role": (t["characters"] if t["is_cast"] else t["jobs"]) or (
                 "Cast" if t["is_cast"] else "Crew"),
             "events": int(t["events"] or 0)}
            for t in titles
        ],
    })


@bp.post("/people/<person_id>/enrich")
@require_perm("ingest.write")
def enrich_person_now(person_id: str):
    from ..plugins import enrich_person
    return jsonify(enrich_person(person_id))


@bp.post("/titles/enrich-missing")
@require_perm("catalog.read")
def enrich_missing():
    """Queue background enrichment for titles not yet enriched. Used by the
    frontend to lazily fill metadata for posters scrolling into view."""
    body = request.get_json(force=True, silent=True) or {}
    raw_ids = body.get("ids") or []
    ids = [str(i) for i in raw_ids][:100]
    if not ids:
        return jsonify({"queued": 0})
    rows = query_all(
        "SELECT id FROM titles WHERE id = ANY(%s::uuid[]) AND enriched_at IS NULL", (ids,))
    queued = 0
    if rows:
        import json
        from ..db import connection
        with connection() as conn, conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    "INSERT INTO background_jobs (kind, payload) "
                    "SELECT 'enrich_title', %s::jsonb WHERE NOT EXISTS ("
                    "  SELECT 1 FROM background_jobs WHERE kind='enrich_title' "
                    "  AND payload->>'title_id' = %s AND status IN ('pending','running'))",
                    (json.dumps({"title_id": str(r["id"])}), str(r["id"])))
                queued += 1
    return jsonify({"queued": queued})
