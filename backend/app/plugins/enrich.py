"""Metadata enrichment: dispatch to capable plugins, merge results into the
central model via the shared catalog helpers, and record per-field provenance.

Two entry points:

* ``enrich_title(title_id)``  — posters/overview(s)/genres/cast/crew for a title.
* ``enrich_person(person_id)`` — biography (in every language), birth info, photo.
"""
from __future__ import annotations

import json
import re

from ..catalog import apply_person_details, apply_title_details, upsert_episode
from ..db import connection
from . import runtime


# ── Title matching ─────────────────────────────────────────────────────────
# Provider titles are noisy (Netflix keeps season/episode tails, some sources
# append a "(YEAR)", series/movies are classified heuristically and the watch
# year rarely equals the release year). A single year-constrained search on the
# raw string therefore misses a lot of titles. We instead try a small ordered
# set of progressively-relaxed queries and accept the first provider hit.

_YEAR_SUFFIX = re.compile(r"\s*[\(\[]\s*(?:19|20)\d{2}\s*[\)\]]\s*$")
_BRACKETED = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_TRAILING_NOISE = re.compile(
    r"[\s:–-]+\b(?:season|seizoen|series|s[ae]ison|temporada|stagione|staffel|"
    r"part|deel|parte|partie|teil|chapter|episode|aflevering|volume|vol|"
    r"limited series|miniseries|collection)\b.*$",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")


def _tidy(text: str) -> str:
    return _WS.sub(" ", (text or "")).strip(" \t-–:·|")


def _clean_variants(title: str) -> list[str]:
    """Progressively simpler query variants of a raw provider title."""
    base = _tidy(title)
    variants: list[str] = []

    def add(candidate: str) -> None:
        c = _tidy(candidate)
        if c and c.lower() != base.lower() and c not in variants:
            variants.append(c)

    add(_YEAR_SUFFIX.sub("", base))            # drop a trailing "(2021)"
    add(_TRAILING_NOISE.sub("", base))         # drop "… Season 2: …" tails
    add(_BRACKETED.sub("", base))              # drop any bracketed qualifier
    add(base.split(":")[0])                    # keep just the show name
    return variants


def build_search_attempts(title: str, year: int | None, kind: str) -> list[tuple[str, int | None, str]]:
    """Ordered (query, year, kind) attempts for matching a title against a
    provider. Same-kind queries are exhausted first (most reliable); the other
    media type is tried last to recover items that were misclassified at ingest."""
    base = _tidy(title)
    if not base:
        return []
    other = "movie" if kind == "series" else "series"
    attempts: list[tuple[str, int | None, str]] = []

    def add(query: str, yr: int | None, k: str) -> None:
        key = (query, yr, k)
        if query and key not in attempts:
            attempts.append(key)

    add(base, year, kind)
    if year:
        add(base, None, kind)
    for v in _clean_variants(base):
        add(v, year, kind)
        add(v, None, kind)
    # Last resort: the title may have been classified as the wrong media type.
    add(base, year, other)
    add(base, None, other)
    for v in _clean_variants(base):
        add(v, None, other)
    return attempts


def _find_match(plugin, title_row) -> tuple[int | None, str]:
    """Return (tmdb_id, matched_kind) for the first successful search attempt."""
    kind = title_row["kind"]
    for query, year, k in build_search_attempts(title_row["title"], title_row.get("year"), kind):
        try:
            results = plugin.search(query, year, k)
        except Exception:  # noqa: BLE001
            results = None
        if results:
            tmdb_id = results[0].get("id")
            if tmdb_id:
                return tmdb_id, k
    return None, kind


def _populate_episodes(plugin, title_id: str, tmdb_id: int, seasons: list) -> int:
    """Fetch every season's episode list from the provider and upsert them so the
    full series structure (watched or not) is browsable. Network calls happen
    first, then a single transaction writes the rows."""
    if not tmdb_id or not seasons or not hasattr(plugin, "tv_season"):
        return 0
    fetched: list[tuple[int, list]] = []
    for s in seasons:
        sn = s.get("season_number")
        if sn is None:
            continue
        season = plugin.tv_season(tmdb_id, sn)
        if season and season.get("episodes"):
            fetched.append((sn, season["episodes"]))
    if not fetched:
        return 0
    count = 0
    with connection() as conn, conn.cursor() as cur:
        for sn, episodes in fetched:
            for ep in episodes:
                ep["season_number"] = sn
                upsert_episode(cur, title_id, ep)
                count += 1
    return count


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
    matched_plugin = None
    matched_tmdb_id = None
    matched_kind = kind
    for pid in providers:
        try:
            plugin = runtime.get_plugin(pid)
        except Exception:  # noqa: BLE001
            continue
        if not getattr(plugin, "configured", True):
            continue
        tmdb_id = title.get("tmdb_id")
        fetch_kind = kind
        if not tmdb_id:
            tmdb_id, fetch_kind = _find_match(plugin, title)
        if not tmdb_id:
            continue
        details = (plugin.tv_details(tmdb_id) if fetch_kind == "series"
                   else plugin.movie_details(tmdb_id))
        if details:
            source = pid
            matched_plugin = plugin
            matched_tmdb_id = details.get("tmdb_id") or tmdb_id
            matched_kind = fetch_kind
            break

    if not details:
        # Mark as attempted so the worker/lazy-enrich doesn't retry on every open.
        with connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE titles SET enriched_at = COALESCE(enriched_at, now()) "
                        "WHERE id = %s", (title_id,))
        return {"status": "no_match"}

    with connection() as conn, conn.cursor() as cur:
        # Correct the media type when the match came from the other endpoint.
        if matched_kind != kind:
            cur.execute("UPDATE titles SET kind = %s, updated_at = now() WHERE id = %s",
                        (matched_kind, title_id))
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

    episodes = 0
    if matched_kind == "series":
        episodes = _populate_episodes(
            matched_plugin, title_id, matched_tmdb_id, details.get("seasons") or [])

    return {"status": "enriched", "source": source, "tmdb_id": details.get("tmdb_id"),
            "people_queued": len(person_ids), "episodes": episodes}


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
