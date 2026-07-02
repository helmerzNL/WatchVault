"""Live scrobbling receiver (Expert-mode feature).

Push endpoints accept real-time playback from Plex (native webhook) and a generic
JSON shape used by Home Assistant / AppleTV / Shortcuts, keep a now-playing view,
and let the household map incoming account names to profiles. Plex webhooks can't
set an Authorization header, so the Plex endpoint also accepts the token as a
`?token=` query parameter.
"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from ..db import connection, execute, query_all, query_one
from ..auth.sessions import current_user, require_perm, resolve_current_user
from ..auth.sessions import _from_api_token  # token resolution for ?token= path
from ..ingest import parse_plex_payload, parse_generic_payload, handle_scrobble
from ._common import household_user_ids, poster_url

bp = Blueprint("scrobble", __name__, url_prefix="/api/scrobble")

DEFAULT_THRESHOLD = 90


# ── Auth + settings helpers ─────────────────────────────────────────────────

def _push_user():
    """Resolve the household for a push: Authorization Bearer / session cookie,
    or a `?token=` query param (Plex). Requires the ingest.write permission."""
    user = resolve_current_user()
    if user is None:
        token = (request.args.get("token") or "").strip()
        if token.startswith("wvapi_"):
            user = _from_api_token(token)
    if user is None:
        return None
    perms = user.get("permissions", set())
    if "*" not in perms and "ingest.write" not in perms:
        return None
    return user


def _commit_threshold() -> float:
    row = query_one("SELECT data->>'scrobble_commit_threshold' AS t FROM app_settings WHERE id = 1")
    try:
        return float(row["t"]) if row and row["t"] is not None else DEFAULT_THRESHOLD
    except (ValueError, TypeError):
        return DEFAULT_THRESHOLD


# ── Push endpoints ──────────────────────────────────────────────────────────

@bp.post("/plex")
def plex_webhook():
    user = _push_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    # Plex posts multipart/form-data with a `payload` JSON field.
    raw = request.form.get("payload")
    if not raw and request.is_json:
        payload = request.get_json(silent=True) or {}
    else:
        try:
            payload = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            return jsonify({"error": "bad_payload"}), 400
    evt = parse_plex_payload(payload)
    if not evt:
        return jsonify({"ok": True, "ignored": True})
    result = handle_scrobble(str(user["household_id"]), evt, str(user["id"]),
                             _commit_threshold())
    return jsonify({"ok": True, **result})


@bp.post("/generic")
def generic_scrobble():
    user = _push_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    body = request.get_json(force=True, silent=True) or {}
    evt = parse_generic_payload(body)
    if not evt:
        return jsonify({"error": "bad_payload", "message": "title and event are required"}), 400
    result = handle_scrobble(str(user["household_id"]), evt, str(user["id"]),
                             _commit_threshold())
    return jsonify({"ok": True, **result})


# ── Now playing (UI) ────────────────────────────────────────────────────────

@bp.get("/now-playing")
@require_perm("ingest.write")
def now_playing():
    user = current_user()
    rows = query_all(
        "SELECT s.*, u.display_name AS profile_name, p.name AS provider_name, "
        "       p.key AS provider_key, p.color AS provider_color, t.poster_path "
        "FROM scrobble_sessions s "
        "LEFT JOIN users u ON u.id = s.user_id "
        "LEFT JOIN providers p ON p.id = s.provider_id "
        "LEFT JOIN titles t ON t.id = s.title_id "
        "WHERE s.household_id = %s AND s.state <> 'stopped' "
        # Hide a session that has been paused for more than 10 minutes: a `pause`
        # event refreshes updated_at, so an old updated_at while state='paused'
        # means it's been idle-on-pause too long. A later `resume` brings it back.
        "AND NOT (s.state = 'paused' "
        "         AND s.updated_at < now() - interval '10 minutes') "
        "ORDER BY s.updated_at DESC",
        (user["household_id"],),
    )
    return jsonify([
        {
            "id": str(r["id"]),
            "title_id": str(r["title_id"]) if r["title_id"] else None,
            "profile": r["profile_name"],
            "profile_id": str(r["user_id"]) if r["user_id"] else None,
            "account_label": r["account_label"],
            "source": r["source"],
            "provider": r["provider_name"],
            "provider_key": r["provider_key"],
            "provider_color": r["provider_color"],
            "title": r["raw_title"],
            "kind": r["kind"],
            "season": r["season"],
            "episode": r["episode"],
            "episode_name": r["episode_name"],
            "year": r["year"],
            "poster": poster_url(r["poster_path"]),
            "progress": float(r["progress_percent"] or 0),
            "state": r["state"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ])


# ── Manual season/episode picker (long-press on a Now-playing card) ─────────

def _session_for_household(session_id: str, household_id: str):
    return query_one(
        "SELECT * FROM scrobble_sessions WHERE id = %s AND household_id = %s",
        (session_id, household_id))


def _resolve_series_title(raw_title: str) -> tuple[str | None, int | None]:
    """Find (or create) the central *series* title for a show name and make sure
    TMDB enrichment is queued so its seasons/episodes get populated. SkyShowtime /
    Videoland arrive via the generic push as a bare movie title with no S/E, so the
    session's own title_id may point at a movie — the picker always works off the
    series title resolved from the show name. Returns (title_id, tmdb_id)."""
    from ..ingest.normalize import _resolve_title
    from ..ingest.scrobble import _maybe_enqueue_enrich
    name = (raw_title or "").strip()
    if not name:
        return None, None
    with connection() as conn, conn.cursor() as cur:
        title_id, _created = _resolve_title(cur, "series", name, None, None, {})
        _maybe_enqueue_enrich(cur, title_id)
        cur.execute("SELECT tmdb_id FROM titles WHERE id = %s", (title_id,))
        row = cur.fetchone()
        tmdb_id = row["tmdb_id"] if row else None
    return str(title_id), tmdb_id


@bp.get("/sessions/<session_id>/seasons")
@require_perm("ingest.write")
def session_seasons(session_id: str):
    """Available seasons + episodes (from TMDB, via title_episodes) for a live
    session's show, so the household member can correct which episode is playing."""
    user = current_user()
    session = _session_for_household(session_id, str(user["household_id"]))
    if not session:
        return jsonify({"error": "not_found"}), 404

    title_id, tmdb_id = _resolve_series_title(session["raw_title"])
    if not title_id:
        return jsonify({"seasons": [], "reason": "no_title"})

    eps = query_all(
        "SELECT season, episode, name FROM title_episodes "
        "WHERE title_id = %s AND episode IS NOT NULL "
        "ORDER BY season, episode", (title_id,))

    if not eps:
        # Episodes not fetched yet: enrichment (queued above) or a dedicated
        # episode backfill will fill them; tell the UI to show a loading state.
        from .search import _queue_episode_backfill
        if tmdb_id:
            _queue_episode_backfill(title_id)
        return jsonify({"seasons": [], "backfilling": True, "title_id": title_id})

    by_season: dict[int, list] = {}
    for e in eps:
        by_season.setdefault(e["season"] or 0, []).append(
            {"episode": e["episode"], "name": e["name"]})
    seasons = [
        {"season": s, "episodes": by_season[s], "episode_count": len(by_season[s])}
        for s in sorted(by_season)
    ]
    return jsonify({
        "title_id": title_id,
        "current": {"season": session["season"], "episode": session["episode"]},
        "seasons": seasons,
    })


@bp.post("/sessions/<session_id>/episode")
@require_perm("ingest.write")
def set_session_episode(session_id: str):
    """Lock a hand-picked season/episode onto a live session and bind it to the
    resolved series title. handle_scrobble then preserves this pick across ticks
    and commits it (not the raw payload) when the play finishes."""
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    try:
        season = int(body.get("season"))
        episode = int(body.get("episode"))
    except (TypeError, ValueError):
        return jsonify({"error": "bad_request", "message": "season and episode are required"}), 400

    session = _session_for_household(session_id, str(user["household_id"]))
    if not session:
        return jsonify({"error": "not_found"}), 404

    title_id, _tmdb = _resolve_series_title(session["raw_title"])
    if not title_id:
        return jsonify({"error": "no_title"}), 409

    ep = query_one(
        "SELECT id, name FROM title_episodes "
        "WHERE title_id = %s AND season = %s AND episode = %s",
        (title_id, season, episode))
    if not ep:
        return jsonify({"error": "unknown_episode"}), 404

    execute(
        "UPDATE scrobble_sessions SET title_id = %s, episode_id = %s, kind = 'series', "
        "  season = %s, episode = %s, episode_name = %s, manual_episode = true, "
        "  updated_at = now() WHERE id = %s AND household_id = %s",
        (title_id, ep["id"], season, episode, ep["name"], session_id,
         str(user["household_id"])))
    return jsonify({
        "ok": True, "title_id": title_id,
        "season": season, "episode": episode, "episode_name": ep["name"],
    })


# ── Persistent progress (title/series pages) ────────────────────────────────

@bp.get("/progress")
@require_perm("ingest.write")
def title_progress():
    """Latest *uncommitted* scrobble session per title, regardless of state
    (playing / paused / stopped). Drives the persistent progress bar on the
    film/series page: unlike now-playing this keeps returning the last known
    position after playback stops, so you can see what you're partway through.

    ``?title_id=`` narrows to one title (used by the detail page); omitted
    returns every in-progress title for the household. Only sessions that were
    never committed to a finished watch_event are returned (a finished play has
    ``committed_at`` set and is not 'in progress')."""
    user = current_user()
    title_id = (request.args.get("title_id") or "").strip() or None
    params: list = [user["household_id"]]
    where = "s.household_id = %s AND s.committed_at IS NULL AND s.title_id IS NOT NULL"
    if title_id:
        where += " AND s.title_id = %s"
        params.append(title_id)
    # One row per (title, season, episode): the most recently updated session.
    rows = query_all(
        "SELECT DISTINCT ON (s.title_id, COALESCE(s.season,0), COALESCE(s.episode,0)) "
        "       s.title_id, s.season, s.episode, s.episode_name, s.kind, "
        "       s.progress_percent, s.state, s.updated_at, s.user_id, "
        "       u.display_name AS profile_name "
        "FROM scrobble_sessions s LEFT JOIN users u ON u.id = s.user_id "
        "WHERE " + where +
        " ORDER BY s.title_id, COALESCE(s.season,0), COALESCE(s.episode,0), s.updated_at DESC",
        tuple(params),
    )
    return jsonify([
        {
            "title_id": str(r["title_id"]),
            "season": r["season"],
            "episode": r["episode"],
            "episode_name": r["episode_name"],
            "kind": r["kind"],
            "progress": float(r["progress_percent"] or 0),
            "state": r["state"],
            "profile": r["profile_name"],
            "profile_id": str(r["user_id"]) if r["user_id"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ])


# ── Account → profile mapping ───────────────────────────────────────────────

@bp.get("/account-map")
@require_perm("ingest.write")
def get_account_map():
    user = current_user()
    hid = user["household_id"]
    mappings = query_all(
        "SELECT m.source, m.account_label, m.user_id, u.display_name "
        "FROM scrobble_account_map m JOIN users u ON u.id = m.user_id "
        "WHERE m.household_id = %s ORDER BY m.source, m.account_label",
        (hid,),
    )
    mapped = {(m["source"], m["account_label"]) for m in mappings}
    # Incoming account labels seen on sessions that aren't mapped yet.
    seen = query_all(
        "SELECT DISTINCT source, account_label FROM scrobble_sessions "
        "WHERE household_id = %s AND account_label <> '' ORDER BY source, account_label",
        (hid,),
    )
    unmapped = [
        {"source": s["source"], "account_label": s["account_label"]}
        for s in seen if (s["source"], s["account_label"]) not in mapped
    ]
    return jsonify({
        "mappings": [
            {"source": m["source"], "account_label": m["account_label"],
             "user_id": str(m["user_id"]), "profile": m["display_name"]}
            for m in mappings
        ],
        "unmapped": unmapped,
    })


@bp.put("/account-map")
@require_perm("ingest.write")
def set_account_map():
    user = current_user()
    hid = user["household_id"]
    body = request.get_json(force=True, silent=True) or {}
    source = (body.get("source") or "").strip()
    account = (body.get("account_label") or "").strip()
    target = body.get("user_id")
    if not source or not account:
        return jsonify({"error": "source and account_label required"}), 400
    if target in (None, ""):
        execute("DELETE FROM scrobble_account_map "
                "WHERE household_id = %s AND source = %s AND account_label = %s",
                (hid, source, account))
        return jsonify({"ok": True, "deleted": True})
    # Guard: the target profile must belong to this household.
    if str(target) not in [str(u) for u in household_user_ids()]:
        return jsonify({"error": "invalid_profile"}), 400
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO scrobble_account_map (household_id, source, account_label, user_id) "
            "VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (household_id, source, account_label) DO UPDATE SET user_id = EXCLUDED.user_id",
            (hid, source, account, target),
        )
        # Back-fill the resolved profile onto live, not-yet-mapped sessions.
        cur.execute(
            "UPDATE scrobble_sessions SET user_id = %s "
            "WHERE household_id = %s AND source = %s AND account_label = %s "
            "AND committed_at IS NULL",
            (target, hid, source, account),
        )
    return jsonify({"ok": True})


# ── Settings (commit threshold) ─────────────────────────────────────────────

@bp.get("/settings")
@require_perm("ingest.write")
def get_settings():
    return jsonify({"commit_threshold": _commit_threshold()})


@bp.put("/settings")
@require_perm("settings.manage")
def put_settings():
    body = request.get_json(force=True, silent=True) or {}
    try:
        threshold = float(body.get("commit_threshold"))
    except (ValueError, TypeError):
        return jsonify({"error": "commit_threshold must be a number"}), 400
    threshold = max(1.0, min(100.0, threshold))
    execute(
        "UPDATE app_settings SET data = jsonb_set(data, '{scrobble_commit_threshold}', %s::jsonb, true) "
        "WHERE id = 1",
        (json.dumps(threshold),),
    )
    return jsonify({"ok": True, "commit_threshold": threshold})
