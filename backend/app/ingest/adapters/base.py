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
    # Per-adapter connection config schema (API adapters). Each field:
    #   {"key", "label", "type": 'text'|'password'|'url', "placeholder", "required", "help"}
    config_fields: list[dict] = []

    def import_file(self, content: bytes, filename: str) -> list[NormalizedEvent]:
        raise NotImplementedError(f"{self.id} does not support file import")

    def fetch_history(self, config: dict, cursor: dict) -> tuple[list[NormalizedEvent], dict]:
        raise NotImplementedError(f"{self.id} does not support API sync")

    def fetch_title_history(self, config: dict, title_ref: dict) -> list[NormalizedEvent]:
        """Fetch the full watch history for a single title from this source.

        ``title_ref`` carries what we know about the local title — at minimum
        ``{"kind": 'movie'|'series', "tmdb_id": int|None, "external_ids": dict}`` —
        so the adapter can resolve it to its own id and return every watch event
        for just that title. Used for per-title cross-sync (e.g. enriching a Plex
        series with episodes only known to Trakt). Adapters that can't scope a
        fetch to one title keep the default (unsupported).
        """
        raise NotImplementedError(f"{self.id} does not support per-title history")

    def list_libraries(self, config: dict) -> list[dict]:
        """Discover selectable libraries for this connection.

        Returns ``[{"id": str, "name": str, "type": str}]``. Adapters whose
        source has no concept of libraries can leave the default (none).
        """
        return []

    def library_prune_spec(self, config: dict) -> tuple[str, set[str]] | None:
        """Describe how to prune watch events to the selected library subset.

        Returns ``(raw_key, selected_ids)`` where ``raw_key`` is the JSON key each
        event records its source library under (in ``raw``) and ``selected_ids`` is
        the set of libraries to keep. Returns ``None`` when no subset is selected
        (i.e. all libraries are kept, nothing to prune). Adapters without libraries
        keep the default (no pruning).
        """
        return None

    def prepare_config(self, config: dict) -> tuple[dict, bool]:
        """Hook to refresh/rotate credentials right before a sync.

        Returns ``(config, changed)``. When ``changed`` is True the caller persists
        the returned config back to the connection (e.g. rotated OAuth tokens).
        Adapters with static credentials keep the default (no change).
        """
        return config, False

