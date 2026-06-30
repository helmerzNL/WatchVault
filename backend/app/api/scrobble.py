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
        "       p.color AS provider_color, t.poster_path "
        "FROM scrobble_sessions s "
        "LEFT JOIN users u ON u.id = s.user_id "
        "LEFT JOIN providers p ON p.id = s.provider_id "
        "LEFT JOIN titles t ON t.tmdb_id = s.tmdb_id "
        "WHERE s.household_id = %s AND s.committed_at IS NULL AND s.state <> 'stopped' "
        "ORDER BY s.updated_at DESC",
        (user["household_id"],),
    )
    return jsonify([
        {
            "id": str(r["id"]),
            "profile": r["profile_name"],
            "profile_id": str(r["user_id"]) if r["user_id"] else None,
            "account_label": r["account_label"],
            "source": r["source"],
            "provider": r["provider_name"],
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
