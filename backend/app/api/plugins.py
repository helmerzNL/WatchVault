"""Plugin management API: list, configure secrets, enable/disable, provenance,
and manual title enrichment."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import query_all, query_one
from ..plugins import enrich_title, runtime
from ..auth.sessions import require_perm
from ._common import scope_user_ids

bp = Blueprint("plugins", __name__, url_prefix="/api")


@bp.get("/plugins")
@require_perm("plugins.manage")
def list_plugins():
    manifests = runtime.discover()
    rows = {r["id"]: r for r in query_all("SELECT * FROM plugins")}
    out = []
    for pid, manifest in manifests.items():
        db = rows.get(pid, {})
        out.append({
            "id": pid,
            "name": manifest.get("name", pid),
            "version": manifest.get("version", "0.0.0"),
            "kind": manifest.get("kind", "provider"),
            "description": manifest.get("description", ""),
            "capabilities": manifest.get("capabilities", []),
            "enabled": db.get("enabled", True),
            "is_system": db.get("is_system", False),
            "configured": runtime.is_configured(pid),
            "secret_keys": list(manifest.get("secrets", {}).keys()),
            "settings_schema": manifest.get("settings", {}),
        })
    return jsonify(out)


@bp.put("/plugins/<plugin_id>/secrets")
@require_perm("plugins.manage")
def set_secrets(plugin_id: str):
    body = request.get_json(force=True, silent=True) or {}
    # only persist non-empty values so blanks don't wipe existing secrets
    clean = {k: v for k, v in body.items() if isinstance(v, str) and v.strip()}
    if clean:
        runtime.set_secrets(plugin_id, clean)
    return jsonify({"ok": True, "configured": runtime.is_configured(plugin_id)})


@bp.post("/plugins/<plugin_id>/enable")
@require_perm("plugins.manage")
def set_enabled(plugin_id: str):
    body = request.get_json(force=True, silent=True) or {}
    runtime.set_enabled(plugin_id, bool(body.get("enabled", True)))
    return jsonify({"ok": True})


@bp.get("/titles/<title_id>/provenance")
@require_perm("plugins.manage")
def provenance(title_id: str):
    rows = query_all(
        "SELECT field, source, value, created_at FROM metadata_provenance "
        "WHERE entity_type='title' AND entity_id = %s ORDER BY field",
        (title_id,),
    )
    return jsonify([
        {"field": r["field"], "source": r["source"], "value": r["value"],
         "created_at": r["created_at"].isoformat()}
        for r in rows
    ])


@bp.post("/titles/<title_id>/enrich")
@require_perm("ingest.write")
def enrich(title_id: str):
    result = enrich_title(title_id)
    return jsonify(result)
