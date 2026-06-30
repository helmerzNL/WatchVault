"""Cinema adapter — imports films you saw in the cinema from a simple CSV.

The expected format is one film per line as ``date, film title`` (e.g.
``2025-01-12, Dune: Part Two``). A header row is tolerated and skipped. Titles
containing commas are preserved (every non-date cell is rejoined). Each row
becomes a *movie* watch event attributed directly to the Cinema provider; the
``cinema`` source is non-movable, so re-attribution never moves these off the
Cinema platform."""
from __future__ import annotations

import csv
import datetime as dt
import io

from .base import SourceAdapter
from .netflix import parse_date
from ..models import NormalizedEvent

_HEADER_TOKENS = {"date", "datum", "title", "titel", "film", "movie", "naam", "name"}


def _parse_when(value: str) -> dt.datetime | None:
    """Parse an ISO or common day/month/year date, else ``None``."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        pass
    return parse_date(value)


def _cells_to_event(cells: list[str]) -> NormalizedEvent | None:
    cells = [c.strip() for c in cells]
    if not any(cells):
        return None
    # Find the date cell (usually the first); the title is everything else.
    when = None
    title_cells: list[str] = []
    for c in cells:
        if when is None and _parse_when(c):
            when = _parse_when(c)
        else:
            title_cells.append(c)
    title = ", ".join(c for c in title_cells if c).strip()
    if not title:
        return None
    return NormalizedEvent(
        raw_title=title,
        watched_at=when or dt.datetime.now(dt.timezone.utc),
        kind="movie",
        clean_title=title,
        completed=True,
        raw={"source": "cinema"},
    )


class CinemaAdapter(SourceAdapter):
    id = "cinema"
    ingest_type = "csv"
    display_name = "Cinema"

    def import_file(self, content: bytes, filename: str) -> list[NormalizedEvent]:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        events: list[NormalizedEvent] = []
        for row in reader:
            if not row:
                continue
            # Skip an optional header row ('datum, filmtitel' / 'date, title').
            lowered = [c.strip().lower() for c in row]
            if not any(_parse_when(c) for c in row) and any(
                tok in _HEADER_TOKENS for tok in lowered
            ):
                continue
            ev = _cells_to_event(row)
            if ev:
                events.append(ev)
        return events
