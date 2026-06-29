"""Shared helpers for API blueprints: user scoping, image URLs, serialization."""
from __future__ import annotations

from flask import request

from ..db import query_all
from ..auth.sessions import current_user

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

# Effective watch seconds: real duration, else the title runtime, else 0.
EFF_SECONDS = "COALESCE(we.duration_seconds, t.runtime_minutes * 60, 0)"


def household_user_ids() -> list[str]:
    user = current_user()
    rows = query_all(
        "SELECT id FROM users WHERE household_id = %s AND deleted_at IS NULL",
        (user["household_id"],),
    )
    return [r["id"] for r in rows]


def scope_user_ids(profile: str | None = None) -> list[str]:
    """Resolve the ?profile= filter to a concrete list of user ids in the
    current household. 'all'/None -> every member; otherwise a single member."""
    if profile is None:
        profile = request.args.get("profile")
    all_ids = household_user_ids()
    if not profile or profile in ("all", "household"):
        return all_ids
    return [uid for uid in all_ids if str(uid) == str(profile)]


def poster_url(path: str | None, size: str = "w342") -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"{TMDB_IMAGE_BASE}/{size}{path}"


def profile_url(path: str | None) -> str | None:
    return poster_url(path, "w185")
