"""Small shared utilities: hashing, normalization, tokens, JSON encoding."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import secrets
import uuid
from typing import Any

# ── Secret hashing (salted SHA-256, hash at rest) ──────────────────────────

def new_salt() -> str:
    return secrets.token_hex(16)


def hash_secret(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def verify_secret(value: str, salt: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_secret(value, salt), expected_hash)


def generate_token(prefix: str = "wvapi") -> tuple[str, str]:
    """Return (full_token, display_prefix). Full token is shown once."""
    body = secrets.token_urlsafe(32)
    full = f"{prefix}_{body}"
    return full, full[: len(prefix) + 9]


def generate_recovery_code() -> str:
    raw = secrets.token_hex(5).upper()  # 10 hex chars
    return f"{raw[:5]}-{raw[5:]}"


# ── Title / name normalization (for matching & dedup) ──────────────────────

_WS = re.compile(r"\s+")
_NON = re.compile(r"[^a-z0-9 ]+")
_ARTICLE = re.compile(r"^(the|a|an|de|het|een)\s+")


def normalize_text(value: str) -> str:
    s = (value or "").lower().strip()
    s = s.replace("&", "and")
    s = _NON.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    s = _ARTICLE.sub("", s)
    return s


# Recognize "Show: Season 1: Episode Name" / "Show (2020)" patterns
_SEASON_EP = re.compile(
    r"(?:season|seizoen|s)\s*(\d+).{0,4}?(?:episode|aflevering|ep|e)\s*(\d+)",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\((\d{4})\)")


def parse_episode_marker(text: str) -> tuple[int | None, int | None]:
    m = _SEASON_EP.search(text or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def parse_year(text: str) -> int | None:
    m = _YEAR.search(text or "")
    return int(m.group(1)) if m else None


def dedup_hash(*parts: Any) -> str:
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# ── JSON encoding for datetimes / UUIDs ────────────────────────────────────

class WVJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:  # noqa: D401
        if isinstance(o, (dt.datetime, dt.date)):
            return o.isoformat()
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, dt.timedelta):
            return o.total_seconds()
        return super().default(o)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
