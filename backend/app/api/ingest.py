"""Ingestion API: file imports, API-sync connections, providers list."""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from ..db import execute, query_all, query_one
from ..ingest import ingest_events
from ..ingest.adapters import get_adapter
from ..auth.sessions import current_user, require_perm
from ._common import household_user_ids

bp = Blueprint("ingest", __name__, url_prefix="/api")


# ── Providers catalog ──────────────────────────────────────────────────────

@bp.get("/providers")
@require_perm("catalog.read")
def list_providers():
    rows = query_all("SELECT id, key, name, ingest_type, adapter, color FROM providers ORDER BY name")
    return jsonify([
        {"id": str(r["id"]), "key": r["key"], "name": r["name"],
         "ingest_type": r["ingest_type"], "adapter": r["adapter"], "color": r["color"]}
        for r in rows
    ])


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
        "SELECT sc.id, sc.name, sc.enabled, sc.last_sync_at, sc.last_status, "
        "  p.key AS provider_key, p.name AS provider_name "
        "FROM source_connections sc JOIN providers p ON p.id = sc.provider_id "
        "WHERE sc.household_id = %s ORDER BY sc.created_at",
        (user["household_id"],),
    )
    return jsonify([
        {"id": str(r["id"]), "name": r["name"], "enabled": r["enabled"],
         "provider_key": r["provider_key"], "provider_name": r["provider_name"],
         "last_sync_at": r["last_sync_at"].isoformat() if r["last_sync_at"] else None,
         "last_status": r["last_status"]}
        for r in rows
    ])


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


@bp.delete("/connections/<conn_id>")
@require_perm("ingest.write")
def delete_connection(conn_id: str):
    user = current_user()
    execute("DELETE FROM source_connections WHERE id = %s AND household_id = %s",
            (conn_id, user["household_id"]))
    return jsonify({"ok": True})


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
        events, new_cursor = adapter.fetch_history(conn["config"], conn["cursor"] or {})
    except Exception as exc:  # noqa: BLE001
        execute("UPDATE source_connections SET last_status = %s, last_sync_at = now() WHERE id = %s",
                (f"error: {exc}", conn_id))
        return jsonify({"error": f"sync failed: {exc}"}), 400

    summary = ingest_events(target, str(conn["provider_id"]), conn_id, events) if events else \
        {"inserted": 0, "duplicates": 0, "titles_created": 0}
    execute(
        "UPDATE source_connections SET cursor = %s, last_status = %s, last_sync_at = now() WHERE id = %s",
        (json.dumps(new_cursor), f"ok: +{summary['inserted']}", conn_id),
    )
    return jsonify({"ok": True, "fetched": len(events), **summary})


@bp.post("/ingest/rebuild-agg")
@require_perm("settings.manage")
def rebuild_agg():
    execute("SELECT wv_rebuild_daily_agg()")
    return jsonify({"ok": True})
