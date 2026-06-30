"""Ingestion API: file imports, API-sync connections, providers list."""
from __future__ import annotations

import datetime as dt
import json

from flask import Blueprint, jsonify, request

from ..db import execute, query_all, query_one
from ..ingest import (ingest_events, prune_connection_libraries,
                      clear_connection_events, reset_all_data,
                      ingest_title_from_trakt, enqueue_trakt_title_syncs,
                      add_manual_movie, add_manual_episode, add_manual_season,
                      remove_manual_watch)
from ..ingest.adapters import get_adapter
from ..auth.sessions import current_user, require_perm
from ._common import household_user_ids

bp = Blueprint("ingest", __name__, url_prefix="/api")


# ── Providers catalog ──────────────────────────────────────────────────────

@bp.get("/providers")
@require_perm("catalog.read")
def list_providers():
    rows = query_all("SELECT id, key, name, ingest_type, adapter, color FROM providers ORDER BY name")
    out = []
    for r in rows:
        try:
            fields = get_adapter(r["adapter"]).config_fields
        except KeyError:
            fields = []
        out.append({
            "id": str(r["id"]), "key": r["key"], "name": r["name"],
            "ingest_type": r["ingest_type"], "adapter": r["adapter"], "color": r["color"],
            "config_fields": fields,
        })
    return jsonify(out)


def _provider_by_key(key: str):
    return query_one("SELECT * FROM providers WHERE key = %s", (key,))


def _target_user(default_user):
    """The household member the import is attributed to (default: self)."""
    uid = request.form.get("user_id") or (request.get_json(silent=True) or {}).get("user_id")
    if not uid:
        return str(default_user["id"])
    if str(uid) in [str(i) for i in household_user_ids()]:
        return str(uid)
    return None


# ── File import (Netflix CSV, generic CSV/JSON, …) ─────────────────────────

@bp.post("/ingest/import")
@require_perm("ingest.write")
def import_file():
    user = current_user()
    provider_key = request.form.get("provider")
    if not provider_key:
        return jsonify({"error": "provider required"}), 400
    provider = _provider_by_key(provider_key)
    if not provider:
        return jsonify({"error": "unknown provider"}), 400
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400

    target = _target_user(user)
    if not target:
        return jsonify({"error": "invalid target user"}), 400

    f = request.files["file"]
    content = f.read()
    try:
        adapter = get_adapter(provider["adapter"])
        events = adapter.import_file(content, f.filename or "")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"parse failed: {exc}"}), 400

    if not events:
        return jsonify({"error": "no events found in file", "inserted": 0}), 200

    summary = ingest_events(target, str(provider["id"]), None, events)
    execute("INSERT INTO audit_events (user_id, action, target, data) VALUES (%s,%s,%s,%s)",
            (user["id"], "import", provider_key, json.dumps(summary)))
    return jsonify({"ok": True, "provider": provider_key, "parsed": len(events), **summary})


# ── API-sync connections ───────────────────────────────────────────────────

@bp.get("/connections")
@require_perm("catalog.read")
def list_connections():
    user = current_user()
    rows = query_all(
        "SELECT sc.id, sc.name, sc.enabled, sc.last_sync_at, sc.last_status, sc.config, "
        "  p.key AS provider_key, p.name AS provider_name "
        "FROM source_connections sc JOIN providers p ON p.id = sc.provider_id "
        "WHERE sc.household_id = %s ORDER BY sc.created_at",
        (user["household_id"],),
    )
    out = []
    for r in rows:
        cfg = r["config"] or {}
        out.append({
            "id": str(r["id"]), "name": r["name"], "enabled": r["enabled"],
            "provider_key": r["provider_key"], "provider_name": r["provider_name"],
            "last_sync_at": r["last_sync_at"].isoformat() if r["last_sync_at"] else None,
            "last_status": r["last_status"],
            # Non-secret hints so the UI can drive the Trakt re-authorize flow.
            # The client_id is not sensitive; the secret/token are never exposed.
            "client_id": cfg.get("client_id"),
            "has_secret": bool(cfg.get("client_secret")),
            "has_token": bool(cfg.get("access_token")),
        })
    return jsonify(out)


@bp.get("/connections/<conn_id>/libraries")
@require_perm("ingest.write")
def connection_libraries(conn_id: str):
    """List libraries for an existing connection using its stored credentials, plus
    the currently selected subset — so the edit UI never has to handle secrets."""
    user = current_user()
    conn = query_one(
        "SELECT sc.config, p.adapter FROM source_connections sc "
        "JOIN providers p ON p.id = sc.provider_id "
        "WHERE sc.id = %s AND sc.household_id = %s",
        (conn_id, user["household_id"]),
    )
    if not conn:
        return jsonify({"error": "not found"}), 404
    config = conn["config"] or {}
    try:
        libraries = get_adapter(conn["adapter"]).list_libraries(config)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"could not load libraries: {exc}"}), 400
    selected = config.get("library_ids") or []
    if isinstance(selected, str):
        selected = [selected]
    return jsonify({"libraries": libraries, "selected": [str(s) for s in selected]})


@bp.post("/connections/libraries")
@require_perm("ingest.write")
def discover_libraries():
    """List the libraries available for a given provider + connection config,
    so the user can pick which ones to sync before saving the connection."""
    body = request.get_json(force=True, silent=True) or {}
    provider = _provider_by_key(body.get("provider", ""))
    if not provider:
        return jsonify({"error": "unknown provider"}), 400
    try:
        adapter = get_adapter(provider["adapter"])
        libraries = adapter.list_libraries(body.get("config") or {})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"could not load libraries: {exc}"}), 400
    return jsonify({"libraries": libraries})


@bp.post("/connections")
@require_perm("ingest.write")
def create_connection():
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    provider = _provider_by_key(body.get("provider", ""))
    if not provider:
        return jsonify({"error": "unknown provider"}), 400
    if provider["ingest_type"] != "api":
        return jsonify({"error": "provider does not support API sync"}), 400
    row = query_one(
        "INSERT INTO source_connections (household_id, provider_id, name, config) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (user["household_id"], provider["id"],
         body.get("name") or provider["name"], json.dumps(body.get("config") or {})),
    )
    return jsonify({"ok": True, "id": str(row["id"])})


@bp.put("/connections/<conn_id>")
@require_perm("ingest.write")
def update_connection(conn_id: str):
    """Edit a connection's name/config. When the selected library subset changes,
    reset the sync cursor (so the next sync re-pulls and re-tags) and immediately
    prune watch events that came from libraries that are no longer selected."""
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    conn = query_one(
        "SELECT sc.*, p.adapter FROM source_connections sc "
        "JOIN providers p ON p.id = sc.provider_id "
        "WHERE sc.id = %s AND sc.household_id = %s",
        (conn_id, user["household_id"]),
    )
    if not conn:
        return jsonify({"error": "not found"}), 404

    old_config = conn["config"] or {}
    patch = body.get("config")
    # Merge so the client can change just the library subset without resending secrets.
    new_config = {**old_config, **patch} if isinstance(patch, dict) else old_config
    name = body.get("name") or conn["name"]

    libraries_changed = (old_config.get("library_ids") or []) != (new_config.get("library_ids") or [])
    if libraries_changed:
        # Forget the cursor so a full resync re-pulls every event and tags its
        # library, then prune anything no longer in the selected subset right away.
        execute("UPDATE source_connections SET name=%s, config=%s, cursor='{}'::jsonb WHERE id=%s",
                (name, json.dumps(new_config), conn_id))
    else:
        execute("UPDATE source_connections SET name=%s, config=%s WHERE id=%s",
                (name, json.dumps(new_config), conn_id))

    pruned = 0
    spec = get_adapter(conn["adapter"]).library_prune_spec(new_config)
    if spec:
        pruned = prune_connection_libraries(conn_id, spec[0], spec[1])
    return jsonify({"ok": True, "pruned": pruned, "resync": libraries_changed})


@bp.post("/connections/<conn_id>/clear")
@require_perm("ingest.write")
def clear_connection(conn_id: str):
    """Wipe every watch event this connection imported, without removing the
    connection itself. The cursor is kept so the cleared history isn't re-pulled."""
    user = current_user()
    conn = query_one(
        "SELECT id FROM source_connections WHERE id = %s AND household_id = %s",
        (conn_id, user["household_id"]),
    )
    if not conn:
        return jsonify({"error": "not found"}), 404
    removed = clear_connection_events(conn_id)
    return jsonify({"ok": True, "removed": removed})


@bp.delete("/connections/<conn_id>")
@require_perm("ingest.write")
def delete_connection(conn_id: str):
    user = current_user()
    execute("DELETE FROM source_connections WHERE id = %s AND household_id = %s",
            (conn_id, user["household_id"]))
    return jsonify({"ok": True})


@bp.post("/connections/trakt/device-code")
@require_perm("ingest.write")
def trakt_device_code():
    """Start the Trakt device flow and return the short user code + device code.

    Used by both the add-connection form (client_id in the body) and the
    re-authorize panel of an existing connection (connection_id in the body, so
    the stored client_id is reused)."""
    from ..ingest.adapters.trakt import request_device_code
    body = request.get_json(force=True, silent=True) or {}
    client_id = (body.get("client_id") or "").strip()
    conn_id = (body.get("connection_id") or "").strip()
    if not client_id and conn_id:
        user = current_user()
        conn = query_one(
            "SELECT config FROM source_connections WHERE id = %s AND household_id = %s",
            (conn_id, user["household_id"]),
        )
        if conn:
            client_id = ((conn["config"] or {}).get("client_id") or "").strip()
    if not client_id:
        return jsonify({"error": "client_id is required"}), 400
    try:
        data = request_device_code(client_id)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **data})


@bp.post("/connections/trakt/device-token")
@require_perm("ingest.write")
def trakt_device_token():
    """Poll the Trakt device flow during the add-connection form.

    Returns the current status; on ``authorized`` the access/refresh tokens are
    returned so the frontend can store them into the new connection config."""
    from ..ingest.adapters.trakt import poll_device_token
    body = request.get_json(force=True, silent=True) or {}
    client_id = (body.get("client_id") or "").strip()
    client_secret = (body.get("client_secret") or "").strip()
    device_code = (body.get("device_code") or "").strip()
    if not (client_id and client_secret and device_code):
        return jsonify({"error": "client_id, client_secret and device_code are required"}), 400
    try:
        result = poll_device_token(client_id, client_secret, device_code)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@bp.post("/connections/<conn_id>/trakt-authorize")
@require_perm("ingest.write")
def trakt_authorize_existing(conn_id: str):
    """(Re)authorize an existing Trakt connection via the device flow.

    The frontend polls this with the device_code obtained from
    /connections/trakt/device-code. The stored client_id/secret are reused (the
    secret may be supplied in the body to fill one that was never saved). On the
    ``authorized`` status the new tokens are persisted on the connection — this is
    what fixes a connection stuck on 401/403 because it has no/expired token."""
    from ..ingest.adapters.trakt import poll_device_token
    user = current_user()
    conn = query_one(
        "SELECT sc.config FROM source_connections sc "
        "WHERE sc.id = %s AND sc.household_id = %s",
        (conn_id, user["household_id"]),
    )
    if not conn:
        return jsonify({"error": "not found"}), 404
    cfg = conn["config"] or {}
    body = request.get_json(force=True, silent=True) or {}
    client_id = (body.get("client_id") or cfg.get("client_id") or "").strip()
    client_secret = (body.get("client_secret") or cfg.get("client_secret") or "").strip()
    device_code = (body.get("device_code") or "").strip()
    if not (client_id and client_secret and device_code):
        return jsonify({"error": "client_id, client_secret and device_code are required"}), 400
    try:
        result = poll_device_token(client_id, client_secret, device_code)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    if result.get("status") == "authorized":
        tokens = {k: result[k] for k in ("access_token", "refresh_token", "token_expires_at")
                  if k in result}
        new_cfg = {**cfg, "client_id": client_id, "client_secret": client_secret,
                   **tokens, "username": cfg.get("username") or "me"}
        execute("UPDATE source_connections SET config = %s WHERE id = %s",
                (json.dumps(new_cfg), conn_id))
    return jsonify({"ok": True, "status": result.get("status")})


@bp.post("/connections/<conn_id>/sync")
@require_perm("ingest.write")
def sync_connection(conn_id: str):
    user = current_user()
    conn = query_one(
        "SELECT sc.*, p.adapter, p.id AS provider_id FROM source_connections sc "
        "JOIN providers p ON p.id = sc.provider_id "
        "WHERE sc.id = %s AND sc.household_id = %s",
        (conn_id, user["household_id"]),
    )
    if not conn:
        return jsonify({"error": "not found"}), 404

    target = _target_user(user)
    try:
        adapter = get_adapter(conn["adapter"])
        config = conn["config"] or {}
        new_config, changed = adapter.prepare_config(config)
        if changed:
            execute("UPDATE source_connections SET config = %s WHERE id = %s",
                    (json.dumps(new_config), conn_id))
            config = new_config
        events, new_cursor = adapter.fetch_history(config, conn["cursor"] or {})
    except Exception as exc:  # noqa: BLE001
        execute("UPDATE source_connections SET last_status = %s, last_sync_at = now() WHERE id = %s",
                (f"error: {exc}", conn_id))
        return jsonify({"error": f"sync failed: {exc}"}), 400

    summary = ingest_events(target, str(conn["provider_id"]), conn_id, events) if events else \
        {"inserted": 0, "duplicates": 0, "titles_created": 0}
    spec = adapter.library_prune_spec(config)
    if spec:
        summary["pruned"] = prune_connection_libraries(conn_id, spec[0], spec[1])
    # After a self-hosted (non-Trakt) sync, cross-check each touched series with
    # Trakt for episodes this source didn't know about.
    if conn["adapter"] != "trakt_api":
        enqueue_trakt_title_syncs(str(user["household_id"]), target,
                                  summary.get("series_title_ids"))
    execute(
        "UPDATE source_connections SET cursor = %s, last_status = %s, last_sync_at = now() WHERE id = %s",
        (json.dumps(new_cursor), f"ok: +{summary['inserted']}", conn_id),
    )
    return jsonify({"ok": True, "fetched": len(events), **summary})


@bp.post("/titles/<title_id>/trakt-sync")
@require_perm("ingest.write")
def trakt_sync_title(title_id: str):
    """Pull a single title's full Trakt watch history and ingest it.

    Attributed to the active profile (the clicking user, or ``user_id`` in the
    body). Used by the per-title "Sync with Trakt" button; dedup means only
    episodes not already known locally are added."""
    user = current_user()
    target = _target_user(user)
    if not target:
        return jsonify({"error": "invalid target user"}), 400
    try:
        result = ingest_title_from_trakt(target, str(user["household_id"]), title_id)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"trakt sync failed: {exc}"}), 400
    if result.get("status") == "no_trakt":
        return jsonify({"error": "no authorized Trakt connection"}), 400
    if result.get("status") == "no_title":
        return jsonify({"error": "title not found"}), 404
    return jsonify({"ok": True, **result})


# ── Manual watch entries (mark watched / add a date by hand) ────────────────

def _parse_watch_date(body: dict) -> dt.date:
    """Resolve the optional ?date=YYYY-MM-DD body field; defaults to today.
    Raises ValueError on a malformed date."""
    raw = (body.get("date") or "").strip()
    if not raw:
        return dt.date.today()
    return dt.date.fromisoformat(raw)


@bp.post("/titles/<title_id>/watch")
@require_perm("ingest.write")
def mark_title_watched(title_id: str):
    """Manually mark a movie watched (or add another watch date). Series use the
    per-episode/per-season endpoints instead. Attributed to the active profile."""
    user = current_user()
    target = _target_user(user)
    if not target:
        return jsonify({"error": "invalid target user"}), 400
    body = request.get_json(silent=True) or {}
    try:
        date = _parse_watch_date(body)
    except ValueError:
        return jsonify({"error": "invalid date"}), 400
    result = add_manual_movie(target, title_id, date)
    status = result.get("status")
    if status == "no_title":
        return jsonify({"error": "title not found"}), 404
    if status == "not_movie":
        return jsonify({"error": "use the episode or season endpoint for series"}), 400
    if status != "ok":
        return jsonify({"error": "could not mark watched"}), 400
    return jsonify({"ok": True, **result})


@bp.post("/episodes/<episode_id>/watch")
@require_perm("ingest.write")
def mark_episode_watched(episode_id: str):
    """Manually mark one episode watched (or add another watch date)."""
    user = current_user()
    target = _target_user(user)
    if not target:
        return jsonify({"error": "invalid target user"}), 400
    body = request.get_json(silent=True) or {}
    try:
        date = _parse_watch_date(body)
    except ValueError:
        return jsonify({"error": "invalid date"}), 400
    result = add_manual_episode(target, episode_id, date)
    if result.get("status") == "no_episode":
        return jsonify({"error": "episode not found"}), 404
    if result.get("status") != "ok":
        return jsonify({"error": "could not mark watched"}), 400
    return jsonify({"ok": True, **result})


@bp.post("/titles/<title_id>/seasons/<int:season>/watch")
@require_perm("ingest.write")
def mark_season_watched(title_id: str, season: int):
    """Manually mark every episode of one season watched on a date."""
    user = current_user()
    target = _target_user(user)
    if not target:
        return jsonify({"error": "invalid target user"}), 400
    body = request.get_json(silent=True) or {}
    try:
        date = _parse_watch_date(body)
    except ValueError:
        return jsonify({"error": "invalid date"}), 400
    result = add_manual_season(target, title_id, season, date)
    status = result.get("status")
    if status == "no_title":
        return jsonify({"error": "title not found"}), 404
    if status == "no_episodes":
        return jsonify({"error": "no episodes in this season"}), 404
    if status != "ok":
        return jsonify({"error": "could not mark watched"}), 400
    return jsonify({"ok": True, **result})


@bp.delete("/watch-events/<event_id>")
@require_perm("ingest.write")
def delete_watch_event(event_id: str):
    """Remove a single hand-entered watch date. Only ``manual`` events belonging
    to the current household can be deleted; imported/synced events are untouched."""
    if remove_manual_watch(household_user_ids(), event_id):
        return jsonify({"ok": True})
    return jsonify({"error": "not found or not removable"}), 404


@bp.post("/ingest/rebuild-agg")
@require_perm("settings.manage")
def rebuild_agg():
    execute("SELECT wv_rebuild_daily_agg()")
    return jsonify({"ok": True})


@bp.post("/ingest/reset-all")
@require_perm("settings.manage")
def reset_all():
    """Factory-reset: wipe all imported watch events and the entire catalog,
    starting from an empty database. Configured connections are kept; their
    cursors are reset so a fresh sync re-imports everything from scratch.
    Requires confirm=true in the body to avoid accidental wipes."""
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirmation required"}), 400
    removed = reset_all_data(reset_cursors=True)
    return jsonify({"ok": True, "removed": removed})
