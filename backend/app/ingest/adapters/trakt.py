"""Trakt adapter — direct API sync against the official Trakt.tv API.

Trakt has a well-documented REST API. Watch history is read from:

    GET https://api.trakt.tv/users/{username}/history?page=&limit=&start_at=&extended=full
    GET https://api.trakt.tv/sync/history (authenticated user, incl. private)

Required headers: ``trakt-api-version: 2`` and ``trakt-api-key: {client_id}``.
A private profile additionally needs an OAuth ``Authorization: Bearer {access_token}``;
with a token we read ``/sync/history`` (your own history, including private).

Obtaining a token without leaving the app: the user creates a Trakt application
(Client ID + Client Secret) and authorizes via the device flow — WatchVault shows
a short code that the user enters at trakt.tv/activate. We poll Trakt
(``request_device_code`` / ``poll_device_token``) until approved and store the
returned access + refresh token. Tokens are refreshed automatically before they
expire (``refresh_tokens`` / ``prepare_config``).

Config: {"client_id", "client_secret", "access_token", "refresh_token",
         "token_expires_at" (epoch), "username"}
"""
from __future__ import annotations

import datetime as dt
import time

import requests

from .base import SourceAdapter
from ..models import NormalizedEvent

API_BASE = "https://api.trakt.tv"
PAGE_LIMIT = 100
MAX_PAGES = 25          # cap one sync at 2500 events; cursor makes the next sync incremental
# A single title's full history is bounded by its episode count; a generous cap.
TITLE_MAX_PAGES = 20

# Device OAuth flow: the user enters a short code at trakt.tv/activate.
# (Trakt removed support for the urn:ietf:wg:oauth:2.0:oob "PIN" redirect, which
#  now fails with "redirect uri is malformed or doesn't match client redirect URI".)
DEVICE_CODE_URL = f"{API_BASE}/oauth/device/code"
DEVICE_TOKEN_URL = f"{API_BASE}/oauth/device/token"
# Map a Trakt device-token poll HTTP status to a flow state.
_DEVICE_POLL_STATUS = {
    200: "authorized",
    400: "pending",     # waiting for the user to approve in Trakt
    404: "error",       # invalid device code
    409: "error",       # already used
    410: "expired",     # the code expired — start again
    418: "denied",      # the user denied the request
    429: "slow_down",   # polling too fast — back off
}
# Refresh a token this many seconds before it actually expires.
REFRESH_SKEW = 86_400


def _token_payload(data: dict) -> dict:
    """Normalize a Trakt /oauth/token response into the bits we persist."""
    created = int(data.get("created_at") or time.time())
    expires_in = int(data.get("expires_in") or 0)
    return {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "token_expires_at": created + expires_in if expires_in else None,
    }


def request_device_code(client_id: str) -> dict:
    """Start the Trakt device flow.

    Returns a short ``user_code`` the user types at ``verification_url`` plus the
    ``device_code`` we poll with (see ``poll_device_token``)."""
    resp = requests.post(
        DEVICE_CODE_URL,
        json={"client_id": client_id},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise ValueError(
            "Trakt could not start authorization. Check the Client ID and try again.")
    d = resp.json()
    return {
        "device_code": d.get("device_code"),
        "user_code": d.get("user_code"),
        "verification_url": d.get("verification_url") or "https://trakt.tv/activate",
        "expires_in": int(d.get("expires_in") or 600),
        "interval": int(d.get("interval") or 5),
    }


def poll_device_token(client_id: str, client_secret: str, device_code: str) -> dict:
    """Poll once for the device-flow result.

    Returns ``{"status": ...}`` where status is one of authorized / pending /
    slow_down / expired / denied / error. On ``authorized`` the access + refresh
    tokens are merged into the returned dict."""
    resp = requests.post(
        DEVICE_TOKEN_URL,
        json={"code": device_code, "client_id": client_id, "client_secret": client_secret},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    status = _DEVICE_POLL_STATUS.get(resp.status_code, "error")
    if status == "authorized":
        return {"status": status, **_token_payload(resp.json())}
    return {"status": status}


def refresh_tokens(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Rotate an expired/expiring access token using its refresh token."""
    resp = requests.post(
        f"{API_BASE}/oauth/token",
        json={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise ValueError("Trakt token refresh failed — re-authorize the connection.")
    return _token_payload(resp.json())


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _runtime_seconds(obj: dict) -> int | None:
    rt = obj.get("runtime")
    return int(rt) * 60 if isinstance(rt, (int, float)) and rt else None


def _pretty_genres(obj: dict) -> list[str]:
    # Trakt returns genre slugs like "science-fiction"; make them display-friendly
    # and consistent with TMDB's names ("Science Fiction").
    return [g.replace("-", " ").title() for g in (obj.get("genres") or []) if g]


class TraktAdapter(SourceAdapter):
    id = "trakt_api"
    ingest_type = "api"
    display_name = "Trakt"
    config_fields = [
        {"key": "client_id", "label": "API client ID", "type": "text", "required": True,
         "placeholder": "Trakt application Client ID",
         "help": "Create an app at trakt.tv/oauth/applications and copy its Client ID."},
        {"key": "client_secret", "label": "API client secret", "type": "password", "required": False,
         "placeholder": "Trakt application Client Secret",
         "help": "Needed to authorize and to auto-refresh the access token. "
                 "Copy it from the same Trakt application page."},
        {"key": "username", "label": "Username", "type": "text", "required": True,
         "placeholder": "me", "help": "Your Trakt username, or 'me' when using an access token."},
        # Special field: renders the device authorize flow in the UI and stores the
        # resulting access_token/refresh_token/token_expires_at into the config.
        {"key": "access_token", "label": "Authorization", "type": "trakt_oauth", "required": False,
         "help": "Recommended: Trakt profiles are private by default. Authorize with a device "
                 "code so your own history (including private) syncs via /sync/history. Without "
                 "it, only a public profile works."},
    ]

    def prepare_config(self, config: dict) -> tuple[dict, bool]:
        """Proactively refresh the Trakt access token when it is near expiry.

        Requires a client_secret + refresh_token. Returns the (possibly updated)
        config and whether it changed so the caller can persist new tokens.
        """
        refresh_token = config.get("refresh_token")
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        expires_at = config.get("token_expires_at")
        if not (refresh_token and client_id and client_secret):
            return config, False
        # Refresh when expired/expiring, or when expiry is unknown but we have a token.
        if expires_at and time.time() < (int(expires_at) - REFRESH_SKEW):
            return config, False
        tokens = refresh_tokens(client_id, client_secret, refresh_token)
        return {**config, **tokens}, True

    def fetch_history(self, config: dict, cursor: dict) -> tuple[list[NormalizedEvent], dict]:
        client_id = config.get("client_id")
        username = (config.get("username") or "me").strip() or "me"
        access_token = config.get("access_token")
        if not client_id:
            raise ValueError("Trakt connection requires a client_id")

        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": client_id,
        }
        # With an OAuth token, read the authenticated user's own history via /sync/history.
        # This works for private profiles and avoids username/slug mismatches. Without a
        # token, fall back to the public /users/{username}/history (public profiles only).
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
            url = f"{API_BASE}/sync/history"
        else:
            url = f"{API_BASE}/users/{username}/history"

        since = _parse_iso(cursor.get("since")) or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

        events: list[NormalizedEvent] = []
        max_watched = since
        page = 1
        while page <= MAX_PAGES:
            resp = requests.get(
                url,
                params={
                    "page": page,
                    "limit": PAGE_LIMIT,
                    "start_at": since.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "extended": "full",
                },
                headers=headers,
                timeout=30,
            )
            if resp.status_code in (401, 403):
                raise ValueError(
                    "Trakt returned 401/403 — your watch history is private. Add an OAuth "
                    "access token to this connection (and set username to 'me'), or make your "
                    "Trakt profile/history public.")
            resp.raise_for_status()
            rows = resp.json() or []
            if not rows:
                break

            for row in rows:
                ev = self._to_event(row)
                if ev is None:
                    continue
                if ev.watched_at <= since:
                    continue
                max_watched = max(max_watched, ev.watched_at)
                events.append(ev)

            page_count = int(resp.headers.get("X-Pagination-Page-Count", "1") or "1")
            if page >= page_count:
                break
            page += 1

        return events, {"since": max_watched.isoformat()}

    def _auth_headers(self, config: dict) -> dict:
        client_id = config.get("client_id")
        access_token = config.get("access_token")
        if not client_id:
            raise ValueError("Trakt connection requires a client_id")
        if not access_token:
            raise ValueError(
                "Trakt per-title sync needs an OAuth access token — authorize the "
                "Trakt connection first.")
        return {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": client_id,
            "Authorization": f"Bearer {access_token}",
        }

    def _resolve_trakt_id(self, headers: dict, kind: str, tmdb_id, external_ids: dict):
        """Find the Trakt id for a local title.

        Prefers a Trakt id we already stored on the title's external_ids; falls
        back to resolving the TMDB id via Trakt's search. Returns the Trakt
        numeric id (or slug) as a string, or None when it can't be resolved.
        """
        ext = external_ids or {}
        for key in ("trakt", "slug"):
            if ext.get(key):
                return str(ext[key])
        if not tmdb_id:
            return None
        search_type = "show" if kind == "series" else "movie"
        resp = requests.get(
            f"{API_BASE}/search/tmdb/{tmdb_id}",
            params={"type": search_type},
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        for hit in resp.json() or []:
            obj = hit.get(search_type) or {}
            ids = obj.get("ids") or {}
            if ids.get("trakt"):
                return str(ids["trakt"])
        return None

    def fetch_title_history(self, config: dict, title_ref: dict) -> list[NormalizedEvent]:
        kind = title_ref.get("kind") or "movie"
        headers = self._auth_headers(config)
        trakt_id = self._resolve_trakt_id(
            headers, kind, title_ref.get("tmdb_id"), title_ref.get("external_ids") or {})
        if not trakt_id:
            return []

        item_type = "shows" if kind == "series" else "movies"
        url = f"{API_BASE}/sync/history/{item_type}/{trakt_id}"
        events: list[NormalizedEvent] = []
        page = 1
        while page <= TITLE_MAX_PAGES:
            resp = requests.get(
                url,
                params={"page": page, "limit": PAGE_LIMIT, "extended": "full"},
                headers=headers,
                timeout=30,
            )
            if resp.status_code in (401, 403):
                raise ValueError(
                    "Trakt returned 401/403 — re-authorize the Trakt connection.")
            resp.raise_for_status()
            rows = resp.json() or []
            if not rows:
                break
            for row in rows:
                ev = self._to_event(row)
                if ev is not None:
                    events.append(ev)
            page_count = int(resp.headers.get("X-Pagination-Page-Count", "1") or "1")
            if page >= page_count:
                break
            page += 1
        return events

    @staticmethod
    def _to_event(row: dict) -> NormalizedEvent | None:
        watched_at = _parse_iso(row.get("watched_at"))
        if not watched_at:
            return None
        rtype = row.get("type")
        hist_id = row.get("id")

        if rtype == "movie":
            movie = row.get("movie") or {}
            ids = movie.get("ids") or {}
            return NormalizedEvent(
                raw_title=movie.get("title", ""),
                watched_at=watched_at, kind="movie",
                clean_title=movie.get("title", ""),
                year=movie.get("year"),
                duration_seconds=_runtime_seconds(movie),
                completed=True,
                tmdb_id=ids.get("tmdb"),
                external_ids={k: v for k, v in ids.items() if v is not None},
                metadata={
                    "overview": movie.get("overview"),
                    "genres": _pretty_genres(movie),
                    "runtime_minutes": movie.get("runtime"),
                },
                raw={"source": "trakt", "history_id": hist_id},
            )

        if rtype == "episode":
            episode = row.get("episode") or {}
            show = row.get("show") or {}
            show_ids = show.get("ids") or {}
            return NormalizedEvent(
                raw_title=show.get("title", ""),
                watched_at=watched_at, kind="series",
                clean_title=show.get("title", ""),
                year=show.get("year"),
                season=episode.get("season"),
                episode=episode.get("number"),
                episode_name=episode.get("title"),
                duration_seconds=_runtime_seconds(episode) or _runtime_seconds(show),
                completed=True,
                tmdb_id=show_ids.get("tmdb"),
                external_ids={k: v for k, v in show_ids.items() if v is not None},
                metadata={
                    "overview": show.get("overview"),
                    "genres": _pretty_genres(show),
                    "runtime_minutes": show.get("runtime"),
                },
                raw={"source": "trakt", "history_id": hist_id},
            )

        return None
