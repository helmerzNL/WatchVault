"""Adapter parsing tests — no database required. Run with: pytest backend/tests

These exercise the provider-adapter pattern's normalization layer against the
bundled sample exports so a regression in title/episode parsing is caught early.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.adapters import get_adapter, list_adapters  # noqa: E402

SAMPLES = ROOT / "sample-data"


def _load(adapter_id: str, filename: str):
    data = (SAMPLES / filename).read_bytes()
    return get_adapter(adapter_id).import_file(data, filename)


def test_registry_has_core_adapters():
    ids = {a.id for a in list_adapters()}
    assert {"netflix_csv", "generic", "plex_api", "jellyfin_api"} <= ids


def test_netflix_series_vs_movie():
    events = _load("netflix_csv", "netflix-viewing-activity.csv")
    assert len(events) == 15

    st = [e for e in events if e.clean_title == "Stranger Things"]
    assert st and all(e.item_kind == "episode" and e.season == 4 for e in st)
    assert st[0].episode_name == "Chapter One: The Hellfire Club"

    irishman = [e for e in events if e.clean_title == "The Irishman"]
    assert irishman and irishman[0].item_kind == "movie"


def test_generic_csv_minutes_scaled_to_seconds():
    events = _load("generic", "hbomax-generic.csv")
    assert len(events) == 7
    dune = next(e for e in events if e.clean_title == "Dune: Part Two")
    assert dune.item_kind == "movie"
    assert dune.duration_seconds == 166 * 60

    hotd = [e for e in events if e.clean_title == "House of the Dragon"]
    assert hotd and all(e.season == 2 for e in hotd)


def test_generic_json_dutch_providers():
    events = _load("generic", "videoland-generic.json")
    assert len(events) == 3
    assert any(e.clean_title == "Flikken Maastricht" and e.season == 18 for e in events)
    de_oost = next(e for e in events if e.clean_title == "De Oost")
    assert de_oost.item_kind == "movie"
    assert de_oost.progress_percent == 88
    assert de_oost.completed is False  # < 90% progress


def test_netflix_date_parsing_variants():
    from app.ingest.adapters.netflix import parse_date
    assert parse_date("01/14/2025") is not None
    assert parse_date("2025-01-14") is not None
    assert parse_date("14-01-2025") is not None
    assert parse_date("not a date") is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
