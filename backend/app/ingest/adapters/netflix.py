"""Netflix adapter — parses the official 'Viewing activity' CSV export
(Account → Profile → Viewing activity → Download all). Format: Title,Date."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

from .base import SourceAdapter
from ..models import NormalizedEvent
from ...util import normalize_text

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


def _series_prefixes(items: list[tuple[str, dict]]) -> set[str]:
    """Learn which 'Show:' prefixes denote a series within one export. A prefix
    qualifies when an explicit season/part marker already identified it as a
    series, or when the same prefix appears with two or more distinct remainders.
    Netflix often exports a series' episodes as 'Show: Episode' with no season
    marker, which on its own is indistinguishable from a movie subtitle (e.g.
    'Glass Onion: A Knives Out Mystery'); the repetition of the prefix across
    different episodes is what reveals it as a series."""
    prefixes: set[str] = set()
    variants: dict[str, set[str]] = {}
    for title, parsed in items:
        if parsed["is_series"]:
            key = normalize_text(parsed["clean"])
            if key:
                prefixes.add(key)
        if ":" in title:
            pre, rem = title.split(":", 1)
            key = normalize_text(pre)
            if key:
                variants.setdefault(key, set()).add(normalize_text(rem))
    for pre, rems in variants.items():
        if len(rems) >= 2:
            prefixes.add(pre)
    return prefixes


def _group_episode(title: str, parsed: dict, series_prefixes: set[str]) -> dict:
    """Promote a 2-part 'Show: Episode' row that the basic parser left as a movie
    to a series episode when its prefix is a known series, so all of a show's
    episodes collapse onto one title instead of creating one title per episode."""
    if parsed["is_series"] or ":" not in title:
        return parsed
    pre, rem = title.split(":", 1)
    if pre.strip() and normalize_text(pre) in series_prefixes:
        return {"clean": pre.strip(), "season": None,
                "episode_name": rem.strip() or None, "is_series": True}
    return parsed


class NetflixAdapter(SourceAdapter):
    id = "netflix_csv"
    ingest_type = "csv"
    display_name = "Netflix"

    def import_file(self, content: bytes, filename: str) -> list[NormalizedEvent]:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        # First pass: parse every row, so we can learn which colon-prefixes are
        # series before deciding how to classify the ambiguous 'Show: Episode'
        # rows. Without this, those episodes each become a standalone movie.
        rows: list[tuple[str, dt.datetime, dict, dict]] = []
        for row in reader:
            # tolerate header casing / extra columns
            title = (row.get("Title") or row.get("title") or "").strip()
            date_raw = (row.get("Date") or row.get("date") or "").strip()
            if not title:
                continue
            watched = parse_date(date_raw) or dt.datetime.now(dt.timezone.utc)
            rows.append((title, watched, row, parse_title(title)))

        series_prefixes = _series_prefixes([(t, p) for (t, _w, _r, p) in rows])

        events: list[NormalizedEvent] = []
        for title, watched, row, parsed in rows:
            parsed = _group_episode(title, parsed, series_prefixes)
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
