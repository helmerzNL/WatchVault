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
    assert {"netflix_csv", "generic", "plex_api", "jellyfin_api", "trakt_api"} <= ids


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


def test_trakt_requires_client_id():
    adapter = get_adapter("trakt_api")
    with pytest.raises(ValueError):
        adapter.fetch_history({"username": "me"}, {})


def test_trakt_event_mapping():
    from app.ingest.adapters.trakt import TraktAdapter
    movie = TraktAdapter._to_event({
        "id": 1, "watched_at": "2025-01-14T20:00:00.000Z", "type": "movie",
        "movie": {"title": "Dune: Part Two", "year": 2024, "runtime": 166,
                  "ids": {"trakt": 9, "tmdb": 693134, "imdb": "tt15239678"}},
    })
    assert movie.item_kind == "movie"
    assert movie.clean_title == "Dune: Part Two"
    assert movie.duration_seconds == 166 * 60
    assert movie.tmdb_id == 693134
    assert movie.external_ids["imdb"] == "tt15239678"
    assert movie.completed is True

    ep = TraktAdapter._to_event({
        "id": 2, "watched_at": "2025-01-15T21:30:00.000Z", "type": "episode",
        "episode": {"season": 2, "number": 5, "title": "The Red Dragon", "runtime": 58},
        "show": {"title": "House of the Dragon", "year": 2022, "ids": {"tmdb": 94997}},
    })
    assert ep.item_kind == "episode"
    assert ep.clean_title == "House of the Dragon"
    assert ep.season == 2 and ep.episode == 5
    assert ep.episode_name == "The Red Dragon"
    assert ep.tmdb_id == 94997


class _FakeResp:
    def __init__(self, *, content: bytes = b"", payload=None, headers=None):
        self.content = content
        self._payload = payload
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_plex_library_filter(monkeypatch):
    from app.ingest.adapters import plex
    xml = (
        b'<MediaContainer>'
        b'<Video type="movie" title="Kept Movie" year="2024" viewedAt="100" '
        b'librarySectionID="1" duration="6000000" ratingKey="a"/>'
        b'<Video type="movie" title="Filtered Movie" year="2024" viewedAt="101" '
        b'librarySectionID="2" duration="6000000" ratingKey="b"/>'
        b'</MediaContainer>'
    )
    monkeypatch.setattr(plex.requests, "get", lambda *a, **k: _FakeResp(content=xml))
    adapter = plex.PlexAdapter()
    events, _ = adapter.fetch_history(
        {"base_url": "http://x", "token": "t", "library_ids": ["1"]}, {})
    assert [e.clean_title for e in events] == ["Kept Movie"]

    all_events, _ = adapter.fetch_history({"base_url": "http://x", "token": "t"}, {})
    assert len(all_events) == 2


def test_plex_list_libraries(monkeypatch):
    from app.ingest.adapters import plex
    xml = (b'<MediaContainer>'
           b'<Directory key="1" title="Movies" type="movie"/>'
           b'<Directory key="2" title="TV" type="show"/>'
           b'</MediaContainer>')
    monkeypatch.setattr(plex.requests, "get", lambda *a, **k: _FakeResp(content=xml))
    libs = plex.PlexAdapter().list_libraries({"base_url": "http://x", "token": "t"})
    assert {l["name"] for l in libs} == {"Movies", "TV"}
    assert {l["id"] for l in libs} == {"1", "2"}


def test_jellyfin_library_scoped_queries(monkeypatch):
    from app.ingest.adapters import jellyfin
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params.get("ParentId"))
        pid = params.get("ParentId")
        return _FakeResp(payload={"Items": [{
            "Id": f"item-{pid}", "Type": "Movie", "Name": f"Movie {pid}",
            "ProductionYear": 2024, "RunTimeTicks": 60_000_000_000,
            "UserData": {"LastPlayedDate": "2025-01-10T10:00:00.000Z", "Played": True},
        }]})

    monkeypatch.setattr(jellyfin.requests, "get", fake_get)
    adapter = jellyfin.JellyfinAdapter()
    events, _ = adapter.fetch_history(
        {"base_url": "http://x", "api_key": "k", "user_id": "u",
         "library_ids": ["libA", "libB"]}, {})
    assert sorted(calls) == ["libA", "libB"]
    assert {e.clean_title for e in events} == {"Movie libA", "Movie libB"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
