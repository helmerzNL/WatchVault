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
    config_fields = [
        {"key": "base_url", "label": "Server URL", "type": "url", "required": True,
         "placeholder": "http://192.168.1.10:32400"},
        {"key": "token", "label": "Plex token", "type": "password", "required": True,
         "placeholder": "X-Plex-Token", "help": "Settings → Account → API token (X-Plex-Token)."},
        {"key": "account_id", "label": "Account ID", "type": "text", "required": False,
         "placeholder": "Restrict to one Plex account (optional)"},
        {"key": "library_ids", "label": "Libraries", "type": "library_select", "required": False,
         "help": "Only sync watch history from these libraries. Leave empty for all."},
    ]

    def _section_id(self, config: dict):
        sid = config.get("library_ids")
        if not sid:
            return None
        if isinstance(sid, str):
            sid = [sid]
        return {str(s) for s in sid if str(s).strip()}

    def list_libraries(self, config: dict) -> list[dict]:
        base = (config.get("base_url") or "").rstrip("/")
        token = config.get("token")
        if not base or not token:
            raise ValueError("Plex connection requires base_url and token")
        resp = requests.get(f"{base}/library/sections",
                            params={"X-Plex-Token": token}, timeout=20,
                            headers={"Accept": "application/xml"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        out = []
        for d in root.findall("Directory"):
            out.append({"id": d.get("key"), "name": d.get("title", "Library"),
                        "type": d.get("type", "")})
        return out

    def fetch_history(self, config: dict, cursor: dict) -> tuple[list[NormalizedEvent], dict]:
        base = (config.get("base_url") or "").rstrip("/")
        token = config.get("token")
        if not base or not token:
            raise ValueError("Plex connection requires base_url and token")
        since = int(cursor.get("since", 0))
        sections = self._section_id(config)

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

        meta_cache: dict[str, dict] = {}
        events: list[NormalizedEvent] = []
        max_viewed = since
        for video in root.findall("Video"):
            if sections and video.get("librarySectionID") not in sections:
                continue
            viewed_at = int(video.get("viewedAt", "0"))
            if viewed_at <= since:
                continue
            max_viewed = max(max_viewed, viewed_at)
            vtype = video.get("type", "movie")
            watched = dt.datetime.fromtimestamp(viewed_at, tz=dt.timezone.utc)
            duration_ms = video.get("duration")
            duration_s = int(int(duration_ms) / 1000) if duration_ms else None
            if vtype == "episode":
                meta_key = video.get("grandparentRatingKey")
                events.append(NormalizedEvent(
                    raw_title=video.get("grandparentTitle", video.get("title", "")),
                    watched_at=watched, kind="series",
                    clean_title=video.get("grandparentTitle", video.get("title", "")),
                    season=_int(video.get("parentIndex")),
                    episode=_int(video.get("index")),
                    episode_name=video.get("title"),
                    duration_seconds=duration_s, completed=True,
                    metadata=self._title_metadata(base, token, meta_key, meta_cache, "series"),
                    raw={"source": "plex", "ratingKey": video.get("ratingKey")},
                ))
            else:
                events.append(NormalizedEvent(
                    raw_title=video.get("title", ""),
                    watched_at=watched, kind="movie",
                    clean_title=video.get("title", ""),
                    year=_int(video.get("year")),
                    duration_seconds=duration_s, completed=True,
                    metadata=self._title_metadata(base, token, video.get("ratingKey"), meta_cache, "movie"),
                    raw={"source": "plex", "ratingKey": video.get("ratingKey")},
                ))
        return events, {"since": max_viewed}

    def _title_metadata(self, base: str, token: str, rating_key: str | None,
                        cache: dict, kind: str) -> dict:
        """Fetch Plex-native metadata for a title (cached per ratingKey).
        Best-effort: a failed call just yields no extra metadata."""
        if not rating_key:
            return {}
        if rating_key in cache:
            return cache[rating_key]
        md: dict = {}
        try:
            resp = requests.get(f"{base}/library/metadata/{rating_key}",
                                params={"X-Plex-Token": token}, timeout=20,
                                headers={"Accept": "application/xml"})
            if getattr(resp, "status_code", 200) == 200:
                root = ET.fromstring(resp.content)
                node = root.find("Directory") or root.find("Video")
                if node is not None:
                    md = _parse_metadata(node)
        except Exception:  # noqa: BLE001 — best-effort, never break a sync
            md = {}
        cache[rating_key] = md
        return md


def _int(value) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_metadata(node) -> dict:
    """Extract WatchVault-shaped metadata from a Plex <Video>/<Directory> node."""
    genres = [g.get("tag") for g in node.findall("Genre") if g.get("tag")]
    cast = [{"name": r.get("tag"), "character": r.get("role"), "ord": i}
            for i, r in enumerate(node.findall("Role")) if r.get("tag")]
    crew = [{"name": d.get("tag"), "job": "Director"} for d in node.findall("Director") if d.get("tag")]
    crew += [{"name": w.get("tag"), "job": "Writer"} for w in node.findall("Writer") if w.get("tag")]
    duration_ms = node.get("duration")
    runtime_minutes = round(int(duration_ms) / 60000) if duration_ms and duration_ms.isdigit() else None
    return {
        "overview": node.get("summary") or None,
        "original_title": node.get("originalTitle") or None,
        "genres": genres,
        "cast": cast[:15],
        "crew": crew,
        "runtime_minutes": runtime_minutes,
    }
