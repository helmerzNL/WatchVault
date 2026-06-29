"""Netflix adapter — parses the official 'Viewing activity' CSV export
(Account → Profile → Viewing activity → Download all). Format: Title,Date."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

from .base import SourceAdapter
from ..models import NormalizedEvent

_MARKER = re.compile(
    r"\b(?:season|seizoen|part|deel|volume|vol|limited series|chapter|book|series)\b\s*(\d+)?",
    re.IGNORECASE,
)
_DATE_FORMATS = ["%m/%d/%y", "%m/%d/%Y", "%d/%m/%Y", "%d/%m/%y",
                 "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"]


def parse_date(value: str) -> dt.datetime | None:
    value = (value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            d = dt.datetime.strptime(value, fmt)
            return d.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def parse_title(title: str) -> dict:
    parts = [p.strip() for p in title.split(":")]
    clean, season, episode_name, is_series = title.strip(), None, None, False
    marker_idx = None
    for i, p in enumerate(parts[1:], start=1):
        m = _MARKER.search(p)
        if m:
            marker_idx = i
            season = int(m.group(1)) if m.group(1) else 1
            break
    if marker_idx is not None:
        is_series = True
        clean = ": ".join(parts[:marker_idx]).strip() or parts[0]
        tail = parts[marker_idx + 1:]
        episode_name = ": ".join(tail).strip() or None
    elif len(parts) >= 3:
        is_series = True
        clean = parts[0]
        episode_name = ": ".join(parts[1:]).strip()
    return {"clean": clean, "season": season,
            "episode_name": episode_name, "is_series": is_series}


class NetflixAdapter(SourceAdapter):
    id = "netflix_csv"
    ingest_type = "csv"
    display_name = "Netflix"

    def import_file(self, content: bytes, filename: str) -> list[NormalizedEvent]:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        events: list[NormalizedEvent] = []
        for row in reader:
            # tolerate header casing / extra columns
            title = (row.get("Title") or row.get("title") or "").strip()
            date_raw = (row.get("Date") or row.get("date") or "").strip()
            if not title:
                continue
            watched = parse_date(date_raw) or dt.datetime.now(dt.timezone.utc)
            parsed = parse_title(title)
            events.append(NormalizedEvent(
                raw_title=title,
                watched_at=watched,
                kind="series" if parsed["is_series"] else "movie",
                clean_title=parsed["clean"],
                season=parsed["season"],
                episode_name=parsed["episode_name"],
                completed=True,
                raw={"source": "netflix_csv", "row": row},
            ))
        return events
