"""Trakt adapter — direct API sync against the official Trakt.tv API.

Trakt has a well-documented REST API. Watch history is read from:

    GET https://api.trakt.tv/users/{username}/history?page=&limit=&start_at=&extended=full

Required headers: ``trakt-api-version: 2`` and ``trakt-api-key: {client_id}``.
A private profile additionally needs an OAuth ``Authorization: Bearer {access_token}``
(use username ``me`` in that case); a public profile works with the client id alone.

Config: {"client_id": "...", "access_token": "...(optional)", "username": "me"}
"""
from __future__ import annotations

import datetime as dt

import requests

from .base import SourceAdapter
from ..models import NormalizedEvent

API_BASE = "https://api.trakt.tv"
PAGE_LIMIT = 100
MAX_PAGES = 25          # cap one sync at 2500 events; cursor makes the next sync incremental


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
        {"key": "username", "label": "Username", "type": "text", "required": True,
         "placeholder": "me", "help": "Your Trakt username, or 'me' when using an access token."},
        {"key": "access_token", "label": "Access token", "type": "password", "required": False,
         "placeholder": "OAuth access token (private history only)",
         "help": "Only needed if your Trakt profile/history is private."},
    ]

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
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        since = _parse_iso(cursor.get("since")) or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

        events: list[NormalizedEvent] = []
        max_watched = since
        page = 1
        while page <= MAX_PAGES:
            resp = requests.get(
                f"{API_BASE}/users/{username}/history",
                params={
                    "page": page,
                    "limit": PAGE_LIMIT,
                    "start_at": since.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "extended": "full",
                },
                headers=headers,
                timeout=30,
            )
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
