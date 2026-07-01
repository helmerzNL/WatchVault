"""Passwordless WebAuthn (passkey) registration & login, plus the
OAuth2 + PKCE mobile bridge and recovery codes."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import uuid

from flask import Blueprint, jsonify, make_response, request
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..config import get_config
from ..db import connection, execute, query_all, query_one
from ..util import (
    generate_recovery_code,
    hash_secret,
    new_salt,
    now_utc,
    verify_secret,
)
from .sessions import current_user, issue_session, require_auth, revoke_session

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

CHALLENGE_TTL = dt.timedelta(minutes=5)


def _store_challenge(purpose: str, challenge: bytes, data: dict, user_id=None) -> None:
    execute(
        "INSERT INTO webauthn_challenges (purpose, user_id, challenge, data, expires_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (purpose, user_id, bytes_to_base64url(challenge), json.dumps(data),
         now_utc() + CHALLENGE_TTL),
    )


def _take_challenge(purpose: str) -> dict | None:
    rows = query_all(
        "SELECT * FROM webauthn_challenges WHERE purpose = %s AND expires_at > now() "
        "ORDER BY created_at DESC LIMIT 25",
        (purpose,),
    )
    return rows[0] if rows else None


def _set_session_cookie(resp, token: str):
    cfg = get_config()
    resp.set_cookie(
        cfg.SESSION_COOKIE, token,
        httponly=True, samesite="Lax", secure=cfg.is_secure_origin,
        max_age=cfg.SESSION_TTL_HOURS * 3600, path="/",
    )
    return resp


def _household_count() -> int:
    row = query_one("SELECT count(*) AS n FROM users WHERE deleted_at IS NULL")
    return int(row["n"]) if row else 0


# ── Status ─────────────────────────────────────────────────────────────────

@bp.get("/status")
def status():
    user = current_user()
    bootstrapped = _household_count() > 0
    out = {"bootstrapped": bootstrapped, "authenticated": bool(user)}
    if user:
        out["user"] = _public_user(user)
    return jsonify(out)


def _public_user(user: dict) -> dict:
    return {
        "id": str(user["id"]),
        "display_name": user["display_name"],
        "email": user.get("email"),
        "avatar_path": user.get("avatar_path"),
        "accent_color": user.get("accent_color"),
        "is_admin": user["is_admin"],
        "household_id": str(user["household_id"]),
        "household_name": user.get("household_name"),
        "permissions": sorted(user.get("permissions", set())),
    }


# ── Registration ───────────────────────────────────────────────────────────

@bp.post("/register/begin")
def register_begin():
    cfg = get_config()
    body = request.get_json(force=True, silent=True) or {}
    display_name = (body.get("display_name") or "").strip()
    if not display_name:
        return jsonify({"error": "display_name required"}), 400

    first_user = _household_count() == 0
    if not first_user and cfg.REGISTRATION_INVITE_CODE:
        if body.get("invite_code") != cfg.REGISTRATION_INVITE_CODE:
            return jsonify({"error": "invalid invite code"}), 403

    new_id = uuid.uuid4()
    options = generate_registration_options(
        rp_id=cfg.RP_ID,
        rp_name=cfg.RP_NAME,
        user_id=new_id.bytes,
        user_name=display_name,
        user_display_name=display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _store_challenge(
        "register", options.challenge,
        {"user_id": str(new_id), "display_name": display_name, "first_user": first_user},
    )
    return make_response(options_to_json(options), 200, {"Content-Type": "application/json"})


@bp.post("/register/complete")
def register_complete():
    cfg = get_config()
    body = request.get_json(force=True, silent=True) or {}
    credential = body.get("credential")
    if not credential:
        return jsonify({"error": "credential required"}), 400

    ch = _take_challenge("register")
    if not ch:
        return jsonify({"error": "no pending registration"}), 400
    data = ch["data"]

    try:
        verification = verify_registration_response(
            credential=json.dumps(credential),
            expected_challenge=base64url_to_bytes(ch["challenge"]),
            expected_rp_id=cfg.RP_ID,
            expected_origin=cfg.RP_ORIGINS,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"verification failed: {exc}"}), 400

    user_id = uuid.UUID(data["user_id"])
    first_user = data["first_user"]
    recovery_codes = [generate_recovery_code() for _ in range(8)]

    with connection() as conn, conn.cursor() as cur:
        if first_user:
            cur.execute("INSERT INTO households (name) VALUES (%s) RETURNING id",
                        ("My Household",))
            household_id = cur.fetchone()["id"]
        else:
            cur.execute("SELECT id FROM households ORDER BY created_at LIMIT 1")
            household_id = cur.fetchone()["id"]

        cur.execute(
            "INSERT INTO users (id, household_id, display_name, is_admin) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, household_id, data["display_name"], first_user),
        )
        # default role
        role_key = "admin" if first_user else "member"
        cur.execute("SELECT id FROM roles WHERE key = %s", (role_key,))
        role_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                    (user_id, role_id))
        # credential
        cur.execute(
            "INSERT INTO webauthn_credentials "
            "(user_id, credential_id, public_key, sign_count, transports, name) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, verification.credential_id, verification.credential_public_key,
             verification.sign_count, credential.get("response", {}).get("transports", []) or [],
             "Passkey"),
        )
        # recovery codes (hashed)
        for code in recovery_codes:
            salt = new_salt()
            cur.execute(
                "INSERT INTO recovery_codes (user_id, code_hash, salt) VALUES (%s, %s, %s)",
                (user_id, hash_secret(code, salt), salt),
            )
        cur.execute("INSERT INTO user_preferences (user_id, data) VALUES (%s, '{}'::jsonb) "
                    "ON CONFLICT DO NOTHING", (user_id,))
        cur.execute("DELETE FROM webauthn_challenges WHERE id = %s", (ch["id"],))

    token = issue_session(str(user_id), request.headers.get("User-Agent"))
    resp = jsonify({"ok": True, "recovery_codes": recovery_codes,
                    "user_id": str(user_id)})
    return _set_session_cookie(resp, token)


# ── Login (discoverable passkeys) ──────────────────────────────────────────

@bp.post("/login/begin")
def login_begin():
    cfg = get_config()
    options = generate_authentication_options(
        rp_id=cfg.RP_ID,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _store_challenge("login", options.challenge, {})
    return make_response(options_to_json(options), 200, {"Content-Type": "application/json"})


@bp.post("/login/complete")
def login_complete():
    cfg = get_config()
    body = request.get_json(force=True, silent=True) or {}
    credential = body.get("credential")
    if not credential:
        return jsonify({"error": "credential required"}), 400

    ch = _take_challenge("login")
    if not ch:
        return jsonify({"error": "no pending login"}), 400

    raw_id = base64url_to_bytes(credential["rawId"])
    cred_row = query_one(
        "SELECT * FROM webauthn_credentials WHERE credential_id = %s", (raw_id,)
    )
    if not cred_row:
        return jsonify({"error": "unknown credential"}), 400

    try:
        verification = verify_authentication_response(
            credential=json.dumps(credential),
            expected_challenge=base64url_to_bytes(ch["challenge"]),
            expected_rp_id=cfg.RP_ID,
            expected_origin=cfg.RP_ORIGINS,
            credential_public_key=bytes(cred_row["public_key"]),
            credential_current_sign_count=cred_row["sign_count"],
            require_user_verification=False,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"verification failed: {exc}"}), 400

    execute(
        "UPDATE webauthn_credentials SET sign_count = %s, last_used_at = now() WHERE id = %s",
        (verification.new_sign_count, cred_row["id"]),
    )
    execute("UPDATE users SET last_seen_at = now() WHERE id = %s", (cred_row["user_id"],))
    execute("DELETE FROM webauthn_challenges WHERE id = %s", (ch["id"],))

    token = issue_session(str(cred_row["user_id"]), request.headers.get("User-Agent"))
    resp = jsonify({"ok": True})
    return _set_session_cookie(resp, token)


@bp.post("/logout")
@require_auth
def logout():
    user = current_user()
    if user.get("_jti"):
        revoke_session(user["_jti"])
    resp = jsonify({"ok": True})
    resp.delete_cookie(get_config().SESSION_COOKIE, path="/")
    return resp


# ── Recovery: redeem a code to enroll a new passkey ───────────────────────

@bp.post("/recover")
def recover():
    body = request.get_json(force=True, silent=True) or {}
    code = (body.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "code required"}), 400
    rows = query_all("SELECT rc.*, u.display_name FROM recovery_codes rc "
                     "JOIN users u ON u.id = rc.user_id WHERE rc.used_at IS NULL")
    for r in rows:
        if verify_secret(code, r["salt"], r["code_hash"]):
            execute("UPDATE recovery_codes SET used_at = now() WHERE id = %s", (r["id"],))
            # short-lived session to let the user add a passkey
            token = issue_session(str(r["user_id"]), request.headers.get("User-Agent"))
            resp = jsonify({"ok": True})
            return _set_session_cookie(resp, token)
    return jsonify({"error": "invalid code"}), 400


# ── Add an extra passkey to the current account ───────────────────────────

@bp.post("/passkey/add/begin")
@require_auth
def passkey_add_begin():
    cfg = get_config()
    user = current_user()
    existing = query_all(
        "SELECT credential_id FROM webauthn_credentials WHERE user_id = %s", (user["id"],)
    )
    options = generate_registration_options(
        rp_id=cfg.RP_ID,
        rp_name=cfg.RP_NAME,
        user_id=uuid.UUID(str(user["id"])).bytes,
        user_name=user["display_name"],
        user_display_name=user["display_name"],
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(e["credential_id"])) for e in existing
        ],
    )
    _store_challenge("register", options.challenge,
                     {"user_id": str(user["id"]), "display_name": user["display_name"],
                      "add_only": True, "first_user": False})
    return make_response(options_to_json(options), 200, {"Content-Type": "application/json"})


@bp.post("/passkey/add/complete")
@require_auth
def passkey_add_complete():
    cfg = get_config()
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    credential = body.get("credential")
    ch = _take_challenge("register")
    if not credential or not ch:
        return jsonify({"error": "bad request"}), 400
    try:
        verification = verify_registration_response(
            credential=json.dumps(credential),
            expected_challenge=base64url_to_bytes(ch["challenge"]),
            expected_rp_id=cfg.RP_ID,
            expected_origin=cfg.RP_ORIGINS,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"verification failed: {exc}"}), 400
    execute(
        "INSERT INTO webauthn_credentials (user_id, credential_id, public_key, sign_count, name) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user["id"], verification.credential_id, verification.credential_public_key,
         verification.sign_count, body.get("name") or "Passkey"),
    )
    execute("DELETE FROM webauthn_challenges WHERE id = %s", (ch["id"],))
    return jsonify({"ok": True})


# ── List / delete passkeys for the current account ────────────────────────

@bp.get("/passkeys")
@require_auth
def list_passkeys():
    user = current_user()
    rows = query_all(
        "SELECT id, name, created_at, last_used_at FROM webauthn_credentials "
        "WHERE user_id = %s ORDER BY created_at",
        (user["id"],),
    )
    return jsonify([
        {
            "id": str(r["id"]),
            "name": r["name"] or "Passkey",
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
        }
        for r in rows
    ])


@bp.delete("/passkeys/<cred_id>")
@require_auth
def delete_passkey(cred_id):
    user = current_user()
    try:
        cid = uuid.UUID(cred_id)
    except ValueError:
        return jsonify({"error": "invalid id"}), 400
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM webauthn_credentials WHERE user_id = %s",
            (user["id"],),
        )
        if cur.fetchone()["n"] <= 1:
            # Never leave an account with no way to sign in.
            return jsonify({"error": "cannot delete the last passkey"}), 400
        cur.execute(
            "DELETE FROM webauthn_credentials WHERE id = %s AND user_id = %s",
            (cid, user["id"]),
        )
        if cur.rowcount == 0:
            return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


# ── Regenerate recovery codes for the current account ─────────────────────

@bp.post("/recovery-codes/regenerate")
@require_auth
def regenerate_recovery_codes():
    user = current_user()
    codes = [generate_recovery_code() for _ in range(8)]
    with connection() as conn, conn.cursor() as cur:
        # Replacing the set invalidates any previously issued codes.
        cur.execute("DELETE FROM recovery_codes WHERE user_id = %s", (user["id"],))
        for code in codes:
            salt = new_salt()
            cur.execute(
                "INSERT INTO recovery_codes (user_id, code_hash, salt) VALUES (%s, %s, %s)",
                (user["id"], hash_secret(code, salt), salt),
            )
    return jsonify({"ok": True, "recovery_codes": codes})


# ── OAuth2 + PKCE mobile bridge ────────────────────────────────────────────
# Native app: open /authorize in a web view (user signs in with passkey),
# receive an auth code on the redirect, then exchange it at /token with the
# PKCE verifier for a JWT.

@bp.post("/oauth/authorize")
@require_auth
def oauth_authorize():
    user = current_user()
    body = request.get_json(force=True, silent=True) or {}
    challenge = body.get("code_challenge")
    redirect_uri = body.get("redirect_uri")
    client_id = body.get("client_id", "watchvault-ios")
    if not challenge or not redirect_uri:
        return jsonify({"error": "code_challenge and redirect_uri required"}), 400
    code = uuid.uuid4().hex + uuid.uuid4().hex
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    execute(
        "INSERT INTO oauth_authorizations "
        "(code_hash, user_id, client_id, redirect_uri, code_challenge, scope, expires_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (code_hash, user["id"], client_id, redirect_uri, challenge, body.get("scope", ""),
         now_utc() + dt.timedelta(minutes=5)),
    )
    return jsonify({"code": code, "redirect_uri": redirect_uri})


@bp.post("/oauth/token")
def oauth_token():
    body = request.get_json(force=True, silent=True) or {}
    code = body.get("code")
    verifier = body.get("code_verifier")
    if not code or not verifier:
        return jsonify({"error": "code and code_verifier required"}), 400
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    row = query_one(
        "SELECT * FROM oauth_authorizations WHERE code_hash = %s AND consumed_at IS NULL "
        "AND expires_at > now()",
        (code_hash,),
    )
    if not row:
        return jsonify({"error": "invalid_grant"}), 400
    # Verify PKCE S256
    digest = hashlib.sha256(verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    if expected != row["code_challenge"]:
        return jsonify({"error": "invalid_grant"}), 400
    execute("UPDATE oauth_authorizations SET consumed_at = now() WHERE id = %s", (row["id"],))
    token = issue_session(str(row["user_id"]), "ios")
    return jsonify({"access_token": token, "token_type": "Bearer",
                    "expires_in": get_config().SESSION_TTL_HOURS * 3600})
