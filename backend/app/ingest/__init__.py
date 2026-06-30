"""Ingestion package: provider adapters + normalization into the central model."""
from .models import NormalizedEvent
from .normalize import (ingest_events, prune_connection_libraries,
                        clear_connection_events, reset_all_data)
from .trakt_sync import (find_trakt_connection, trakt_configured,
                         ingest_title_from_trakt, enqueue_trakt_title_syncs)

__all__ = ["NormalizedEvent", "ingest_events", "prune_connection_libraries",
           "clear_connection_events", "reset_all_data",
           "find_trakt_connection", "trakt_configured",
           "ingest_title_from_trakt", "enqueue_trakt_title_syncs"]
