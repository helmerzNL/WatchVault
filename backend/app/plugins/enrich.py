"""Metadata enrichment: dispatch to capable plugins, merge results into the
central model via the shared catalog helpers, and record per-field provenance.

Two entry points:

* ``enrich_title(title_id)``  — posters/overview(s)/genres/cast/crew for a title.
* ``enrich_person(person_id)`` — biography (in every language), birth info, photo.
"""
from __future__ import annotations

import json

from ..catalog import apply_person_details, apply_title_details
from ..db import connection
from . import runtime


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
        apply_title_details(cur, title_id, details, source)
        # queue lazy person enrichment for linked people that have a tmdb id
        cur.execute(
            "SELECT DISTINCT pe.id FROM title_people tp JOIN people pe ON pe.id = tp.person_id "
            "WHERE tp.title_id = %s AND pe.tmdb_id IS NOT NULL AND pe.enriched_at IS NULL",
            (title_id,))
        person_ids = [str(r["id"]) for r in cur.fetchall()]
        for pid_ in person_ids:
            cur.execute(
                "INSERT INTO background_jobs (kind, payload) VALUES ('enrich_person', %s::jsonb)",
                (json.dumps({"person_id": pid_}),))

    return {"status": "enriched", "source": source, "tmdb_id": details.get("tmdb_id"),
            "people_queued": len(person_ids)}


def enrich_person(person_id: str) -> dict:
    """Enrich a person's biography (all languages) + birth info via TMDB."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, tmdb_id FROM people WHERE id = %s", (person_id,))
        person = cur.fetchone()
    if not person:
        return {"status": "not_found"}

    providers = runtime.capability_providers("person_details")
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
        tmdb_id = person.get("tmdb_id")
        if not tmdb_id and hasattr(plugin, "search_person"):
            results = plugin.search_person(person["name"])
            if results:
                tmdb_id = results[0].get("id")
        if not tmdb_id:
            continue
        details = plugin.person_details(tmdb_id)
        if details:
            source = pid
            break

    if not details:
        # mark as attempted so we don't retry on every page open
        with connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE people SET enriched_at = now() WHERE id = %s", (person_id,))
        return {"status": "no_match"}

    with connection() as conn, conn.cursor() as cur:
        apply_person_details(cur, person_id, details, source)
    return {"status": "enriched", "source": source, "tmdb_id": details.get("tmdb_id")}
