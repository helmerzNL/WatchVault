"""Metadata enrichment: dispatch to capable plugins, merge results into a
title, and record per-field provenance (which plugin contributed which field)."""
from __future__ import annotations

import json

from ..db import connection
from ..util import normalize_text
from . import runtime


def _provenance(cur, entity_id, field, source, value):
    cur.execute(
        "INSERT INTO metadata_provenance (entity_type, entity_id, field, source, value) "
        "VALUES ('title', %s, %s, %s, %s) "
        "ON CONFLICT (entity_type, entity_id, field) DO UPDATE SET "
        "source = EXCLUDED.source, value = EXCLUDED.value, created_at = now()",
        (entity_id, field, source, json.dumps(value)),
    )


def _upsert_genre(cur, name: str) -> int:
    cur.execute(
        "INSERT INTO genres (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
        "RETURNING id",
        (name,),
    )
    return cur.fetchone()["id"]


def _upsert_person(cur, person: dict) -> str:
    tmdb_id = person.get("tmdb_id")
    name = (person.get("name") or "").strip()
    if not name:
        return None
    if tmdb_id:
        cur.execute("SELECT id FROM people WHERE tmdb_id = %s", (tmdb_id,))
        row = cur.fetchone()
        if row:
            return row["id"]
    cur.execute("SELECT id FROM people WHERE normalized_key = %s AND tmdb_id IS NULL",
                (normalize_text(name),))
    row = cur.fetchone()
    if row:
        if tmdb_id:
            cur.execute("UPDATE people SET tmdb_id = %s, profile_path = %s WHERE id = %s",
                        (tmdb_id, person.get("profile_path"), row["id"]))
        return row["id"]
    cur.execute(
        "INSERT INTO people (name, normalized_key, tmdb_id, profile_path) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (name, normalize_text(name), tmdb_id, person.get("profile_path")),
    )
    return cur.fetchone()["id"]


def enrich_title(title_id: str) -> dict:
    """Enrich a single title via the TMDB plugin (and any other providers)."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM titles WHERE id = %s", (title_id,))
        title = cur.fetchone()
        if not title:
            return {"status": "not_found"}

    kind = title["kind"]
    detail_cap = "tv_details" if kind == "series" else "movie_details"
    providers = runtime.capability_providers(detail_cap)
    if not providers:
        return {"status": "no_provider"}

    details = None
    source = None
    for pid in providers:
        try:
            plugin = runtime.get_plugin(pid)
        except Exception:  # noqa: BLE001
            continue
        if not getattr(plugin, "configured", True):
            continue
        tmdb_id = title.get("tmdb_id")
        if not tmdb_id:
            results = plugin.search(title["title"], title.get("year"), kind)
            if results:
                tmdb_id = results[0].get("id")
        if not tmdb_id:
            continue
        details = (plugin.tv_details(tmdb_id) if kind == "series"
                   else plugin.movie_details(tmdb_id))
        if details:
            source = pid
            break

    if not details:
        return {"status": "no_match"}

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE titles SET "
            "  title = COALESCE(%s, title), original_title = %s, year = COALESCE(%s, year), "
            "  overview = %s, runtime_minutes = COALESCE(%s, runtime_minutes), "
            "  poster_path = %s, backdrop_path = %s, tmdb_id = %s, imdb_id = %s, "
            "  metadata = metadata || %s::jsonb, enriched_at = now(), updated_at = now() "
            "WHERE id = %s",
            (details.get("title"), details.get("original_title"), details.get("year"),
             details.get("overview"), details.get("runtime_minutes"),
             details.get("poster_path"), details.get("backdrop_path"),
             details.get("tmdb_id"), details.get("imdb_id"),
             json.dumps({"enriched_by": source}), title_id),
        )
        for fld in ("poster_path", "overview", "year", "runtime_minutes"):
            if details.get(fld) is not None:
                _provenance(cur, title_id, fld, source, details.get(fld))

        # genres
        for gname in details.get("genres", []):
            if gname:
                gid = _upsert_genre(cur, gname)
                cur.execute(
                    "INSERT INTO title_genres (title_id, genre_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING", (title_id, gid))

        # cast + crew
        for c in details.get("cast", []):
            pid_ = _upsert_person(cur, c)
            if pid_:
                cur.execute(
                    "INSERT INTO title_people (title_id, person_id, role, character, ord) "
                    "VALUES (%s, %s, 'cast', %s, %s) ON CONFLICT (title_id, person_id, role) "
                    "DO UPDATE SET character = EXCLUDED.character, ord = EXCLUDED.ord",
                    (title_id, pid_, c.get("character"), c.get("ord", 999)))
        for c in details.get("crew", []):
            pid_ = _upsert_person(cur, c)
            if pid_:
                cur.execute(
                    "INSERT INTO title_people (title_id, person_id, role, job) "
                    "VALUES (%s, %s, 'crew', %s) ON CONFLICT (title_id, person_id, role) "
                    "DO UPDATE SET job = EXCLUDED.job",
                    (title_id, pid_, c.get("job")))

    return {"status": "enriched", "source": source, "tmdb_id": details.get("tmdb_id")}
