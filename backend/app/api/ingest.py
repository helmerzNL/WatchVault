"""Ingestion API: file imports, API-sync connections, providers list."""
from __future__ import annotations

import datetime as dt
import json
import logging

from flask import Blueprint, jsonify, request

from ..db import connection, execute, query_all, query_one
from ..ingest import (ingest_events, prune_connection_libraries,
                      clear_connection_events, reset_all_data,
                      ingest_events_by_profile,
                      ingest_title_from_trakt,
                      add_manual_movie, add_manual_episode, add_manual_season,
                      delete_episode_watch, delete_movie_watch, delete_title)
from ..ingest.adapters import get_adapter
from ..auth.sessions import current_user, require_perm
from ..catalog import get_or_create_movie_by_tmdb
from ..plugins import enrich_title, runtime
from ._common import household_user_ids, poster_url, scope_user_ids

logger = logging.getLogger(__name__)

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


@bp.get("/connections/<conn_id>/accounts")
@require_perm("ingest.write")
def connection_accounts(conn_id: str):
    """List the source accounts (Plex users) for a connection plus the current
    account→profile mapping, so the edit UI can attribute synced history per user.
    The mapping is stored in scrobble_account_map (shared with live scrobbling)."""
    user = current_user()
    conn = query_one(
        "SELECT sc.config, p.adapter, p.key AS provider_key FROM source_connections sc "
        "JOIN providers p ON p.id = sc.provider_id "
        "WHERE sc.id = %s AND sc.household_id = %s",
        (conn_id, user["household_id"]),
    )
    if not conn:
        return jsonify({"error": "not found"}), 404
    try:
        accounts = get_adapter(conn["adapter"]).list_accounts(conn["config"] or {})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"could not load accounts: {exc}"}), 400
    rows = query_all(
        "SELECT account_label, user_id FROM scrobble_account_map "
        "WHERE household_id = %s AND source = %s",
        (user["household_id"], conn["provider_key"]),
    )
    mapping = {r["account_label"]: str(r["user_id"]) for r in rows}
    return jsonify({
        "source": conn["provider_key"],
        "accounts": [{"id": a.get("id"), "name": a.get("name"),
                      "user_id": mapping.get(a.get("name"))}
                     for a in accounts],
    })


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
        "SELECT sc.*, p.adapter, p.key AS provider_key, p.id AS provider_id "
        "FROM source_connections sc "
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

    # Attribute each event to the profile that watched it (Plex user -> profile via
    # scrobble_account_map); unmapped/label-less events fall back to `target`.
    summary = ingest_events_by_profile(
        str(user["household_id"]), conn["provider_key"], str(conn["provider_id"]),
        conn_id, target, events, is_trakt=conn["adapter"] == "trakt_api")
    spec = adapter.library_prune_spec(config)
    if spec:
        summary["pruned"] = prune_connection_libraries(conn_id, spec[0], spec[1])
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


@bp.put("/titles/<title_id>/platform-override")
@require_perm("ingest.write")
def set_platform_override(title_id: str):
    """Force the platform for a whole title, or clear it back to "Auto".

    Body: ``{"provider_id": "<uuid>"}`` to override, or ``{"provider_id": null}``
    to clear. The title's *soft* events (Trakt + manual) are immediately moved
    onto the chosen provider; real digital syncs (Plex/Jellyfin/Netflix/CSV) are
    left untouched. The override is household-wide (per title)."""
    body = request.get_json(silent=True) or {}
    provider_id = body.get("provider_id")

    title = query_one("SELECT id FROM titles WHERE id = %s", (title_id,))
    if not title:
        return jsonify({"error": "title not found"}), 404

    if provider_id:
        prov = query_one("SELECT id, key FROM providers WHERE id = %s", (provider_id,))
        if not prov:
            return jsonify({"error": "unknown provider"}), 400
        execute("UPDATE titles SET platform_override_provider_id = %s WHERE id = %s",
                (provider_id, title_id))
    else:
        execute("UPDATE titles SET platform_override_provider_id = NULL WHERE id = %s",
                (title_id,))

    from ..networks import reattribute_title_events
    result = reattribute_title_events(title_id)
    return jsonify({"ok": True, "override": provider_id or None, **result})

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


# ── Manual "add a cinema film": search TMDB, then create + mark watched ─────

def _map_movie_search_result(r: dict) -> dict | None:
    """Trim a raw TMDB movie search hit to the fields the picker needs. Returns
    ``None`` when the result has no usable id."""
    tmdb_id = r.get("id")
    if not tmdb_id:
        return None
    rd = r.get("release_date") or ""
    return {
        "tmdb_id": tmdb_id,
        "title": r.get("title") or r.get("name"),
        "year": int(rd[:4]) if rd[:4].isdigit() else None,
        "release_date": rd or None,
        "poster": poster_url(r.get("poster_path")),
        "overview": r.get("overview") or None,
    }


@bp.get("/catalog/tmdb-search")
@require_perm("catalog.read")
def tmdb_search():
    """Search TMDB for a movie to add by hand (e.g. a film seen in the cinema).

    Privacy: only the public query string is sent to TMDB — never any personal
    watch data. Returns an empty list when no metadata provider is configured."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})
    year = request.args.get("year")
    try:
        year_i = int(year) if year else None
    except ValueError:
        year_i = None

    results: list[dict] = []
    for pid in runtime.capability_providers("search"):
        try:
            plugin = runtime.get_plugin(pid)
        except Exception:  # noqa: BLE001
            logger.exception("search: could not load plugin %s", pid)
            continue
        if not getattr(plugin, "configured", True):
            continue
        try:
            raw = plugin.search(q, year_i, "movie") or []
        except Exception:  # noqa: BLE001 — a provider error must not break search
            logger.exception("search: provider %s failed for %r", pid, q)
            continue
        for r in raw:
            mapped = _map_movie_search_result(r)
            if mapped:
                results.append(mapped)
        if results:
            break  # first configured provider with hits wins
    return jsonify({"results": results})


@bp.post("/catalog/add-film")
@require_perm("ingest.write")
def add_film():
    """Add a movie picked from TMDB: create/reuse the title, enrich it, mark it
    watched on a date, and attribute it to a platform (default "Cinema").

    Body: ``{tmdb_id, title?, year?, date?, provider_key?, user_id?}``. The title
    is bound to the exact ``tmdb_id`` up front so enrichment fetches that record
    directly; the partial UNIQUE index on ``(kind, tmdb_id)`` reuses an existing
    row so a later sync of the same film never duplicates it. The watch is a
    ``manual`` event re-attributed onto the chosen platform via a title-level
    override."""
    user = current_user()
    target = _target_user(user)
    if not target:
        return jsonify({"error": "invalid target user"}), 400
    body = request.get_json(silent=True) or {}

    raw_id = body.get("tmdb_id")
    try:
        tmdb_id = int(raw_id)
    except (TypeError, ValueError):
        return jsonify({"error": "tmdb_id required"}), 400
    try:
        date = _parse_watch_date(body)
    except ValueError:
        return jsonify({"error": "invalid date"}), 400

    title_text = (body.get("title") or "").strip()
    year = body.get("year")
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None
    provider_key = (body.get("provider_key") or "cinema").strip() or "cinema"

    provider = query_one("SELECT id, key FROM providers WHERE key = %s", (provider_key,))
    if not provider:
        return jsonify({"error": "unknown provider"}), 400

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, enriched_at FROM titles "
                    "WHERE kind = 'movie' AND tmdb_id = %s", (tmdb_id,))
        existing = cur.fetchone()
        title_id = get_or_create_movie_by_tmdb(cur, tmdb_id, title_text, year)
        needs_enrich = existing is None or existing.get("enriched_at") is None

    if needs_enrich:
        try:
            enrich_title(title_id)
        except Exception:  # noqa: BLE001 — enrichment is best-effort
            logger.exception("enrich failed for title %s (best-effort)", title_id)

    result = add_manual_movie(target, title_id, date)
    if result.get("status") not in ("ok",):
        return jsonify({"error": "could not mark watched"}), 400

    execute("UPDATE titles SET platform_override_provider_id = %s WHERE id = %s",
            (provider["id"], title_id))
    from ..networks import reattribute_title_events
    reattribute_title_events(title_id)

    t = query_one("SELECT title FROM titles WHERE id = %s", (title_id,))
    return jsonify({"ok": True, "title_id": str(title_id),
                    "title": t["title"] if t else title_text,
                    "inserted": result.get("inserted", 0)})


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


@bp.delete("/episodes/<episode_id>/watch")
@require_perm("ingest.write")
def remove_episode_watch(episode_id: str):
    """Remove an episode's watch on a given date (``?date=YYYY-MM-DD``), for the
    scoped profile(s). Synced events are tombstoned so a later sync won't re-add
    them; manual events are deleted outright."""
    try:
        date = dt.date.fromisoformat((request.args.get("date") or "").strip())
    except ValueError:
        return jsonify({"error": "valid date required"}), 400
    result = delete_episode_watch(scope_user_ids(), episode_id, date)
    if result.get("status") == "no_episode":
        return jsonify({"error": "episode not found"}), 404
    return jsonify({"ok": True, **result})


@bp.delete("/titles/<title_id>/watch")
@require_perm("ingest.write")
def remove_title_watch(title_id: str):
    """Remove a movie's watch on a given date (``?date=YYYY-MM-DD``), for the
    scoped profile(s). Synced events are tombstoned against re-sync; manual ones
    are deleted."""
    try:
        date = dt.date.fromisoformat((request.args.get("date") or "").strip())
    except ValueError:
        return jsonify({"error": "valid date required"}), 400
    result = delete_movie_watch(scope_user_ids(), title_id, date)
    return jsonify({"ok": True, **result})


@bp.delete("/titles/<title_id>")
@require_perm("ingest.write")
def delete_title_endpoint(title_id: str):
    """Expert-mode action: permanently remove a whole title (and every watch
    event referencing it) from the database, then rebuild affected aggregates.
    The frontend gates the long-press that reaches this on ``prefs.expert``."""
    result = delete_title(title_id)
    if result.get("status") == "no_title":
        return jsonify({"error": "title not found"}), 404
    return jsonify({"ok": True, **result})


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
