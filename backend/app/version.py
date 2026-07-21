"""Canonical application version sourced from the repository or image root."""
from __future__ import annotations

import re
from pathlib import Path

_STABLE_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_VERSION_PATH = Path(__file__).resolve().parents[2] / "VERSION"


def read_version(path: Path = _VERSION_PATH) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not _STABLE_SEMVER.fullmatch(value):
        raise RuntimeError(f"Invalid stable SemVer in {path}")
    return value


VERSION = read_version()
