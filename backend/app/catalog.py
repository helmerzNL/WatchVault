"""Shared catalog write-helpers used by both ingestion (source-native metadata)
and plugin enrichment (TMDB).

Design rules so the two paths compose predictably:

* **Scalar fields fill empty only** (``COALESCE(existing, new)``). Because source
  ingestion runs before the TMDB enrich job, the *source* stays authoritative
  for whatever it provides; TMDB only fills the gaps (posters, runtime, year,
  and any missing overview).
* **The per-language overview/biography maps are merged** (``||``) so every
  provider can contribute languages without clobbering the others.
* **Genres, cast and crew are additive** (upsert / ``ON CONFLICT DO NOTHING``).

Every field a provider touches is recorded in ``metadata_provenance`` so the UI
can show which source supplied which field.
"""
from __future__ import annotations

import json

from .genres import canonical_genre
from .util import normalize_text

# Languages we capture/translate content into (kept in sync with the frontend).
LANGS = ["en", "nl", "fr", "es", "it", "de"]


def _json(value) -> str:
    return json.dumps(value or {})


def set_provenance(cur, entity_type: str, entity_id: str, field: str,
                   source: str, value) -> None:
    cur.execute(
        "INSERT INTO metadata_provenance (entity_type, entity_id, field, source, value) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (entity_type, entity_id, field) DO UPDATE SET "
        "  source = EXCLUDED.source, value = EXCLUDED.value, created_at = now()",
        (entity_type, entity_id, field, source, json.dumps(value)),
    )


def upsert_genre(cur, name: str) -> int:
    # Normalize provider-localized/variant names ("Misdaad" -> "Crime") onto a
    # single canonical English row so the genre list has no language duplicates.
    cur.execute(
        "INSERT INTO genres (name) VALUES (%s) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (canonical_genre(name),),
    )
    return cur.fetchone()["id"]


def link_genre(cur, title_id: str, genre_id: int) -> None:
    cur.execute(
        "INSERT INTO title_genres (title_id, genre_id) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING",
        (title_id, genre_id),
    )


def upsert_person(cur, person: dict) -> str | None:
    """Resolve a person by tmdb_id, then by normalized name; create if new.
    Backfills tmdb_id/profile_path onto an existing name-matched row."""
    tmdb_id = person.get("tmdb_id")
    name = (person.get("name") or "").strip()
    if not name:
        return None
    if tmdb_id:
        cur.execute("SELECT id FROM people WHERE tmdb_id = %s", (tmdb_id,))
        row = cur.fetchone()
        if row:
            if person.get("profile_path"):
                cur.execute(
                    "UPDATE people SET profile_path = COALESCE(profile_path, %s) WHERE id = %s",
                    (person.get("profile_path"), row["id"]))
            return row["id"]
    cur.execute("SELECT id FROM people WHERE normalized_key = %s AND tmdb_id IS NULL",
                (normalize_text(name),))
    row = cur.fetchone()
    if row:
        if tmdb_id or person.get("profile_path"):
            cur.execute(
                "UPDATE people SET tmdb_id = COALESCE(%s, tmdb_id), "
                "  profile_path = COALESCE(profile_path, %s) WHERE id = %s",
                (tmdb_id, person.get("profile_path"), row["id"]))
        return row["id"]
    cur.execute(
        "INSERT INTO people (name, normalized_key, tmdb_id, profile_path) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (name, normalize_text(name), tmdb_id, person.get("profile_path")),
    )
    return cur.fetchone()["id"]


def link_person(cur, title_id: str, person: dict, role: str) -> None:
    pid = upsert_person(cur, person)
    if not pid:
        return
    if role == "cast":
        cur.execute(
            "INSERT INTO title_people (title_id, person_id, role, character, ord) "
            "VALUES (%s, %s, 'cast', %s, %s) "
            "ON CONFLICT (title_id, person_id, role) DO UPDATE SET "
            "  character = COALESCE(EXCLUDED.character, title_people.character), "
            "  ord = LEAST(title_people.ord, EXCLUDED.ord)",
            (title_id, pid, person.get("character"), person.get("ord", 999)))
    else:
        cur.execute(
            "INSERT INTO title_people (title_id, person_id, role, job, ord) "
            "VALUES (%s, %s, 'crew', %s, %s) "
            "ON CONFLICT (title_id, person_id, role) DO UPDATE SET "
            "  job = COALESCE(EXCLUDED.job, title_people.job)",
            (title_id, pid, person.get("job"), person.get("ord", 999)))


def apply_title_details(cur, title_id: str, details: dict, source: str) -> None:
    """Merge a provider's title details into the central model (fill-empty for
    scalars, merge for the overview map, additive for genres/cast/crew)."""
    overviews = {k: v for k, v in (details.get("overviews") or {}).items() if v}
    meta_update = {"updated_by": source}
    if details.get("networks"):
        meta_update["networks"] = details["networks"]
    if details.get("release_date"):
        meta_update["release_date"] = details["release_date"]
    cur.execute(
        "UPDATE titles SET "
        "  original_title  = COALESCE(original_title, %s), "
        "  year            = COALESCE(year, %s), "
        "  overview        = COALESCE(NULLIF(overview, ''), %s), "
        "  overviews       = overviews || %s::jsonb, "
        "  runtime_minutes = COALESCE(runtime_minutes, %s), "
        "  poster_path     = CASE WHEN manual_poster THEN poster_path "
        "                        ELSE COALESCE(poster_path, %s) END, "
        "  backdrop_path   = COALESCE(backdrop_path, %s), "
        "  tmdb_id         = COALESCE(tmdb_id, %s), "
        "  imdb_id         = COALESCE(imdb_id, %s), "
        "  external_ids    = external_ids || %s::jsonb, "
        "  metadata        = metadata || %s::jsonb, "
        "  enriched_at     = COALESCE(enriched_at, CASE WHEN %s THEN now() ELSE NULL END), "
        "  updated_at      = now() "
        "WHERE id = %s",
        (details.get("original_title"), details.get("year"),
         details.get("overview"), _json(overviews),
         details.get("runtime_minutes"), details.get("poster_path"),
         details.get("backdrop_path"), details.get("tmdb_id"),
         details.get("imdb_id"), _json(details.get("external_ids")),
         _json(meta_update), bool(details.get("authoritative")),
         title_id),
    )
    for fld in ("overview", "year", "runtime_minutes", "poster_path"):
        if details.get(fld) is not None:
            set_provenance(cur, "title", title_id, fld, source, details.get(fld))
    if overviews:
        set_provenance(cur, "title", title_id, "overviews", source, list(overviews.keys()))

    for gname in details.get("genres", []) or []:
        if gname:
            link_genre(cur, title_id, upsert_genre(cur, gname))
    for c in details.get("cast", []) or []:
        link_person(cur, title_id, c, "cast")
    for c in details.get("crew", []) or []:
        link_person(cur, title_id, c, "crew")


def dedupe_title_by_tmdb(cur, kind: str, tmdb_id, current_title_id: str) -> str:
    """Collapse every title that shares ``(kind, tmdb_id)`` into the oldest one.

    Used at enrich time: ``current_title_id`` is the title being enriched (it may
    not carry ``tmdb_id`` yet), and any *other* title already on that tmdb_id is a
    duplicate of the same show imported from a second source. The oldest row is
    kept as canonical (stable id), the rest are merged into it via the SQL
    ``wv_merge_titles`` helper. Returns the surviving canonical id so the caller
    can keep working on it.
    """
    if not tmdb_id:
        return current_title_id
    cur.execute(
        "SELECT id FROM titles WHERE kind = %s AND tmdb_id = %s",
        (kind, tmdb_id))
    candidates = [str(r["id"]) for r in cur.fetchall()]
    if current_title_id not in candidates:
        candidates.append(current_title_id)
    if len(candidates) < 2:
        return current_title_id
    cur.execute(
        "SELECT id FROM titles WHERE id = ANY(%s::uuid[]) ORDER BY created_at, id LIMIT 1",
        (candidates,))
    canonical = str(cur.fetchone()["id"])
    for dup in candidates:
        if dup != canonical:
            cur.execute("SELECT wv_merge_titles(%s::uuid, %s::uuid)", (canonical, dup))
    return canonical


def get_or_create_movie_by_tmdb(cur, tmdb_id, title: str, year: int | None = None) -> str:
    """Resolve a movie title by its TMDB id, creating a minimal row when absent.

    Used by the manual "add a cinema film" flow: the user picked an exact TMDB
    result, so we bind the title to that ``tmdb_id`` up front. Enrichment then
    fetches the full metadata for that exact record (no fuzzy search). The
    partial UNIQUE index on ``(kind, tmdb_id)`` guarantees one movie per tmdb_id,
    so a later sync of the same film reuses this row instead of duplicating it.
    """
    cur.execute("SELECT id FROM titles WHERE kind = 'movie' AND tmdb_id = %s",
                (tmdb_id,))
    row = cur.fetchone()
    if row:
        return str(row["id"])
    norm = normalize_text(title or "") or f"tmdb:{tmdb_id}"
    cur.execute(
        "INSERT INTO titles (kind, title, year, tmdb_id, normalized_key) "
        "VALUES ('movie', %s, %s, %s, %s) RETURNING id",
        ((title or "").strip() or f"TMDB {tmdb_id}", year, tmdb_id, norm))
    return str(cur.fetchone()["id"])


def upsert_episode(cur, title_id: str, ep: dict) -> None:
    """Fill/refresh one episode's metadata (fill-empty for scalars). Season/episode
    numbers are required; rows created during ingest (name only) get enriched here."""
    season = ep.get("season_number")
    number = ep.get("episode_number")
    if number is None or season is None:
        return
    cur.execute(
        "INSERT INTO title_episodes "
        "  (title_id, season, episode, name, overview, air_date, runtime_minutes, "
        "   still_path, tmdb_id, normalized_key) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (title_id, season, episode) DO UPDATE SET "
        "  name            = COALESCE(NULLIF(title_episodes.name, ''), EXCLUDED.name), "
        "  overview        = COALESCE(NULLIF(title_episodes.overview, ''), EXCLUDED.overview), "
        "  air_date        = COALESCE(title_episodes.air_date, EXCLUDED.air_date), "
        "  runtime_minutes = COALESCE(title_episodes.runtime_minutes, EXCLUDED.runtime_minutes), "
        "  still_path      = COALESCE(title_episodes.still_path, EXCLUDED.still_path), "
        "  tmdb_id         = COALESCE(title_episodes.tmdb_id, EXCLUDED.tmdb_id)",
        (title_id, int(season), int(number), ep.get("name"), ep.get("overview"),
         ep.get("air_date"), ep.get("runtime_minutes"), ep.get("still_path"),
         ep.get("tmdb_id"), normalize_text(ep.get("name") or "")),
    )


def apply_person_details(cur, person_id: str, details: dict, source: str) -> None:
    """Merge person bio details (fill-empty scalars, merge biography map)."""
    biographies = {k: v for k, v in (details.get("biographies") or {}).items() if v}
    cur.execute(
        "UPDATE people SET "
        "  name           = COALESCE(NULLIF(name, ''), %s), "
        "  tmdb_id        = COALESCE(tmdb_id, %s), "
        "  profile_path   = COALESCE(profile_path, %s), "
        "  biography      = COALESCE(NULLIF(biography, ''), %s), "
        "  biographies    = biographies || %s::jsonb, "
        "  birthday       = COALESCE(birthday, %s), "
        "  deathday       = COALESCE(deathday, %s), "
        "  place_of_birth = COALESCE(place_of_birth, %s), "
        "  known_for      = COALESCE(known_for, %s), "
        "  also_known_as  = CASE WHEN jsonb_array_length(also_known_as) = 0 "
        "                        THEN %s::jsonb ELSE also_known_as END, "
        "  metadata       = metadata || %s::jsonb, "
        "  enriched_at    = now() "
        "WHERE id = %s",
        (details.get("name"), details.get("tmdb_id"), details.get("profile_path"),
         details.get("biography"), _json(biographies), details.get("birthday"),
         details.get("deathday"), details.get("place_of_birth"),
         details.get("known_for"), json.dumps(details.get("also_known_as") or []),
         _json({"updated_by": source}), person_id),
    )
    for fld in ("biography", "birthday", "place_of_birth"):
        if details.get(fld) is not None:
            set_provenance(cur, "person", person_id, fld, source, str(details.get(fld)))
    if biographies:
        set_provenance(cur, "person", person_id, "biographies", source, list(biographies.keys()))
