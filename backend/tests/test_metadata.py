"""Metadata + multilingual mapping tests — no database or network required."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def _tmdb_plugin():
    spec = importlib.util.spec_from_file_location(
        "wv_tmdb_test", ROOT / "plugins" / "tmdb" / "plugin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Plugin(settings={"language": "en-US"}, secrets={"api_key": "x"})


def test_tmdb_movie_multilingual_overviews():
    plugin = _tmdb_plugin()
    data = {
        "id": 693134, "title": "Dune: Part Two", "original_title": "Dune: Part Two",
        "overview": "English overview.", "release_date": "2024-02-27", "runtime": 166,
        "poster_path": "/p.jpg", "backdrop_path": "/b.jpg",
        "genres": [{"name": "Science Fiction"}, {"name": "Adventure"}],
        "credits": {
            "cast": [{"id": 1, "name": "Timothée Chalamet", "character": "Paul",
                      "order": 0, "profile_path": "/t.jpg"}],
            "crew": [{"id": 2, "name": "Denis Villeneuve", "job": "Director",
                      "profile_path": "/d.jpg"},
                     {"id": 3, "name": "Grip", "job": "Best Boy"}],
        },
        "translations": {"translations": [
            {"iso_639_1": "nl", "data": {"overview": "Nederlandse samenvatting."}},
            {"iso_639_1": "fr", "data": {"overview": "Résumé français."}},
            {"iso_639_1": "de", "data": {"overview": "Deutsche Beschreibung."}},
            {"iso_639_1": "es", "data": {"overview": ""}},  # empty -> skipped
            {"iso_639_1": "pt", "data": {"overview": "ignored"}},  # not a target lang
        ]},
    }
    details = plugin._normalize(data, "movie")
    assert details["year"] == 2024
    assert details["runtime_minutes"] == 166
    ov = details["overviews"]
    assert ov["en"] == "English overview."
    assert ov["nl"] == "Nederlandse samenvatting."
    assert ov["fr"] == "Résumé français."
    assert ov["de"] == "Deutsche Beschreibung."
    assert "es" not in ov and "pt" not in ov
    assert details["overview"] == "English overview."
    assert details["genres"] == ["Science Fiction", "Adventure"]
    assert [c["name"] for c in details["cast"]] == ["Timothée Chalamet"]
    # crew filtered to Director/Creator/Writer only
    assert [c["name"] for c in details["crew"]] == ["Denis Villeneuve"]
    assert details["authoritative"] is True


def test_tmdb_person_multilingual_biographies():
    plugin = _tmdb_plugin()
    data = {
        "id": 1190668, "name": "Timothée Chalamet", "biography": "English bio.",
        "birthday": "1995-12-27", "deathday": None, "place_of_birth": "New York City",
        "known_for_department": "Acting", "profile_path": "/t.jpg",
        "also_known_as": ["Timmy"],
        "translations": {"translations": [
            {"iso_639_1": "nl", "data": {"biography": "Nederlandse biografie."}},
            {"iso_639_1": "it", "data": {"biography": "Biografia italiana."}},
        ]},
    }
    p = plugin._normalize_person(data)
    assert p["name"] == "Timothée Chalamet"
    assert p["birthday"] == "1995-12-27"
    assert p["place_of_birth"] == "New York City"
    assert p["known_for"] == "Acting"
    assert p["biographies"]["en"] == "English bio."
    assert p["biographies"]["nl"] == "Nederlandse biografie."
    assert p["biographies"]["it"] == "Biografia italiana."
    assert p["biography"] == "English bio."


def test_trakt_captures_source_metadata():
    from app.ingest.adapters.trakt import TraktAdapter
    ev = TraktAdapter._to_event({
        "id": 1, "watched_at": "2025-01-14T20:00:00.000Z", "type": "movie",
        "movie": {"title": "Dune: Part Two", "year": 2024, "runtime": 166,
                  "overview": "Trakt overview.", "genres": ["science-fiction", "adventure"],
                  "ids": {"tmdb": 693134}},
    })
    assert ev.metadata["overview"] == "Trakt overview."
    assert ev.metadata["genres"] == ["Science Fiction", "Adventure"]
    assert ev.metadata["runtime_minutes"] == 166


def test_jellyfin_movie_metadata_people():
    from app.ingest.adapters.jellyfin import _movie_metadata
    md = _movie_metadata({
        "Name": "Dune", "Overview": "Jellyfin overview.", "OriginalTitle": "Dune",
        "Genres": ["Science Fiction"],
        "People": [
            {"Name": "Timothée Chalamet", "Role": "Paul", "Type": "Actor"},
            {"Name": "Denis Villeneuve", "Type": "Director"},
            {"Name": "Lighting Tech", "Type": "GrandparentTitle"},
        ],
    })
    assert md["overview"] == "Jellyfin overview."
    assert md["genres"] == ["Science Fiction"]
    assert [c["name"] for c in md["cast"]] == ["Timothée Chalamet"]
    assert md["cast"][0]["character"] == "Paul"
    assert [c["name"] for c in md["crew"]] == ["Denis Villeneuve"]


def test_plex_parses_metadata_node():
    import xml.etree.ElementTree as ET
    from app.ingest.adapters.plex import _parse_metadata
    node = ET.fromstring(
        '<Directory summary="Plex overview." originalTitle="Dune" duration="9960000">'
        '<Genre tag="Science Fiction"/><Genre tag="Adventure"/>'
        '<Director tag="Denis Villeneuve"/><Writer tag="Jon Spaihts"/>'
        '<Role tag="Timothée Chalamet" role="Paul"/>'
        '</Directory>')
    md = _parse_metadata(node)
    assert md["overview"] == "Plex overview."
    assert md["genres"] == ["Science Fiction", "Adventure"]
    assert md["runtime_minutes"] == 166
    assert [c["name"] for c in md["cast"]] == ["Timothée Chalamet"]
    assert {c["job"] for c in md["crew"]} == {"Director", "Writer"}


def test_plex_metadata_enriches_history(monkeypatch):
    from app.ingest.adapters import plex
    history = (
        b'<MediaContainer>'
        b'<Video type="movie" title="Dune" year="2024" viewedAt="100" '
        b'duration="9960000" ratingKey="rk1"/>'
        b'</MediaContainer>')
    detail = (
        b'<MediaContainer><Video summary="Plex overview." duration="9960000">'
        b'<Genre tag="Science Fiction"/><Role tag="Zendaya" role="Chani"/>'
        b'</Video></MediaContainer>')

    class _R:
        def __init__(self, content):
            self.content = content
            self.status_code = 200

        def raise_for_status(self):
            pass

    def fake_get(url, **k):
        return _R(detail if "/library/metadata/" in url else history)

    monkeypatch.setattr(plex.requests, "get", fake_get)
    events, _ = plex.PlexAdapter().fetch_history({"base_url": "http://x", "token": "t"}, {})
    assert len(events) == 1
    assert events[0].metadata["overview"] == "Plex overview."
    assert events[0].metadata["genres"] == ["Science Fiction"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
