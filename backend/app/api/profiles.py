"""Profiles, the 3-layer preference merge, global settings & API tokens."""
from __future__ import annotations

import json
import os
import uuid

from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from ..config import get_config
from ..db import connection, execute, query_all, query_one
from ..util import generate_recovery_code, generate_token, hash_secret, new_salt
from ..auth.sessions import current_user, require_auth, require_perm
from ._common import poster_url

bp = Blueprint("profiles", __name__, url_prefix="/api")

_AVATAR_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_AVATAR_MAX_BYTES = 8 * 1024 * 1024  # 8 MB


def _avatars_dir() -> str:
    d = os.path.join(get_config().DATA_DIR, "media", "avatars")
    os.makedirs(d, exist_ok=True)
    return d


def compose_display_name(first: str | None, last: str | None, fallback: str | None) -> str | None:
    """Compose "first last" from the edit fields, falling back when both are empty."""
    composed = ((first or "").strip() + " " + (last or "").strip()).strip()
    return composed or fallback

DEFAULT_PREFS = {
    "theme": "system",          # light | dark | system
    "accent": "#0a84ff",
    "default_profile": "all",
    "language": "en",
    "cinemaAdd": True,
    "dashboard_layout": {"order": [], "hidden": []},
}


# ── Profiles ───────────────────────────────────────────────────────────────

@bp.get("/profiles")
@require_perm("catalog.read")
def list_profiles():
    user = current_user()
    rows = query_all(
        "SELECT u.id, u.display_name, u.first_name, u.last_name, u.avatar_path, "
        "  u.accent_color, u.is_admin, u.last_seen_at, "
        "  (SELECT count(*) FROM watch_events we WHERE we.user_id = u.id AND we.deleted_at IS NULL) AS events "
        "FROM users u WHERE u.household_id = %s AND u.deleted_at IS NULL "
        "ORDER BY u.created_at",
        (user["household_id"],),
    )
    return jsonify([
        {"id": str(r["id"]), "display_name": r["display_name"],
         "first_name": r["first_name"], "last_name": r["last_name"],
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
    # first/last name: recompose display_name = "first last" whenever either is sent.
    if "first_name" in body or "last_name" in body:
        first = (body.get("first_name") if "first_name" in body else target.get("first_name")) or ""
        last = (body.get("last_name") if "last_name" in body else target.get("last_name")) or ""
        first, last = first.strip(), last.strip()
        fields.append("first_name = %s"); params.append(first or None)
        fields.append("last_name = %s"); params.append(last or None)
        composed = compose_display_name(first, last, None)
        if composed:
            fields.append("display_name = %s"); params.append(composed)
    if "display_name" in body and "first_name" not in body and "last_name" not in body:
        fields.append("display_name = %s"); params.append(body["display_name"].strip())
    if "accent_color" in body:
        fields.append("accent_color = %s"); params.append(body["accent_color"])
    if "is_admin" in body and user["is_admin"]:
        fields.append("is_admin = %s"); params.append(bool(body["is_admin"]))
    if fields:
        params.append(profile_id)
        execute(f"UPDATE users SET {', '.join(fields)} WHERE id = %s", params)
    return jsonify({"ok": True})


def _guard_profile(profile_id: str):
    """Return (user, target) if the caller may edit profile_id, else (resp, code)."""
    user = current_user()
    is_self = str(profile_id) == str(user["id"])
    if not is_self and "*" not in user["permissions"] and "profiles.manage" not in user["permissions"]:
        return None, (jsonify({"error": "forbidden"}), 403)
    target = query_one("SELECT * FROM users WHERE id = %s AND household_id = %s AND deleted_at IS NULL",
                       (profile_id, user["household_id"]))
    if not target:
        return None, (jsonify({"error": "not found"}), 404)
    return (user, target), None


@bp.post("/profiles/<profile_id>/avatar")
@require_auth
def upload_avatar(profile_id: str):
    ctx, err = _guard_profile(profile_id)
    if err:
        return err
    _, target = ctx
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    f = request.files["file"]
    ext = _AVATAR_EXT.get((f.mimetype or "").lower())
    if not ext:
        return jsonify({"error": "unsupported image type"}), 400
    data = f.read()
    if not data:
        return jsonify({"error": "empty file"}), 400
    if len(data) > _AVATAR_MAX_BYTES:
        return jsonify({"error": "file too large"}), 413

    fname = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(_avatars_dir(), fname), "wb") as out:
        out.write(data)

    old = target.get("avatar_path")
    execute("UPDATE users SET avatar_path = %s WHERE id = %s",
            (f"/api/media/avatars/{fname}", profile_id))
    # Best-effort cleanup of a previously uploaded local avatar.
    if old and isinstance(old, str) and old.startswith("/api/media/avatars/"):
        try:
            os.remove(os.path.join(_avatars_dir(), os.path.basename(old)))
        except OSError:
            pass
    return jsonify({"ok": True, "avatar": poster_url(f"/api/media/avatars/{fname}")})


@bp.delete("/profiles/<profile_id>/avatar")
@require_auth
def delete_avatar(profile_id: str):
    ctx, err = _guard_profile(profile_id)
    if err:
        return err
    _, target = ctx
    old = target.get("avatar_path")
    execute("UPDATE users SET avatar_path = NULL WHERE id = %s", (profile_id,))
    if old and isinstance(old, str) and old.startswith("/api/media/avatars/"):
        try:
            os.remove(os.path.join(_avatars_dir(), os.path.basename(old)))
        except OSError:
            pass
    return jsonify({"ok": True})


@bp.get("/media/avatars/<name>")
def serve_avatar(name: str):
    safe = secure_filename(name)
    if not safe:
        return jsonify({"error": "not found"}), 404
    return send_from_directory(_avatars_dir(), safe, max_age=3600)


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
