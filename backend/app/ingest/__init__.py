"""Ingestion package: provider adapters + normalization into the central model."""
from .models import NormalizedEvent
from .normalize import (ingest_events, prune_connection_libraries,
                        clear_connection_events, reset_all_data)
from .trakt_sync import (find_trakt_connection, trakt_configured,
                         ingest_title_from_trakt, enqueue_trakt_title_syncs)
from .manual import (add_manual_movie, add_manual_episode, add_manual_season,
                     delete_episode_watch, delete_movie_watch)
from .scrobble import (ScrobbleEvent, parse_plex_payload, parse_generic_payload,
                       handle_scrobble, expire_stale_sessions)

__all__ = ["NormalizedEvent", "ingest_events", "prune_connection_libraries",
           "clear_connection_events", "reset_all_data",
           "find_trakt_connection", "trakt_configured",
           "ingest_title_from_trakt", "enqueue_trakt_title_syncs",
           "add_manual_movie", "add_manual_episode", "add_manual_season",
           "delete_episode_watch", "delete_movie_watch",
           "ScrobbleEvent", "parse_plex_payload", "parse_generic_payload",
           "handle_scrobble", "expire_stale_sessions"]
