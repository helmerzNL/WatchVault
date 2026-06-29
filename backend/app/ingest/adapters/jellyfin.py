"""Jellyfin adapter — direct API sync.

Pulls played items with their UserData via the documented Items endpoint:
    GET {base_url}/Users/{user_id}/Items?IsPlayed=true&Recursive=true...
Config: {"base_url": "http://host:8096", "api_key": "...", "user_id": "..."}
"""
from __future__ import annotations

import datetime as dt

import requests

from .base import SourceAdapter
from ..models import NormalizedEvent


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


class JellyfinAdapter(SourceAdapter):
    id = "jellyfin_api"
    ingest_type = "api"
    display_name = "Jellyfin"

    def fetch_history(self, config: dict, cursor: dict) -> tuple[list[NormalizedEvent], dict]:
        base = (config.get("base_url") or "").rstrip("/")
        api_key = config.get("api_key")
        user_id = config.get("user_id")
        if not base or not api_key or not user_id:
            raise ValueError("Jellyfin connection requires base_url, api_key and user_id")
        since = _parse_iso(cursor.get("since")) or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

        resp = requests.get(
            f"{base}/Users/{user_id}/Items",
            params={
                "IsPlayed": "true",
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Episode",
                "Fields": "UserData,ProductionYear,RunTimeTicks",
                "SortBy": "DatePlayed",
                "SortOrder": "Ascending",
                "Limit": 5000,
            },
            headers={"X-Emby-Token": api_key, "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("Items", [])

        events: list[NormalizedEvent] = []
        max_played = since
        for item in items:
            ud = item.get("UserData", {})
            played_at = _parse_iso(ud.get("LastPlayedDate"))
            if not played_at or played_at <= since:
                continue
            max_played = max(max_played, played_at)
            ticks = item.get("RunTimeTicks")
            duration_s = int(ticks / 10_000_000) if ticks else None
            if item.get("Type") == "Episode":
                events.append(NormalizedEvent(
                    raw_title=item.get("SeriesName", item.get("Name", "")),
                    watched_at=played_at, kind="series",
                    clean_title=item.get("SeriesName", item.get("Name", "")),
                    season=item.get("ParentIndexNumber"),
                    episode=item.get("IndexNumber"),
                    episode_name=item.get("Name"),
                    duration_seconds=duration_s, completed=bool(ud.get("Played")),
                    raw={"source": "jellyfin", "id": item.get("Id")},
                ))
            else:
                events.append(NormalizedEvent(
                    raw_title=item.get("Name", ""),
                    watched_at=played_at, kind="movie",
                    clean_title=item.get("Name", ""),
                    year=item.get("ProductionYear"),
                    duration_seconds=duration_s, completed=bool(ud.get("Played")),
                    raw={"source": "jellyfin", "id": item.get("Id")},
                ))
        return events, {"since": max_played.isoformat()}
