"""Attribution log API — visibility into how Trakt/manual ("soft") titles get
re-attributed to a streaming service, and why many land on "Other".

Backed by the ``attribution_log`` (latest decision per title) and
``attribution_log_history`` (trail of changes) tables, both written by
``app.networks.reattribute_title_events``. Read access needs ``catalog.read``;
the re-attribute actions need ``ingest.write``.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import execute, query_all, query_one
from ..auth.sessions import require_perm

bp = Blueprint("attribution", __name__, url_prefix="/api/attribution-log")

# Provider keys that count as the generic "Other" bucket in the UI filter.
_OTHER_KEYS = ("generic",)


@bp.get("")
@require_perm("catalog.read")
def list_log():
    """Latest attribution decision per title.

    ``?filter=other`` keeps only titles that landed on the generic provider
    (shown as "Other"); ``?filter=all`` (default) returns everything. ``?limit``
    caps the rows (default 300)."""
    flt = (request.args.get("filter") or "all").strip()
    try:
        limit = min(max(int(request.args.get("limit", 300)), 1), 1000)
    except (TypeError, ValueError):
        limit = 300

    where = ""
    params: list = []
    if flt == "other":
        where = "WHERE al.provider_key = ANY(%s)"
        params.append(list(_OTHER_KEYS))

    rows = query_all(
        "SELECT al.title_id, al.title, al.kind, al.provider_key, al.reason, "
        "  al.networks, al.events, al.moved, al.collapsed, al.updated_at, "
        "  p.name AS provider_name, p.color AS provider_color "
        "FROM attribution_log al "
        "LEFT JOIN providers p ON p.key = al.provider_key "
        f"{where} "
        "ORDER BY al.updated_at DESC LIMIT %s",
        (*params, limit),
    )
    counts = query_one(
        "SELECT count(*) AS total, "
        "  count(*) FILTER (WHERE provider_key = ANY(%s)) AS other "
        "FROM attribution_log",
        (list(_OTHER_KEYS),),
    ) or {"total": 0, "other": 0}

    return jsonify({
        "total": int(counts["total"]),
        "other": int(counts["other"]),
        "items": [
            {
                "title_id": str(r["title_id"]),
                "title": r["title"],
                "kind": r["kind"],
                "provider_key": r["provider_key"],
                "provider_name": r["provider_name"],
                "provider_color": r["provider_color"],
                "reason": r["reason"],
                "networks": r["networks"] or [],
                "events": int(r["events"] or 0),
                "moved": int(r["moved"] or 0),
                "collapsed": int(r["collapsed"] or 0),
                "updated_at": r["updated_at"].isoformat(),
            }
            for r in rows
        ],
    })


@bp.get("/<title_id>/history")
@require_perm("catalog.read")
def title_history(title_id: str):
    """Chronological attribution changes for one title (newest first)."""
    rows = query_all(
        "SELECT provider_key, reason, networks, moved, collapsed, created_at "
        "FROM attribution_log_history WHERE title_id = %s "
        "ORDER BY created_at DESC LIMIT 50",
        (title_id,),
    )
    return jsonify({
        "items": [
            {
                "provider_key": r["provider_key"],
                "reason": r["reason"],
                "networks": r["networks"] or [],
                "moved": int(r["moved"] or 0),
                "collapsed": int(r["collapsed"] or 0),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
    })


@bp.post("/<title_id>/reattribute")
@require_perm("ingest.write")
def reattribute_one(title_id: str):
    """Re-run network re-attribution for a single title now."""
    title = query_one("SELECT id FROM titles WHERE id = %s", (title_id,))
    if not title:
        return jsonify({"error": "title not found"}), 404
    from ..networks import reattribute_title_events
    result = reattribute_title_events(title_id)
    return jsonify({"ok": True, **result})


@bp.post("/reattribute-all")
@require_perm("ingest.write")
def reattribute_all_route():
    """Queue a household-wide re-attribution backfill (runs in the worker),
    deduped against any pending/running copy."""
    execute(
        "INSERT INTO background_jobs (kind, payload) "
        "SELECT 'reattribute_trakt_all', '{}'::jsonb WHERE NOT EXISTS ("
        "  SELECT 1 FROM background_jobs WHERE kind='reattribute_trakt_all' "
        "  AND status IN ('pending','running'))")
    return jsonify({"ok": True, "queued": True})
