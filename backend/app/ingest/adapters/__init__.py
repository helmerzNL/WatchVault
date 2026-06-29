"""Adapter registry — the single place adapters are registered. Adding a new
provider is just implementing SourceAdapter and registering it here."""
from __future__ import annotations

from .base import SourceAdapter
from .generic import GenericAdapter
from .jellyfin import JellyfinAdapter
from .netflix import NetflixAdapter
from .plex import PlexAdapter

_ADAPTERS: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> None:
    _ADAPTERS[adapter.id] = adapter


for _a in (NetflixAdapter(), GenericAdapter(), PlexAdapter(), JellyfinAdapter()):
    register(_a)


def get_adapter(adapter_id: str) -> SourceAdapter:
    if adapter_id not in _ADAPTERS:
        raise KeyError(f"Unknown adapter: {adapter_id}")
    return _ADAPTERS[adapter_id]


def list_adapters() -> list[SourceAdapter]:
    return list(_ADAPTERS.values())
