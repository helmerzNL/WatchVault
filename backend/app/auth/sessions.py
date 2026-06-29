"""Session issuing, JWT verification, and auth/permission decorators."""
from __future__ import annotations

import datetime as dt
import functools
import uuid
from typing import Optional

import jwt
from flask import g, jsonify, request

from ..config import get_config
from ..db import query_all, query_one, execute
from ..util import hash_secret, now_utc

ALGO = "HS256"


# ── Token issuing ──────────────────────────────────────────────────────────

def issue_session(user_id: str, user_agent: str | None = None) -> str:
    cfg = get_config()
    jti = uuid.uuid4().hex
    expires = now_utc() + dt.timedelta(hours=cfg.SESSION_TTL_HOURS)
    execute(
        "INSERT INTO sessions (user_id, jti, user_agent, expires_at) "
        "VALUES (%s, %s, %s, %s)",
        (user_id, jti, user_agent, expires),
    )
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "iat": int(now_utc().timestamp()),
        "exp": int(expires.timestamp()),
    }
    return jwt.encode(payload, cfg.SESSION_SECRET, algorithm=ALGO)


def revoke_session(jti: str) -> None:
    execute("UPDATE sessions SET revoked_at = now() WHERE jti = %s", (jti,))


# ── Resolution ─────────────────────────────────────────────────────────────

def _load_user(user_id: str) -> Optional[dict]:
    user = query_one(
        "SELECT u.*, h.name AS household_name FROM users u "
        "JOIN households h ON h.id = u.household_id "
        "WHERE u.id = %s AND u.deleted_at IS NULL",
        (user_id,),
    )
    if not user:
        return None
    perms = query_all(
        "SELECT DISTINCT rp.permission_key AS key FROM user_roles ur "
        "JOIN role_permissions rp ON rp.role_id = ur.role_id "
        "WHERE ur.user_id = %s",
        (user_id,),
    )
    user["permissions"] = {p["key"] for p in perms}
    if user["is_admin"]:
        user["permissions"].add("*")
    return user


def _from_jwt(token: str) -> Optional[dict]:
    cfg = get_config()
    try:
        payload = jwt.decode(token, cfg.SESSION_SECRET, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    sess = query_one(
        "SELECT id FROM sessions WHERE jti = %s AND revoked_at IS NULL "
        "AND expires_at > now()",
        (payload.get("jti"),),
    )
    if not sess:
        return None
    user = _load_user(payload["sub"])
    if user:
        user["_jti"] = payload.get("jti")
    return user


def _from_api_token(token: str) -> Optional[dict]:
    prefix = token[: token.find("_") + 9] if "_" in token else token[:9]
    candidates = query_all(
        "SELECT * FROM api_clients WHERE token_prefix = %s AND revoked_at IS NULL",
        (prefix,),
    )
    for c in candidates:
        if hash_secret(token, c["salt"]) == c["token_hash"]:
            execute("UPDATE api_clients SET last_used_at = now() WHERE id = %s", (c["id"],))
            return _load_user(c["user_id"])
    return None


def resolve_current_user() -> Optional[dict]:
    if "user" in g:
        return g.user
    user = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        user = _from_api_token(token) if token.startswith("wvapi_") else _from_jwt(token)
    if user is None:
        cookie = request.cookies.get(get_config().SESSION_COOKIE)
        if cookie:
            user = _from_jwt(cookie)
    g.user = user
    return user


# ── Decorators ─────────────────────────────────────────────────────────────

def require_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = resolve_current_user()
        if not user:
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def require_perm(key: str):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = resolve_current_user()
            if not user:
                return jsonify({"error": "unauthorized"}), 401
            perms = user.get("permissions", set())
            if "*" not in perms and key not in perms:
                return jsonify({"error": "forbidden", "needs": key}), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


def current_user() -> Optional[dict]:
    return resolve_current_user()
