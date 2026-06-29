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


def _movie_metadata(item: dict) -> dict:
    """Capture Jellyfin-native metadata for a movie (cast/crew from People)."""
    people = item.get("People") or []
    cast = [{"name": p.get("Name"), "character": p.get("Role"), "ord": i}
            for i, p in enumerate(people) if p.get("Type") == "Actor" and p.get("Name")]
    crew = [{"name": p.get("Name"), "job": p.get("Type")}
            for p in people if p.get("Type") in ("Director", "Writer") and p.get("Name")]
    return {
        "overview": item.get("Overview"),
        "original_title": item.get("OriginalTitle") or None,
        "genres": item.get("Genres") or [],
        "cast": cast[:15],
        "crew": crew,
    }


class JellyfinAdapter(SourceAdapter):
    id = "jellyfin_api"
    ingest_type = "api"
    display_name = "Jellyfin"
    config_fields = [
        {"key": "base_url", "label": "Server URL", "type": "url", "required": True,
         "placeholder": "http://192.168.1.10:8096"},
        {"key": "api_key", "label": "API key", "type": "password", "required": True,
         "placeholder": "Jellyfin API key", "help": "Dashboard → Advanced → API Keys."},
        {"key": "user_id", "label": "User ID", "type": "text", "required": True,
         "placeholder": "Jellyfin user ID", "help": "The user whose history to sync."},
        {"key": "library_ids", "label": "Libraries", "type": "library_select", "required": False,
         "help": "Only sync watch history from these libraries. Leave empty for all."},
    ]

    def _library_ids(self, config: dict) -> list[str]:
        lib = config.get("library_ids")
        if not lib:
            return []
        if isinstance(lib, str):
            lib = [lib]
        return [str(s) for s in lib if str(s).strip()]

    def list_libraries(self, config: dict) -> list[dict]:
        base = (config.get("base_url") or "").rstrip("/")
        api_key = config.get("api_key")
        user_id = config.get("user_id")
        if not base or not api_key or not user_id:
            raise ValueError("Jellyfin connection requires base_url, api_key and user_id")
        resp = requests.get(
            f"{base}/Users/{user_id}/Views",
            headers={"X-Emby-Token": api_key, "Accept": "application/json"},
            timeout=20,
        )
        resp.raise_for_status()
        out = []
        for v in resp.json().get("Items", []):
            out.append({"id": v.get("Id"), "name": v.get("Name", "Library"),
                        "type": v.get("CollectionType", "")})
        return out

    def _fetch_items(self, base: str, api_key: str, user_id: str, parent_id: str | None) -> list[dict]:
        params = {
            "IsPlayed": "true",
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Episode",
            "Fields": "UserData,ProductionYear,RunTimeTicks,Genres,Overview,People,OriginalTitle",
            "SortBy": "DatePlayed",
            "SortOrder": "Ascending",
            "Limit": 5000,
        }
        if parent_id:
            params["ParentId"] = parent_id
        resp = requests.get(
            f"{base}/Users/{user_id}/Items",
            params=params,
            headers={"X-Emby-Token": api_key, "Accept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("Items", [])

    def fetch_history(self, config: dict, cursor: dict) -> tuple[list[NormalizedEvent], dict]:
        base = (config.get("base_url") or "").rstrip("/")
        api_key = config.get("api_key")
        user_id = config.get("user_id")
        if not base or not api_key or not user_id:
            raise ValueError("Jellyfin connection requires base_url, api_key and user_id")
        since = _parse_iso(cursor.get("since")) or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

        library_ids = self._library_ids(config)
        if library_ids:
            items, seen = [], set()
            for pid in library_ids:
                for it in self._fetch_items(base, api_key, user_id, pid):
                    iid = it.get("Id")
                    if iid in seen:
                        continue
                    seen.add(iid)
                    items.append(it)
        else:
            items = self._fetch_items(base, api_key, user_id, None)

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
                    metadata={"overview": item.get("Overview"),
                              "genres": item.get("Genres") or []},
                    raw={"source": "jellyfin", "id": item.get("Id")},
                ))
            else:
                events.append(NormalizedEvent(
                    raw_title=item.get("Name", ""),
                    watched_at=played_at, kind="movie",
                    clean_title=item.get("Name", ""),
                    year=item.get("ProductionYear"),
                    duration_seconds=duration_s, completed=bool(ud.get("Played")),
                    metadata=_movie_metadata(item),
                    raw={"source": "jellyfin", "id": item.get("Id")},
                ))
        return events, {"since": max_played.isoformat()}
