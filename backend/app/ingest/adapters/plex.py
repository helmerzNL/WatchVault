"""Plex adapter — direct API sync against a Plex Media Server.

Uses the documented history endpoint:
    GET {base_url}/status/sessions/history/all?X-Plex-Token=...&viewedAt>=since
Config: {"base_url": "http://host:32400", "token": "...", "account_id": optional}
"""
from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

import requests

from .base import SourceAdapter
from ..models import NormalizedEvent


class PlexAdapter(SourceAdapter):
    id = "plex_api"
    ingest_type = "api"
    display_name = "Plex"

    def fetch_history(self, config: dict, cursor: dict) -> tuple[list[NormalizedEvent], dict]:
        base = (config.get("base_url") or "").rstrip("/")
        token = config.get("token")
        if not base or not token:
            raise ValueError("Plex connection requires base_url and token")
        since = int(cursor.get("since", 0))

        params = {
            "X-Plex-Token": token,
            "sort": "viewedAt:asc",
            "viewedAt>": since,
        }
        account_id = config.get("account_id")
        if account_id:
            params["accountID"] = account_id

        resp = requests.get(f"{base}/status/sessions/history/all",
                            params=params, timeout=30,
                            headers={"Accept": "application/xml"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        events: list[NormalizedEvent] = []
        max_viewed = since
        for video in root.findall("Video"):
            viewed_at = int(video.get("viewedAt", "0"))
            if viewed_at <= since:
                continue
            max_viewed = max(max_viewed, viewed_at)
            vtype = video.get("type", "movie")
            watched = dt.datetime.fromtimestamp(viewed_at, tz=dt.timezone.utc)
            duration_ms = video.get("duration")
            duration_s = int(int(duration_ms) / 1000) if duration_ms else None
            if vtype == "episode":
                events.append(NormalizedEvent(
                    raw_title=video.get("grandparentTitle", video.get("title", "")),
                    watched_at=watched, kind="series",
                    clean_title=video.get("grandparentTitle", video.get("title", "")),
                    season=_int(video.get("parentIndex")),
                    episode=_int(video.get("index")),
                    episode_name=video.get("title"),
                    duration_seconds=duration_s, completed=True,
                    raw={"source": "plex", "ratingKey": video.get("ratingKey")},
                ))
            else:
                events.append(NormalizedEvent(
                    raw_title=video.get("title", ""),
                    watched_at=watched, kind="movie",
                    clean_title=video.get("title", ""),
                    year=_int(video.get("year")),
                    duration_seconds=duration_s, completed=True,
                    raw={"source": "plex", "ratingKey": video.get("ratingKey")},
                ))
        return events, {"since": max_viewed}


def _int(value) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
