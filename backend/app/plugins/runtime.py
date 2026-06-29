"""Folder + manifest plugin runtime.

Discovers plugin folders under PLUGINS_DIR, validates each manifest, and
dispatches capability calls. Per-plugin settings & secrets live in the DB
(plugins table, jsonb) so API keys stay out of code. Built-ins are registered
in the DB as non-deletable system plugins.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
from typing import Any, Optional

from ..config import get_config
from ..db import query_all, query_one, execute

PLUGINS_DIR = pathlib.Path(
    os.environ.get("PLUGINS_DIR")
    or (pathlib.Path(__file__).resolve().parents[3] / "plugins")
)

_INSTANCES: dict[str, Any] = {}
_MANIFESTS: dict[str, dict] = {}


def discover() -> dict[str, dict]:
    """Scan plugin folders and read manifests (no instantiation yet)."""
    _MANIFESTS.clear()
    if not PLUGINS_DIR.exists():
        return _MANIFESTS
    for folder in sorted(PLUGINS_DIR.iterdir()):
        manifest = folder / "manifest.json"
        if folder.is_dir() and manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                data["_folder"] = str(folder)
                _MANIFESTS[data["id"]] = data
            except (json.JSONDecodeError, KeyError):
                continue
    return _MANIFESTS


def _db_row(plugin_id: str) -> Optional[dict]:
    return query_one("SELECT * FROM plugins WHERE id = %s", (plugin_id,))


def _resolve_secrets(plugin_id: str, manifest: dict) -> dict:
    row = _db_row(plugin_id)
    secrets = dict(row["secrets"]) if row and row.get("secrets") else {}
    # env fallback for the reference TMDB key
    cfg = get_config()
    if plugin_id == "tmdb" and not secrets.get("api_key") and cfg.TMDB_API_KEY:
        secrets["api_key"] = cfg.TMDB_API_KEY
    return secrets


def get_plugin(plugin_id: str):
    """Instantiate (and cache) a plugin's Plugin class with its settings+secrets."""
    if not _MANIFESTS:
        discover()
    if plugin_id not in _MANIFESTS:
        raise KeyError(f"Plugin not found: {plugin_id}")
    manifest = _MANIFESTS[plugin_id]
    row = _db_row(plugin_id)
    if row and not row["enabled"]:
        raise RuntimeError(f"Plugin disabled: {plugin_id}")

    settings = dict(row["settings"]) if row and row.get("settings") else {}
    secrets = _resolve_secrets(plugin_id, manifest)

    cache_key = f"{plugin_id}:{hash(json.dumps(secrets, sort_keys=True))}"
    if cache_key in _INSTANCES:
        return _INSTANCES[cache_key]

    module_path = pathlib.Path(manifest["_folder"]) / "plugin.py"
    spec = importlib.util.spec_from_file_location(f"wv_plugin_{plugin_id}", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    instance = module.Plugin(settings=settings, secrets=secrets)
    _INSTANCES.clear()
    _INSTANCES[cache_key] = instance
    return instance


def is_configured(plugin_id: str) -> bool:
    try:
        plugin = get_plugin(plugin_id)
        return bool(getattr(plugin, "configured", True))
    except Exception:  # noqa: BLE001
        return False


def capability_providers(capability: str) -> list[str]:
    """Which enabled plugins implement a capability."""
    if not _MANIFESTS:
        discover()
    out = []
    for pid, manifest in _MANIFESTS.items():
        if capability in manifest.get("capabilities", []):
            row = _db_row(pid)
            if not row or row["enabled"]:
                out.append(pid)
    return out


def set_secrets(plugin_id: str, secrets: dict) -> None:
    execute(
        "UPDATE plugins SET secrets = secrets || %s::jsonb, updated_at = now() WHERE id = %s",
        (json.dumps(secrets), plugin_id),
    )
    _INSTANCES.clear()


def set_enabled(plugin_id: str, enabled: bool) -> None:
    execute("UPDATE plugins SET enabled = %s, updated_at = now() WHERE id = %s",
            (enabled, plugin_id))
    _INSTANCES.clear()
