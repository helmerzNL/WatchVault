"""Ingestion package: provider adapters + normalization into the central model."""
from .models import NormalizedEvent
from .normalize import ingest_events

__all__ = ["NormalizedEvent", "ingest_events"]
