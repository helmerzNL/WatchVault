"""Re-attribute Trakt watch events to the actual streaming service.

Trakt's history never says *which* service a watch came from. TMDB does expose a
series' ``networks`` (the broadcaster/streamer it airs on, e.g. Netflix, Prime
Video, HBO Max, Apple TV+). We map that network to one of the household's
configured providers and move the Trakt-sourced ``watch_events`` onto it — so
the title page *and* every aggregate/statistic count those hours under the real
service instead of "Trakt".

A title can also carry a manual **platform override** (``titles.platform_override_
provider_id``): when set it wins over the network guess and the title's soft
events are forced onto that provider (e.g. "Cinema").

Rules:
  * Only *soft* events are ever moved — Trakt-sourced and manual ones. Real
    digital syncs/imports (Plex, Jellyfin, Netflix CSV, generic CSV) already
    *are* the service/library they came from and are never re-attributed.
  * Target per event: an override wins for both; otherwise a Trakt event goes to
    its TMDB network (or the generic ``Other`` provider for movies / unknown
    networks) and a manual event stays on the ``manual`` provider.
  * ``dedup_hash`` is intentionally left untouched: it was computed with the
    original provider id, so a later sync recomputes the same hash and hits
    ``ON CONFLICT (dedup_hash) DO NOTHING`` — the event is never re-created.
  * Aggregates (``watch_daily_agg``) are keyed on ``provider_id``, so after the
    move we recompute both the old and the new provider over the affected days
    via ``wv_recompute_agg_days``.
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


# Event ``raw->>'source'`` values that may be re-attributed. Everything else
# (plex, jellyfin, netflix_csv, generic CSV imports) is a real digital sync and
# is left on its own provider.
MOVABLE_SOURCES = ("trakt", "manual")


def _desired_provider(source: str | None, override_id: str | None,
                      network_id: str | None, manual_id: str | None) -> str | None:
    """Target provider id for one event, or ``None`` if it must not be moved.

    An override wins for any movable event. Otherwise a Trakt event resolves to
    its TMDB network and a manual event stays on the ``manual`` provider."""
    if source not in MOVABLE_SOURCES:
        return None
    if override_id:
        return override_id
    if source == "manual":
        return manual_id
    return network_id  # trakt


def _provider_id_by_key(cur, key: str) -> str | None:
    cur.execute("SELECT id FROM providers WHERE key = %s", (key,))
    row = cur.fetchone()
    return str(row["id"]) if row else None


def _attribution_reason(title: dict, override_id: str | None,
                        networks: list[dict], network_key: str | None) -> str:
    """Explain *why* a title's soft events land where they do — for the
    attribution log. Mirrors the resolution order in
    :func:`reattribute_title_events`."""
    if override_id:
        return "override"
    if network_key and network_key != "generic":
        return "network_matched"
    # Fell through to the generic ("Other") provider — classify the cause.
    if title.get("kind") != "series":
        return "movie_no_networks"
    if not title.get("tmdb_id"):
        return "not_enriched"
    metadata = title.get("metadata") or {}
    if "networks" not in metadata and not title.get("enriched_at"):
        return "not_enriched"
    if networks:
        return "network_unmapped"
    return "no_networks"


def _raw_network_names(networks: list[dict]) -> list[str]:
    return [n.get("name") for n in (networks or []) if n.get("name")]


def _log_attribution(title: dict, provider_key: str | None, reason: str,
                     networks: list[dict], events: int, moved: int,
                     collapsed: int) -> None:
    """Upsert the latest attribution decision and append a history row when the
    decision changed (different provider/reason) or events actually moved.

    Best-effort: any failure here is swallowed so it can never break the
    re-attribution itself."""
    title_id = str(title["id"])
    names = _raw_network_names(networks)
    networks_json = json.dumps(names)
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT provider_key, reason FROM attribution_log WHERE title_id = %s",
                        (title_id,))
            prev = cur.fetchone()
            changed = (prev is None or prev["provider_key"] != provider_key
                       or prev["reason"] != reason or moved or collapsed)
            cur.execute(
                "INSERT INTO attribution_log "
                "  (title_id, title, kind, provider_key, reason, networks, events, "
                "   moved, collapsed, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, now()) "
                "ON CONFLICT (title_id) DO UPDATE SET "
                "  title = EXCLUDED.title, kind = EXCLUDED.kind, "
                "  provider_key = EXCLUDED.provider_key, reason = EXCLUDED.reason, "
                "  networks = EXCLUDED.networks, events = EXCLUDED.events, "
                "  moved = EXCLUDED.moved, collapsed = EXCLUDED.collapsed, "
                "  updated_at = now()",
                (title_id, title.get("title") or "", title.get("kind"),
                 provider_key, reason, networks_json, events, moved, collapsed))
            if changed:
                cur.execute(
                    "INSERT INTO attribution_log_history "
                    "  (title_id, provider_key, reason, networks, moved, collapsed) "
                    "VALUES (%s, %s, %s, %s::jsonb, %s, %s)",
                    (title_id, provider_key, reason, networks_json, moved, collapsed))
    except Exception:  # noqa: BLE001 — logging must never break attribution
        pass


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


def reattribute_title_events(title_id: str) -> dict:
    """Move a title's *soft* (Trakt + manual) watch events onto their correct
    provider, recomputing aggregates for every affected provider over the
    affected days.

    Target per event (see :func:`_desired_provider`): a title-level platform
    override wins; otherwise Trakt events go to their TMDB network (or the generic
    provider) and manual events stay on the ``manual`` provider. Real digital
    syncs (Plex/Jellyfin/Netflix CSV/generic imports) are never touched.

    Soft events are selected by ``raw->>'source'`` rather than their current
    provider, so events already moved in an earlier pass are revisited and
    re-targeted (e.g. when an override is set or cleared, or once
    ``metadata.networks`` becomes available). Events already on their desired
    provider are skipped, making this idempotent.

    Returns a status dict with the number of events ``moved`` and ``collapsed``
    (tombstoned because the same watch already exists on the target provider)."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, kind, tmdb_id, metadata, enriched_at, "
            "  platform_override_provider_id "
            "FROM titles WHERE id = %s", (title_id,))
        title = cur.fetchone()
    if not title:
        return {"status": "no_title"}

    override_id = title["platform_override_provider_id"]
    override_id = str(override_id) if override_id else None
    # The TMDB network is only needed when there is no override and the title has
    # Trakt events; fetching it lazily here keeps backfills cheap for overrides.
    networks = [] if override_id else _ensure_networks(dict(title))

    with connection() as conn, conn.cursor() as cur:
        network_id, network_key = resolve_network_provider(cur, networks)
        manual_id = _provider_id_by_key(cur, "manual")
        primary_key = None
        if override_id:
            cur.execute("SELECT key FROM providers WHERE id = %s", (override_id,))
            r = cur.fetchone()
            primary_key = r["key"] if r else None
        else:
            primary_key = network_key

        reason = _attribution_reason(dict(title), override_id, networks, network_key)

        placeholders = ", ".join(["%s"] * len(MOVABLE_SOURCES))
        cur.execute(
            "SELECT id, user_id, watched_date, episode_id, provider_id, "
            "  raw->>'source' AS source "
            "FROM watch_events "
            f"WHERE title_id = %s AND raw->>'source' IN ({placeholders}) "
            "  AND deleted_at IS NULL",
            (title_id, *MOVABLE_SOURCES))
        rows = cur.fetchall()
        if not rows:
            return {"status": "ok", "moved": 0, "collapsed": 0, "provider": primary_key}

        # (user_id, provider_id) -> affected dates, for every provider we drain
        # (old) or fill (new) so the recompute touches exactly the right rollups.
        recompute: dict[tuple[str, str], set] = {}

        def _mark(uid: str, pid: str, date):
            recompute.setdefault((uid, pid), set()).add(date)

        moved = collapsed = 0
        for r in rows:
            desired = _desired_provider(r["source"], override_id, network_id, manual_id)
            if not desired or str(r["provider_id"]) == desired:
                continue
            uid = str(r["user_id"])
            # Collapse (tombstone) the soft event when a *real* (non-movable)
            # provider event already covers this watch, to avoid double counting.
            # Other soft events are excluded so two migrating events don't cancel.
            cur.execute(
                "SELECT 1 FROM watch_events "
                "WHERE user_id = %s AND title_id = %s AND provider_id = %s "
                "  AND watched_date = %s AND deleted_at IS NULL "
                "  AND episode_id IS NOT DISTINCT FROM %s AND id <> %s "
                f"  AND COALESCE(raw->>'source', '') NOT IN ({placeholders}) LIMIT 1",
                (uid, title_id, desired, r["watched_date"],
                 r["episode_id"], r["id"], *MOVABLE_SOURCES))
            if cur.fetchone():
                cur.execute("UPDATE watch_events SET deleted_at = now() WHERE id = %s",
                            (r["id"],))
                _mark(uid, str(r["provider_id"]), r["watched_date"])
                collapsed += 1
                continue
            cur.execute("UPDATE watch_events SET provider_id = %s WHERE id = %s",
                        (desired, r["id"]))
            _mark(uid, str(r["provider_id"]), r["watched_date"])
            _mark(uid, desired, r["watched_date"])
            moved += 1

        for (uid, pid), dates in recompute.items():
            cur.execute("SELECT wv_recompute_agg_days(%s, %s, %s)", (uid, pid, list(dates)))

    _log_attribution(dict(title), primary_key, reason, networks,
                     len(rows), moved, collapsed)
    return {"status": "ok", "moved": moved, "collapsed": collapsed,
            "provider": primary_key}


def reattribute_all() -> dict:
    """Backfill: re-attribute every title that has soft events to move.

    Used as a one-time job on deploy so existing history is moved off "Trakt"
    onto the real services (and any platform overrides are applied) without
    waiting for each title to be re-enriched or re-synced. Titles are found via
    their Trakt events (enriched, so a network is resolvable) or because they
    carry a platform override (whose manual/Trakt events must follow it)."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT we.title_id FROM watch_events we "
            "JOIN titles t ON t.id = we.title_id "
            "WHERE we.deleted_at IS NULL AND ("
            "    (we.raw->>'source' = 'trakt' AND t.enriched_at IS NOT NULL) "
            "    OR t.platform_override_provider_id IS NOT NULL)")
        title_ids = [str(r["title_id"]) for r in cur.fetchall()]

    titles = moved = collapsed = 0
    for tid in title_ids:
        res = reattribute_title_events(tid)
        if res.get("status") == "ok":
            titles += 1
            moved += res.get("moved", 0)
            collapsed += res.get("collapsed", 0)
    return {"status": "ok", "titles": titles, "moved": moved, "collapsed": collapsed}


# Backwards-compatible aliases (older imports / job dispatch).
reattribute_title_trakt_events = reattribute_title_events
reattribute_all_trakt = reattribute_all
