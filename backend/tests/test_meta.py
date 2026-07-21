"""Public metadata endpoints expose the canonical runtime version."""
import pathlib
import sys
from unittest.mock import patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import create_app  # noqa: E402
from app.api import meta  # noqa: E402
from app.version import VERSION, read_version  # noqa: E402


def test_runtime_version_matches_root_version():
    assert VERSION == "1.0.1"
    assert VERSION == (ROOT / "VERSION").read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("value", ["", "1.0", "1.0.1-beta.1", "v1.0.1"])
def test_runtime_version_rejects_invalid_values(value):
    candidate = pathlib.Path("VERSION")
    with pytest.raises(RuntimeError, match="stable SemVer"):
        with patch.object(pathlib.Path, "read_text", return_value=value):
            read_version(candidate)


def test_health_and_config_preserve_shape(monkeypatch):
    monkeypatch.setattr(meta, "query_one", lambda _query: {"ok": 1})
    client = create_app().test_client()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.get_json() == {"status": "ok", "db": True, "version": "1.0.1"}

    config = client.get("/api/meta/config")
    assert config.status_code == 200
    assert config.get_json() == {
        "version": "1.0.1",
        "rp_id": meta.get_config().RP_ID,
        "app": meta.get_config().RP_NAME,
    }
