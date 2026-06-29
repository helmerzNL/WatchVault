"""Normalized event model shared by every provider adapter."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalizedEvent:
    """One watch event, provider-agnostic, ready for the central model."""
    raw_title: str
    watched_at: dt.datetime
    kind: str = "movie"                 # 'movie' | 'series'
    clean_title: Optional[str] = None   # series/movie name without markers
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    progress_percent: Optional[float] = None
    completed: bool = False
    tmdb_id: Optional[int] = None
    external_ids: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @property
    def item_kind(self) -> str:
        if self.kind == "series" or self.season is not None or self.episode is not None:
            return "episode"
        return "movie"

    @property
    def title_kind(self) -> str:
        return "series" if self.item_kind == "episode" else "movie"
