"""Provider-adapter pattern.

Every streaming source is a small adapter implementing a common interface so
new providers can be added without touching core logic:

    import_file(content, filename) -> list[NormalizedEvent]   # CSV/JSON sources
    fetch_history(config, cursor)  -> (list[NormalizedEvent], new_cursor)  # API
"""
from __future__ import annotations

from ..models import NormalizedEvent


class SourceAdapter:
    id: str = "base"
    ingest_type: str = "csv"            # 'csv' | 'json' | 'api'
    display_name: str = "Base"

    def import_file(self, content: bytes, filename: str) -> list[NormalizedEvent]:
        raise NotImplementedError(f"{self.id} does not support file import")

    def fetch_history(self, config: dict, cursor: dict) -> tuple[list[NormalizedEvent], dict]:
        raise NotImplementedError(f"{self.id} does not support API sync")
