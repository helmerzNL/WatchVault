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


def test_search_attempts_year_fallback():
    from app.plugins.enrich import build_search_attempts
    attempts = build_search_attempts("Dune", 2024, "movie")
    # exact (with year) is first, then a year-less retry of the same query
    assert attempts[0] == ("Dune", 2024, "movie")
    assert ("Dune", None, "movie") in attempts


def test_search_attempts_strips_netflix_series_noise():
    from app.plugins.enrich import build_search_attempts
    attempts = build_search_attempts("Stranger Things: Season 4: Chapter One", None, "series")
    queries = [q for (q, _y, _k) in attempts]
    assert "Stranger Things" in queries


def test_search_attempts_strips_year_suffix_and_brackets():
    from app.plugins.enrich import build_search_attempts
    queries = [q for (q, _y, _k) in build_search_attempts("Fargo (2014)", None, "series")]
    assert "Fargo" in queries
    queries2 = [q for (q, _y, _k) in build_search_attempts("Sherlock [UK]", None, "series")]
    assert "Sherlock" in queries2


def test_search_attempts_other_kind_is_last_resort():
    from app.plugins.enrich import build_search_attempts
    attempts = build_search_attempts("Dune", 2024, "movie")
    same_kind = [i for i, (_q, _y, k) in enumerate(attempts) if k == "movie"]
    other_kind = [i for i, (_q, _y, k) in enumerate(attempts) if k == "series"]
    assert other_kind, "expected an other-kind fallback"
    # every same-kind attempt comes before the first other-kind attempt
    assert max(same_kind) < min(other_kind)


def test_search_attempts_empty_title():
    from app.plugins.enrich import build_search_attempts
    assert build_search_attempts("   ", 2024, "movie") == []


def test_find_match_uses_year_fallback():
    from app.plugins.enrich import _find_match

    class FakePlugin:
        def __init__(self):
            self.calls = []

        def search(self, query, year, kind):
            self.calls.append((query, year, kind))
            # only the year-less query returns a hit (mismatched watch year)
            return [{"id": 99}] if year is None else []

    plugin = FakePlugin()
    tmdb_id, kind = _find_match(plugin, {"title": "Some Show", "year": 1999, "kind": "series"})
    assert tmdb_id == 99
    assert kind == "series"
    assert plugin.calls[0] == ("Some Show", 1999, "series")


def test_tmdb_series_extracts_networks():
    plugin = _tmdb_plugin()
    data = {
        "id": 1396, "name": "Severance", "first_air_date": "2022-02-18",
        "episode_run_time": [50], "genres": [{"name": "Drama"}],
        "credits": {"cast": [], "crew": []},
        "number_of_seasons": 2, "number_of_episodes": 19, "seasons": [],
        "networks": [
            {"id": 2552, "name": "Apple TV+", "logo_path": "/apple.png"},
            {"id": 0, "name": "", "logo_path": None},  # blank -> skipped
        ],
    }
    details = plugin._normalize(data, "series")
    assert details["networks"] == [
        {"id": 2552, "name": "Apple TV+", "logo_path": "/apple.png"}]


def test_tmdb_movie_has_no_networks():
    plugin = _tmdb_plugin()
    details = plugin._normalize(
        {"id": 1, "title": "X", "release_date": "2020-01-01", "runtime": 90,
         "genres": [], "credits": {"cast": [], "crew": []}}, "movie")
    assert "networks" not in details
    # The full release date is captured (used for the "Release date" quick-pick).
    assert details["release_date"] == "2020-01-01"


class _FakeCursor:
    """Minimal cursor that resolves provider keys against a fixed catalogue."""
    def __init__(self, present):
        self.present = present  # set of provider keys that exist
        self._row = None

    def execute(self, sql, params=None):
        key = params[0] if params else None
        if key == "generic" or "key = 'generic'" in sql:
            self._row = {"id": "generic-id", "key": "generic"}
        elif key in self.present:
            self._row = {"id": f"{key}-id", "key": key}
        else:
            self._row = None

    def fetchone(self):
        return self._row


def test_resolve_network_provider_maps_known_networks():
    from app.networks import resolve_network_provider
    cur = _FakeCursor({"appletv", "prime", "hbomax", "netflix"})
    assert resolve_network_provider(cur, [{"name": "Apple TV+"}]) == ("appletv-id", "appletv")
    assert resolve_network_provider(cur, [{"name": "Amazon Prime Video"}]) == ("prime-id", "prime")
    assert resolve_network_provider(cur, [{"name": "HBO Max"}]) == ("hbomax-id", "hbomax")
    assert resolve_network_provider(cur, [{"name": "Max"}]) == ("hbomax-id", "hbomax")


def test_resolve_network_provider_falls_back_to_generic():
    from app.networks import resolve_network_provider
    cur = _FakeCursor({"netflix"})
    # unknown network name
    assert resolve_network_provider(cur, [{"name": "Some Obscure Channel"}]) == ("generic-id", "generic")
    # no networks at all (e.g. movies)
    assert resolve_network_provider(cur, []) == ("generic-id", "generic")
    # known alias but provider not in catalogue -> generic
    assert resolve_network_provider(cur, [{"name": "Apple TV+"}]) == ("generic-id", "generic")


def test_ensure_networks_returns_stored_without_fetching():
    from app.networks import _ensure_networks
    # metadata already has the key -> returned as-is, no fetch (would need DB/runtime)
    title = {"id": "t1", "kind": "series", "tmdb_id": 42,
             "metadata": {"networks": [{"name": "Netflix"}]}}
    assert _ensure_networks(title) == [{"name": "Netflix"}]
    # present-but-empty key still short-circuits (marks "already fetched")
    assert _ensure_networks({"id": "t2", "kind": "series", "tmdb_id": 42,
                             "metadata": {"networks": []}}) == []


def test_ensure_networks_skips_movies_and_missing_tmdb():
    from app.networks import _ensure_networks
    # movies have no network -> empty, no fetch attempted
    assert _ensure_networks({"id": "m1", "kind": "movie", "tmdb_id": 9, "metadata": {}}) == []
    # a series without a tmdb id cannot be fetched -> empty
    assert _ensure_networks({"id": "s1", "kind": "series", "tmdb_id": None, "metadata": {}}) == []


def test_desired_provider_override_and_sources():
    from app.networks import _desired_provider
    # An override wins for every movable source.
    assert _desired_provider("trakt", "ovr", "net", "man") == "ovr"
    assert _desired_provider("manual", "ovr", "net", "man") == "ovr"
    # Without an override: Trakt -> TMDB network, manual stays on its home provider.
    assert _desired_provider("trakt", None, "net", "man") == "net"
    assert _desired_provider("manual", None, "net", "man") == "man"
    # Real digital syncs/imports are never moved, even with an override set.
    for src in ("plex", "jellyfin", "netflix_csv", "generic", None):
        assert _desired_provider(src, "ovr", "net", "man") is None


def test_desired_provider_adopts_established_real_platform():
    from app.networks import _desired_provider
    # A Trakt event adopts an already-established real platform ahead of the
    # network guess, so Trakt never overwrites a real sync's platform.
    assert _desired_provider("trakt", None, "net", "man", "real") == "real"
    # An override still wins over the real platform.
    assert _desired_provider("trakt", "ovr", "net", "man", "real") == "ovr"
    # Without a real platform, Trakt still falls back to its TMDB network.
    assert _desired_provider("trakt", None, "net", "man", None) == "net"
    # Manual events are unaffected by the established real platform.
    assert _desired_provider("manual", None, "net", "man", "real") == "man"
    # Real syncs are still never moved.
    assert _desired_provider("plex", None, "net", "man", "real") is None


def test_established_real_provider_picks_most_recent(monkeypatch):
    from app.networks import _established_real_provider

    class _FakeCur:
        def __init__(self, row):
            self._row = row
            self.sql = None
            self.params = None

        def execute(self, sql, params=None):
            self.sql = sql
            self.params = params

        def fetchone(self):
            return self._row

    # Returns the provider id of the most recent real event.
    cur = _FakeCur({"provider_id": "plex-id"})
    assert _established_real_provider(cur, "t1") == "plex-id"
    # The query must exclude the movable (soft) sources and order by recency.
    assert "NOT IN" in cur.sql
    assert "watched_at DESC" in cur.sql
    assert cur.params[0] == "t1"
    # No real event -> None.
    assert _established_real_provider(_FakeCur(None), "t1") is None


def test_attribution_reason_classification():
    from app.networks import _attribution_reason
    # An override always wins, regardless of networks.
    assert _attribution_reason({"kind": "series"}, "ovr", [], "generic") == "override"
    # An established real platform wins over a network guess (but not override).
    assert _attribution_reason(
        {"kind": "series", "tmdb_id": 1, "metadata": {}, "enriched_at": None},
        None, [], "generic", "plex") == "real_sync_matched"
    assert _attribution_reason(
        {"kind": "series"}, "ovr", [], "generic", "plex") == "override"
    # A network that maps to a real provider.
    assert _attribution_reason(
        {"kind": "series", "tmdb_id": 1, "metadata": {"networks": [{"name": "Netflix"}]},
         "enriched_at": "2024-01-01"}, None, [{"name": "Netflix"}], "netflix") == "network_matched"
    # A movie has no TMDB networks -> always "Other".
    assert _attribution_reason(
        {"kind": "movie", "tmdb_id": 9, "metadata": {}, "enriched_at": "2024-01-01"},
        None, [], "generic") == "movie_no_networks"
    # An enriched series whose networks are present but none are catalogued.
    assert _attribution_reason(
        {"kind": "series", "tmdb_id": 1, "metadata": {"networks": [{"name": "Obscure"}]},
         "enriched_at": "2024-01-01"}, None, [{"name": "Obscure"}], "generic") == "network_unmapped"
    # An enriched series that TMDB lists with no networks at all.
    assert _attribution_reason(
        {"kind": "series", "tmdb_id": 1, "metadata": {"networks": []},
         "enriched_at": "2024-01-01"}, None, [], "generic") == "no_networks"
    # A series not enriched yet (no networks fetched).
    assert _attribution_reason(
        {"kind": "series", "tmdb_id": 1, "metadata": {}, "enriched_at": None},
        None, [], "generic") == "not_enriched"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
