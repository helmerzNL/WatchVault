"""Generic CSV/JSON adapter for providers without an official consumer API
(HBO Max, SkyShowtime, Videoland, NLZiet, Disney+, Prime, …).

Auto-detects common column names and tolerates manual exports. Series vs movie
is inferred from a type column or the presence of season/episode fields."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json

from .base import SourceAdapter
from .netflix import parse_date
from ..models import NormalizedEvent

_ALIASES = {
    "title": ["title", "name", "show", "program", "programme", "content_title", "series"],
    "date": ["date", "watched_at", "watched", "timestamp", "viewed_at", "datetime",
             "watched_on", "play_date", "last_watched"],
    "season": ["season", "season_number", "seasonnumber", "s"],
    "episode": ["episode", "episode_number", "episodenumber", "ep", "e"],
    "episode_name": ["episode_title", "episode_name", "episodetitle"],
    "duration": ["duration_seconds", "watched_seconds", "seconds", "duration",
                 "minutes", "runtime", "duration_minutes"],
    "kind": ["type", "kind", "media_type", "content_type"],
    "year": ["year", "release_year", "releaseyear"],
    "progress": ["progress", "percent", "completion", "progress_percent"],
}


def _build_index(fieldnames: list[str]) -> dict:
    lower = {f.lower().strip(): f for f in fieldnames if f}
    idx = {}
    for canon, aliases in _ALIASES.items():
        for a in aliases:
            if a in lower:
                idx[canon] = lower[a]
                break
    return idx


def _to_int(value) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _parse_when(value: str) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    value = str(value).strip()
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        pass
    return parse_date(value) or dt.datetime.now(dt.timezone.utc)


def _duration_seconds(idx_key: str, value) -> int | None:
    if value in (None, ""):
        return None
    n = _to_int(value)
    if n is None:
        return None
    # if the column was a 'minutes'/'runtime' field, scale up
    if idx_key.endswith(("minutes", "runtime")) or "minute" in idx_key:
        return n * 60
    return n


def _row_to_event(row: dict, idx: dict, dur_col: str | None) -> NormalizedEvent | None:
    title = (row.get(idx["title"]) if "title" in idx else "") or ""
    title = str(title).strip()
    if not title:
        return None
    season = _to_int(row.get(idx["season"])) if "season" in idx else None
    episode = _to_int(row.get(idx["episode"])) if "episode" in idx else None
    kind_raw = (str(row.get(idx["kind"])).lower() if "kind" in idx else "")
    is_series = ("series" in kind_raw or "show" in kind_raw or "episode" in kind_raw
                 or "tv" in kind_raw or season is not None or episode is not None)
    duration = None
    if dur_col:
        duration = _duration_seconds(dur_col.lower(), row.get(dur_col))
    progress = None
    if "progress" in idx:
        p = row.get(idx["progress"])
        try:
            progress = float(str(p).replace("%", "").strip())
        except (ValueError, TypeError):
            progress = None
    return NormalizedEvent(
        raw_title=title,
        watched_at=_parse_when(row.get(idx["date"]) if "date" in idx else ""),
        kind="series" if is_series else "movie",
        clean_title=title,
        year=_to_int(row.get(idx["year"])) if "year" in idx else None,
        season=season,
        episode=episode,
        episode_name=(str(row.get(idx["episode_name"])).strip()
                      if "episode_name" in idx else None),
        duration_seconds=duration,
        progress_percent=progress,
        completed=(progress is None or progress >= 90),
        raw={"source": "generic", "row": row},
    )


class GenericAdapter(SourceAdapter):
    id = "generic"
    ingest_type = "json"
    display_name = "Generic CSV/JSON"

    def import_file(self, content: bytes, filename: str) -> list[NormalizedEvent]:
        text = content.decode("utf-8-sig", errors="replace").lstrip()
        if filename.lower().endswith(".json") or text[:1] in "[{":
            return self._from_json(text)
        return self._from_csv(text)

    def _from_csv(self, text: str) -> list[NormalizedEvent]:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return []
        idx = _build_index(reader.fieldnames)
        if "title" not in idx:
            raise ValueError("Could not find a title column in the CSV")
        dur_col = idx.get("duration")
        out = []
        for row in reader:
            ev = _row_to_event(row, idx, dur_col)
            if ev:
                out.append(ev)
        return out

    def _from_json(self, text: str) -> list[NormalizedEvent]:
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("events") or data.get("items") or data.get("history") or []
        if not isinstance(data, list) or not data:
            return []
        keys = list({k for item in data if isinstance(item, dict) for k in item})
        idx = _build_index(keys)
        if "title" not in idx:
            raise ValueError("Could not find a title field in the JSON")
        dur_col = idx.get("duration")
        out = []
        for item in data:
            if isinstance(item, dict):
                ev = _row_to_event(item, idx, dur_col)
                if ev:
                    out.append(ev)
        return out
