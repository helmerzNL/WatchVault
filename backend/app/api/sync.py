"""Offline sync spine for the native client.

Clients pull everything changed since revision N; the server returns the
changed rows (with tombstones via deleted_at) and the new high-water mark.
Titles are a shared catalog; watch events & profiles are household-scoped.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import query_all, query_one
from ..auth.sessions import current_user, require_auth
from ._common import household_user_ids, poster_url

bp = Blueprint("sync", __name__, url_prefix="/api/sync")


@bp.get("/changes")
@require_auth
def changes():
    user = current_user()
    since = int(request.args.get("since", 0))
    ids = [str(i) for i in household_user_ids()]

    users = query_all(
        "SELECT id, display_name, avatar_path, accent_color, is_admin, revision, deleted_at "
        "FROM users WHERE household_id = %s AND revision > %s ORDER BY revision LIMIT 1000",
        (user["household_id"], since),
    )
    titles = query_all(
        "SELECT id, kind, title, year, poster_path, tmdb_id, revision "
        "FROM titles WHERE revision > %s ORDER BY revision LIMIT 2000",
        (since,),
    )
    events = query_all(
        "SELECT id, user_id, provider_id, title_id, episode_id, item_kind, raw_title, "
        "  season, episode, watched_at, watched_date, duration_seconds, completed, "
        "  revision, deleted_at "
        "FROM watch_events WHERE user_id = ANY(%s::uuid[]) AND revision > %s "
        "ORDER BY revision LIMIT 5000",
        (ids, since),
    )
    prefs = query_all(
        "SELECT user_id, data, revision FROM user_preferences "
        "WHERE user_id = ANY(%s::uuid[]) AND revision > %s ORDER BY revision",
        (ids, since),
    )

    hw = query_one("SELECT last_value FROM wv_revision_seq")
    high_water = int(hw["last_value"]) if hw else since

    return jsonify({
        "revision": high_water,
        "users": [
            {"id": str(u["id"]), "display_name": u["display_name"],
             "avatar": poster_url(u["avatar_path"]), "accent_color": u["accent_color"],
             "is_admin": u["is_admin"], "revision": u["revision"],
             "deleted": u["deleted_at"] is not None}
            for u in users
        ],
        "titles": [
            {"id": str(t["id"]), "kind": t["kind"], "title": t["title"], "year": t["year"],
             "poster": poster_url(t["poster_path"]), "tmdb_id": t["tmdb_id"],
             "revision": t["revision"]}
            for t in titles
        ],
        "watch_events": [
            {"id": str(e["id"]), "user_id": str(e["user_id"]),
             "title_id": str(e["title_id"]) if e["title_id"] else None,
             "item_kind": e["item_kind"], "raw_title": e["raw_title"],
             "season": e["season"], "episode": e["episode"],
             "watched_at": e["watched_at"].isoformat(),
             "watched_date": e["watched_date"].isoformat(),
             "duration_seconds": e["duration_seconds"], "completed": e["completed"],
             "revision": e["revision"], "deleted": e["deleted_at"] is not None}
            for e in events
        ],
        "preferences": [
            {"user_id": str(p["user_id"]), "data": p["data"], "revision": p["revision"]}
            for p in prefs
        ],
    })
