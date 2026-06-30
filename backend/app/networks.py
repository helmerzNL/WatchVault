"""Re-attribute Trakt watch events to the actual streaming service.

Trakt's history never says *which* service a watch came from. TMDB does expose a
series' ``networks`` (the broadcaster/streamer it airs on, e.g. Netflix, Prime
Video, HBO Max, Apple TV+). We map that network to one of the household's
configured providers and move the Trakt-sourced ``watch_events`` onto it — so
the title page *and* every aggregate/statistic count those hours under the real
service instead of "Trakt".

Rules:
  * Only Trakt-sourced events are touched; Plex/Jellyfin/Netflix already *are*
    the service/library they came from.
  * A network that isn't in the catalogue — and movies, which have no network —
    fall back to the generic ``Other`` provider (localized "Overig" in the UI).
  * ``dedup_hash`` is intentionally left untouched: it was computed with the
    Trakt provider id, so a later Trakt sync recomputes the same hash and hits
    ``ON CONFLICT (dedup_hash) DO NOTHING`` — the event is never re-created.
  * Aggregates (``watch_daily_agg``) are keyed on ``provider_id``, so after the
    move we recompute both the old (Trakt) and new provider over the affected
    days via ``wv_recompute_agg_days``.
"""
from __future__ import annotations

import json

from .db import connection
from .plugins import runtime

# Normalized TMDB network name -> provider key in our catalogue. Resolution
# still checks the provider exists in the DB, so removed providers (e.g. nlziet)
# simply fall through to the generic provider.
_NETWORK_ALIASES = {
    "netflix": "netflix",
    "hbo": "hbomax",
    "hbo max": "hbomax",
    "max": "hbomax",
    "amazon": "prime",
    "amazon prime": "prime",
    "amazon prime video": "prime",
    "prime video": "prime",
    "prime": "prime",
    "disney+": "disney",
    "disney plus": "disney",
    "disney": "disney",
    "skyshowtime": "skyshowtime",
    "videoland": "videoland",
    "nlziet": "nlziet",
    "apple tv+": "appletv",
    "apple tv plus": "appletv",
    "apple tv": "appletv",
}


def _norm(name: str | None) -> str:
    return " ".join((name or "").strip().lower().split())


def resolve_network_provider(cur, networks: list[dict]):
    """Return ``(provider_id, provider_key)`` for the first network that maps to
    a provider present in the catalogue, else the generic provider."""
    for n in networks or []:
        key = _NETWORK_ALIASES.get(_norm(n.get("name")))
        if not key:
            continue
        cur.execute("SELECT id, key FROM providers WHERE key = %s", (key,))
        row = cur.fetchone()
        if row:
            return str(row["id"]), row["key"]
    cur.execute("SELECT id, key FROM providers WHERE key = 'generic'")
    row = cur.fetchone()
    return str(row["id"]), row["key"]


def _ensure_networks(title: dict) -> list[dict]:
    """Return a series' TMDB networks, lazily fetching + persisting them when
    missing.

    Titles enriched before networks were captured have no ``metadata.networks``,
    so every Trakt event would fall back to "Other" forever (lazy-enrich never
    re-runs once ``enriched_at`` is set). When the key is absent we fetch
    ``tv_details`` once and persist the result — even an empty list, to mark it
    fetched and avoid refetching on every backfill pass. A transient fetch
    failure persists nothing, so it is retried next time."""
    metadata = title.get("metadata") or {}
    if "networks" in metadata:
        return metadata.get("networks") or []
    if title.get("kind") != "series" or not title.get("tmdb_id"):
        return []

    details = None
    try:
        for pid in runtime.capability_providers("tv_details"):
            plugin = runtime.get_plugin(pid)
            if not getattr(plugin, "configured", True):
                continue
            details = plugin.tv_details(title["tmdb_id"])
            if details:
                break
    except Exception:  # noqa: BLE001 — re-attribution must not fail on a fetch error
        return []
    if details is None:
        return []  # provider unreachable — retry on a later pass

    networks = details.get("networks") or []
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE titles SET metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb "
            "WHERE id = %s",
            (json.dumps({"networks": networks}), str(title["id"])))
    return networks


def reattribute_title_trakt_events(title_id: str) -> dict:
    """Move a title's Trakt-sourced watch events onto the provider matching its
    TMDB network (or the generic provider), recomputing aggregates for every
    affected provider over the affected days.

    Trakt-origin events are identified by ``raw->>'source' = 'trakt'`` rather than
    their current provider, so events already moved onto a provider (e.g. the
    generic one from an earlier pass, before the network was known) are picked up
    again and re-attributed once ``metadata.networks`` is available. Events
    already on the resolved target are skipped, making this idempotent.

    Returns a status dict with the number of events ``moved`` and ``collapsed``
    (tombstoned because the same watch already exists on the target provider)."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, kind, tmdb_id, metadata FROM titles WHERE id = %s",
                    (title_id,))
        title = cur.fetchone()
    if not title:
        return {"status": "no_title"}

    networks = _ensure_networks(dict(title))

    with connection() as conn, conn.cursor() as cur:
        target_id, target_key = resolve_network_provider(cur, networks)

        cur.execute(
            "SELECT id, user_id, watched_date, episode_id, provider_id "
            "FROM watch_events "
            "WHERE title_id = %s AND raw->>'source' = 'trakt' AND deleted_at IS NULL "
            "  AND provider_id <> %s",
            (title_id, target_id))
        rows = cur.fetchall()
        if not rows:
            return {"status": "ok", "moved": 0, "collapsed": 0, "provider": target_key}

        # Capture the affected days per old provider (to drain its agg) and per
        # user (to refill the target's agg).
        affected_old: dict[tuple[str, str], set] = {}
        user_dates: dict[str, set] = {}
        for r in rows:
            affected_old.setdefault(
                (str(r["user_id"]), str(r["provider_id"])), set()).add(r["watched_date"])
            user_dates.setdefault(str(r["user_id"]), set()).add(r["watched_date"])

        moved = collapsed = 0
        for r in rows:
            # Collapse (tombstone) the Trakt event when a *real* provider event
            # already covers this watch, to avoid double counting. Other Trakt
            # events are excluded so two migrating events don't cancel each other.
            cur.execute(
                "SELECT 1 FROM watch_events "
                "WHERE user_id = %s AND title_id = %s AND provider_id = %s "
                "  AND watched_date = %s AND deleted_at IS NULL "
                "  AND episode_id IS NOT DISTINCT FROM %s AND id <> %s "
                "  AND COALESCE(raw->>'source', '') <> 'trakt' LIMIT 1",
                (str(r["user_id"]), title_id, target_id, r["watched_date"],
                 r["episode_id"], r["id"]))
            if cur.fetchone():
                cur.execute("UPDATE watch_events SET deleted_at = now() WHERE id = %s",
                            (r["id"],))
                collapsed += 1
                continue
            cur.execute("UPDATE watch_events SET provider_id = %s WHERE id = %s",
                        (target_id, r["id"]))
            moved += 1

        for (uid, old_pid), dates in affected_old.items():
            cur.execute("SELECT wv_recompute_agg_days(%s, %s, %s)", (uid, old_pid, list(dates)))
        for uid, dates in user_dates.items():
            cur.execute("SELECT wv_recompute_agg_days(%s, %s, %s)", (uid, target_id, list(dates)))

    return {"status": "ok", "moved": moved, "collapsed": collapsed,
            "provider": target_key}


def reattribute_all_trakt() -> dict:
    """Backfill: re-attribute every enriched title that still has Trakt events.

    Used as a one-time job on deploy so existing history is moved off "Trakt"
    onto the real services without waiting for each title to be re-enriched.
    Titles are found via ``raw->>'source' = 'trakt'`` so events already moved to
    the generic provider in an earlier (network-less) pass are revisited."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT we.title_id FROM watch_events we "
            "JOIN titles t ON t.id = we.title_id "
            "WHERE we.raw->>'source' = 'trakt' AND we.deleted_at IS NULL "
            "  AND t.enriched_at IS NOT NULL")
        title_ids = [str(r["title_id"]) for r in cur.fetchall()]

    titles = moved = collapsed = 0
    for tid in title_ids:
        res = reattribute_title_trakt_events(tid)
        if res.get("status") == "ok":
            titles += 1
            moved += res.get("moved", 0)
            collapsed += res.get("collapsed", 0)
    return {"status": "ok", "titles": titles, "moved": moved, "collapsed": collapsed}
