"""Profiles, the 3-layer preference merge, global settings & API tokens."""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request

from ..db import connection, execute, query_all, query_one
from ..util import generate_recovery_code, generate_token, hash_secret, new_salt
from ..auth.sessions import current_user, require_auth, require_perm
from ._common import poster_url

bp = Blueprint("profiles", __name__, url_prefix="/api")

DEFAULT_PREFS = {
    "theme": "system",          # light | dark | system
    "accent": "#0a84ff",
    "default_profile": "all",
    "language": "en",
    "cinemaAdd": True,
}


# ── Profiles ───────────────────────────────────────────────────────────────

@bp.get("/profiles")
@require_perm("catalog.read")
def list_profiles():
    user = current_user()
    rows = query_all(
        "SELECT u.id, u.display_name, u.avatar_path, u.accent_color, u.is_admin, "
        "  u.last_seen_at, "
        "  (SELECT count(*) FROM watch_events we WHERE we.user_id = u.id AND we.deleted_at IS NULL) AS events "
        "FROM users u WHERE u.household_id = %s AND u.deleted_at IS NULL "
        "ORDER BY u.created_at",
        (user["household_id"],),
    )
    return jsonify([
        {"id": str(r["id"]), "display_name": r["display_name"],
         "avatar": poster_url(r["avatar_path"]), "accent_color": r["accent_color"],
         "is_admin": r["is_admin"], "events": int(r["events"]),
         "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None}
        for r in rows
    ])


@bp.post("/profiles")
@require_perm("profiles.manage")
def create_profile():
    """Admin onboards a member: creates the user + a recovery code the member
    redeems (then enrolls their own passkey)."""
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("display_name") or "").strip()
    if not name:
        return jsonify({"error": "display_name required"}), 400
    code = generate_recovery_code()
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (household_id, display_name, is_admin) VALUES (%s,%s,%s) RETURNING id",
            (user["household_id"], name, bool(body.get("is_admin"))),
        )
        new_id = cur.fetchone()["id"]
        cur.execute("SELECT id FROM roles WHERE key = %s",
                    ("admin" if body.get("is_admin") else "member",))
        role_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s,%s)", (new_id, role_id))
        salt = new_salt()
        cur.execute("INSERT INTO recovery_codes (user_id, code_hash, salt) VALUES (%s,%s,%s)",
                    (new_id, hash_secret(code, salt), salt))
        cur.execute("INSERT INTO user_preferences (user_id, data) VALUES (%s,'{}'::jsonb)", (new_id,))
    return jsonify({"ok": True, "id": str(new_id), "recovery_code": code})


@bp.patch("/profiles/<profile_id>")
@require_auth
def update_profile(profile_id: str):
    user = current_user()
    is_self = str(profile_id) == str(user["id"])
    if not is_self and "*" not in user["permissions"] and "profiles.manage" not in user["permissions"]:
        return jsonify({"error": "forbidden"}), 403
    target = query_one("SELECT * FROM users WHERE id = %s AND household_id = %s AND deleted_at IS NULL",
                       (profile_id, user["household_id"]))
    if not target:
        return jsonify({"error": "not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    fields, params = [], []
    if "display_name" in body:
        fields.append("display_name = %s"); params.append(body["display_name"].strip())
    if "accent_color" in body:
        fields.append("accent_color = %s"); params.append(body["accent_color"])
    if "is_admin" in body and user["is_admin"]:
        fields.append("is_admin = %s"); params.append(bool(body["is_admin"]))
    if fields:
        params.append(profile_id)
        execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", params)
    return jsonify({"ok": True})


@bp.delete("/profiles/<profile_id>")
@require_perm("profiles.manage")
def delete_profile(profile_id: str):
    user = current_user()
    if str(profile_id) == str(user["id"]):
        return jsonify({"error": "cannot delete yourself"}), 400
    execute("UPDATE users SET deleted_at = now() WHERE id = %s AND household_id = %s",
            (profile_id, user["household_id"]))
    return jsonify({"ok": True})


# ── Preferences (defaults -> global -> user) ───────────────────────────────

def effective_prefs(user_id: str) -> dict:
    glob = query_one("SELECT data FROM app_settings WHERE id = 1")
    usr = query_one("SELECT data FROM user_preferences WHERE user_id = %s", (user_id,))
    merged = dict(DEFAULT_PREFS)
    if glob and glob.get("data"):
        merged.update(glob["data"])
    if usr and usr.get("data"):
        merged.update(usr["data"])
    return merged


@bp.get("/preferences")
@require_auth
def get_preferences():
    user = current_user()
    return jsonify(effective_prefs(str(user["id"])))


@bp.put("/preferences")
@require_auth
def put_preferences():
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    execute(
        "INSERT INTO user_preferences (user_id, data) VALUES (%s, %s::jsonb) "
        "ON CONFLICT (user_id) DO UPDATE SET data = user_preferences.data || EXCLUDED.data",
        (user["id"], json.dumps(body)),
    )
    return jsonify(effective_prefs(str(user["id"])))


@bp.get("/settings")
@require_perm("settings.manage")
def get_settings():
    row = query_one("SELECT data FROM app_settings WHERE id = 1")
    return jsonify(row["data"] if row else {})


@bp.put("/settings")
@require_perm("settings.manage")
def put_settings():
    body = request.get_json(force=True, silent=True) or {}
    execute("UPDATE app_settings SET data = data || %s::jsonb WHERE id = 1", (json.dumps(body),))
    return jsonify({"ok": True})


@bp.patch("/household")
@require_perm("profiles.manage")
def update_household():
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    if "name" in body:
        execute("UPDATE households SET name = %s WHERE id = %s",
                (body["name"].strip(), user["household_id"]))
    return jsonify({"ok": True})


# ── API tokens (per-user, hashed) ──────────────────────────────────────────

@bp.get("/tokens")
@require_auth
def list_tokens():
    user = current_user()
    rows = query_all(
        "SELECT id, name, token_prefix, created_at, last_used_at FROM api_clients "
        "WHERE user_id = %s AND revoked_at IS NULL ORDER BY created_at DESC",
        (user["id"],),
    )
    return jsonify([
        {"id": str(r["id"]), "name": r["name"], "prefix": r["token_prefix"],
         "created_at": r["created_at"].isoformat(),
         "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None}
        for r in rows
    ])


@bp.post("/tokens")
@require_auth
def create_token():
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    full, prefix = generate_token("wvapi")
    salt = new_salt()
    execute(
        "INSERT INTO api_clients (user_id, name, token_prefix, token_hash, salt) "
        "VALUES (%s,%s,%s,%s,%s)",
        (user["id"], body.get("name") or "API token", prefix, hash_secret(full, salt), salt),
    )
    return jsonify({"ok": True, "token": full, "prefix": prefix})


@bp.delete("/tokens/<token_id>")
@require_auth
def revoke_token(token_id: str):
    user = current_user()
    execute("UPDATE api_clients SET revoked_at = now() WHERE id = %s AND user_id = %s",
            (token_id, user["id"]))
    return jsonify({"ok": True})
