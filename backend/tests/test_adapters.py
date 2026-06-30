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


def _load_bytes(adapter_id: str, data: bytes, filename: str = "inline.csv"):
    return get_adapter(adapter_id).import_file(data, filename)


def test_registry_has_core_adapters():
    ids = {a.id for a in list_adapters()}
    assert {"netflix_csv", "generic", "plex_api", "jellyfin_api", "trakt_api", "cinema"} <= ids


def test_cinema_csv_date_title():
    csv_text = (
        "2025-01-12, Dune: Part Two\n"
        "2025-02-03, Oppenheimer\n"
        "14/03/2025, The Brutalist\n"
    )
    events = _load_bytes("cinema", csv_text.encode("utf-8"))
    assert len(events) == 3
    assert all(e.item_kind == "movie" for e in events)
    titles = {e.clean_title for e in events}
    # A title containing a colon (and comma-free) is preserved verbatim.
    assert "Dune: Part Two" in titles
    dune = next(e for e in events if e.clean_title == "Dune: Part Two")
    assert dune.watched_at.date().isoformat() == "2025-01-12"


def test_cinema_csv_skips_header_and_keeps_comma_titles():
    csv_text = (
        "datum,filmtitel\n"
        '2025-04-01,"Crouching Tiger, Hidden Dragon"\n'
    )
    events = _load_bytes("cinema", csv_text.encode("utf-8"))
    assert len(events) == 1
    assert events[0].clean_title == "Crouching Tiger, Hidden Dragon"


def test_cinema_csv_tolerates_title_first():
    events = _load_bytes("cinema", b"Oppenheimer, 2025-02-03\n")
    assert len(events) == 1
    assert events[0].clean_title == "Oppenheimer"
    assert events[0].watched_at.date().isoformat() == "2025-02-03"


def test_netflix_series_vs_movie():
    events = _load("netflix_csv", "netflix-viewing-activity.csv")
    assert len(events) == 15

    st = [e for e in events if e.clean_title == "Stranger Things"]
    assert st and all(e.item_kind == "episode" and e.season == 4 for e in st)
    assert st[0].episode_name == "Chapter One: The Hellfire Club"

    irishman = [e for e in events if e.clean_title == "The Irishman"]
    assert irishman and irishman[0].item_kind == "movie"

    # 'Show: Episode' rows with no season marker (The Queen's Gambit) must group
    # under one series title, not become one movie per episode.
    qg = [e for e in events if e.clean_title == "The Queen's Gambit"]
    assert len(qg) == 2
    assert all(e.item_kind == "episode" for e in qg)
    assert {e.episode_name for e in qg} == {"Openings", "Exchanges"}

    # A genuine 2-part movie that appears once keeps its full title as a movie.
    glass = [e for e in events if e.clean_title == "Glass Onion: A Knives Out Mystery"]
    assert glass and glass[0].item_kind == "movie"


def test_netflix_groups_unmarked_episodes_by_repeated_prefix():
    csv_text = (
        "Title,Date\n"
        "Kingdom: The Hunger,01/01/2025\n"
        "Kingdom: The Cure,01/02/2025\n"
        "Okja,01/03/2025\n"
        "Roma: A Long Subtitle Here,01/04/2025\n"
    )
    events = _load_bytes("netflix_csv", csv_text.encode("utf-8"))
    kingdom = [e for e in events if e.clean_title == "Kingdom"]
    assert len(kingdom) == 2 and all(e.item_kind == "episode" for e in kingdom)
    # single-occurrence colon title stays a movie (not grouped)
    roma = [e for e in events if e.clean_title == "Roma: A Long Subtitle Here"]
    assert roma and roma[0].item_kind == "movie"
    okja = [e for e in events if e.clean_title == "Okja"]
    assert okja and okja[0].item_kind == "movie"


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


def test_trakt_fetch_title_history(monkeypatch):
    from app.ingest.adapters import trakt
    search_payload = [{"type": "show", "show": {"ids": {"trakt": 1390, "tmdb": 94997}}}]
    history_payload = [
        {"id": 11, "watched_at": "2025-01-15T21:30:00.000Z", "type": "episode",
         "episode": {"season": 1, "number": 1, "title": "Pilot", "runtime": 60},
         "show": {"title": "House of the Dragon", "year": 2022, "ids": {"tmdb": 94997}}},
        {"id": 12, "watched_at": "2025-01-16T21:30:00.000Z", "type": "episode",
         "episode": {"season": 1, "number": 2, "title": "Ep Two", "runtime": 60},
         "show": {"title": "House of the Dragon", "year": 2022, "ids": {"tmdb": 94997}}},
    ]
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/search/tmdb/" in url:
            seen["search_type"] = (params or {}).get("type")
            return _FakeResp(payload=search_payload)
        if "/sync/history/shows/" in url:
            seen["history_url"] = url
            return _FakeResp(payload=history_payload, headers={"X-Pagination-Page-Count": "1"})
        return _FakeResp(payload=[])

    monkeypatch.setattr(trakt.requests, "get", fake_get)
    adapter = trakt.TraktAdapter()
    config = {"client_id": "cid", "access_token": "tok"}
    events = adapter.fetch_title_history(
        config, {"kind": "series", "tmdb_id": 94997, "external_ids": {}})

    assert seen["search_type"] == "show"
    assert "/sync/history/shows/1390" in seen["history_url"]
    assert len(events) == 2
    assert {(e.season, e.episode) for e in events} == {(1, 1), (1, 2)}


def test_trakt_fetch_title_history_uses_stored_trakt_id(monkeypatch):
    from app.ingest.adapters import trakt
    calls = {"search": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        if "/search/tmdb/" in url:
            calls["search"] += 1
            return _FakeResp(payload=[])
        return _FakeResp(payload=[], headers={"X-Pagination-Page-Count": "1"})

    monkeypatch.setattr(trakt.requests, "get", fake_get)
    adapter = trakt.TraktAdapter()
    adapter.fetch_title_history(
        {"client_id": "c", "access_token": "t"},
        {"kind": "movie", "tmdb_id": 1, "external_ids": {"trakt": 42}})
    # A stored Trakt id must be used directly, without hitting search.
    assert calls["search"] == 0


def test_trakt_fetch_title_history_requires_token():
    from app.ingest.adapters.trakt import TraktAdapter
    with pytest.raises(ValueError):
        TraktAdapter().fetch_title_history(
            {"client_id": "c"}, {"kind": "series", "tmdb_id": 1, "external_ids": {}})


class _FakeResp:
    def __init__(self, *, content: bytes = b"", payload=None, headers=None, status_code=200):
        self.content = content
        self._payload = payload
        self.headers = headers or {}
        self.status_code = status_code

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


def test_plex_resolves_account_username_to_numeric_id(monkeypatch):
    from app.ingest.adapters import plex
    accounts_xml = (b'<MediaContainer>'
                    b'<Account id="1" name="TheVMaster"/>'
                    b'<Account id="2" name="Kids"/>'
                    b'</MediaContainer>')
    history_xml = (b'<MediaContainer>'
                   b'<Video type="movie" title="M" year="2024" viewedAt="100" '
                   b'duration="6000000" ratingKey="a"/>'
                   b'</MediaContainer>')
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/accounts"):
            return _FakeResp(content=accounts_xml)
        if url.endswith("/history/all"):
            seen["accountID"] = (params or {}).get("accountID")
        return _FakeResp(content=history_xml)

    monkeypatch.setattr(plex.requests, "get", fake_get)
    plex.PlexAdapter().fetch_history(
        {"base_url": "http://x", "token": "t", "account_id": "thevmaster"}, {})
    assert seen["accountID"] == "1"


def test_plex_unknown_account_raises(monkeypatch):
    from app.ingest.adapters import plex
    accounts_xml = b'<MediaContainer><Account id="1" name="TheVMaster"/></MediaContainer>'
    monkeypatch.setattr(plex.requests, "get",
                        lambda *a, **k: _FakeResp(content=accounts_xml))
    with pytest.raises(ValueError):
        plex.PlexAdapter().fetch_history(
            {"base_url": "http://x", "token": "t", "account_id": "nobody"}, {})


def test_trakt_uses_sync_history_with_token(monkeypatch):
    from app.ingest.adapters import trakt
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen["url"] = url
        seen["auth"] = (headers or {}).get("Authorization")
        return _FakeResp(payload=[], headers={"X-Pagination-Page-Count": "1"})

    monkeypatch.setattr(trakt.requests, "get", fake_get)
    trakt.TraktAdapter().fetch_history(
        {"client_id": "c", "username": "helmer", "access_token": "tok"}, {})
    assert seen["url"].endswith("/sync/history")
    assert seen["auth"] == "Bearer tok"


def test_trakt_private_history_raises_clear_error(monkeypatch):
    from app.ingest.adapters import trakt

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResp(payload=[], headers={}, status_code=401)

    monkeypatch.setattr(trakt.requests, "get", fake_get)
    with pytest.raises(ValueError, match="private"):
        trakt.TraktAdapter().fetch_history(
            {"client_id": "c", "username": "helmer"}, {})


def test_plex_tags_library_section(monkeypatch):
    from app.ingest.adapters import plex
    xml = (b'<MediaContainer>'
           b'<Video type="movie" title="M" year="2024" viewedAt="100" '
           b'librarySectionID="3" duration="6000000" ratingKey="a"/>'
           b'</MediaContainer>')
    monkeypatch.setattr(plex.requests, "get", lambda *a, **k: _FakeResp(content=xml))
    events, _ = plex.PlexAdapter().fetch_history({"base_url": "http://x", "token": "t"}, {})
    assert events[0].raw["librarySectionID"] == "3"


def test_plex_prune_spec(monkeypatch):
    from app.ingest.adapters import plex
    adapter = plex.PlexAdapter()
    assert adapter.library_prune_spec({}) is None
    spec = adapter.library_prune_spec({"library_ids": ["1", "2"]})
    assert spec == ("librarySectionID", {"1", "2"})


def test_jellyfin_tags_library_and_prune_spec(monkeypatch):
    from app.ingest.adapters import jellyfin

    def fake_get(url, params=None, headers=None, timeout=None):
        pid = (params or {}).get("ParentId")
        return _FakeResp(payload={"Items": [{
            "Id": f"item-{pid}", "Type": "Movie", "Name": f"Movie {pid}",
            "ProductionYear": 2024, "RunTimeTicks": 60_000_000_000,
            "UserData": {"LastPlayedDate": "2025-01-10T10:00:00.000Z", "Played": True},
        }]})

    monkeypatch.setattr(jellyfin.requests, "get", fake_get)
    adapter = jellyfin.JellyfinAdapter()
    events, _ = adapter.fetch_history(
        {"base_url": "http://x", "api_key": "k", "user_id": "u",
         "library_ids": ["libA"]}, {})
    assert events[0].raw["library_id"] == "libA"
    assert adapter.library_prune_spec(
        {"library_ids": ["libA"]}) == ("library_id", {"libA"})
    assert adapter.library_prune_spec({}) is None


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


def test_trakt_request_device_code_returns_user_code(monkeypatch):
    from app.ingest.adapters import trakt
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _FakeResp(payload={
            "device_code": "dev123", "user_code": "ABCD1234",
            "verification_url": "https://trakt.tv/activate",
            "expires_in": 600, "interval": 5,
        })

    monkeypatch.setattr(trakt.requests, "post", fake_post)
    res = trakt.request_device_code("cid")
    assert res["device_code"] == "dev123"
    assert res["user_code"] == "ABCD1234"
    assert res["verification_url"] == "https://trakt.tv/activate"
    assert res["interval"] == 5
    assert captured["url"].endswith("/oauth/device/code")
    assert captured["body"] == {"client_id": "cid"}


def test_trakt_poll_device_token_authorized_returns_tokens(monkeypatch):
    from app.ingest.adapters import trakt
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _FakeResp(payload={
            "access_token": "acc", "refresh_token": "ref",
            "created_at": 1_000_000, "expires_in": 7776000,
        })

    monkeypatch.setattr(trakt.requests, "post", fake_post)
    res = trakt.poll_device_token("cid", "secret", "dev123")
    assert res == {"status": "authorized", "access_token": "acc",
                   "refresh_token": "ref", "token_expires_at": 1_000_000 + 7776000}
    assert captured["url"].endswith("/oauth/device/token")
    assert captured["body"] == {"code": "dev123", "client_id": "cid", "client_secret": "secret"}


def test_trakt_poll_device_token_pending_and_terminal(monkeypatch):
    from app.ingest.adapters import trakt
    cases = {400: "pending", 410: "expired", 418: "denied", 429: "slow_down", 404: "error"}
    for code, expected in cases.items():
        monkeypatch.setattr(trakt.requests, "post",
                            lambda *a, _c=code, **k: _FakeResp(status_code=_c, payload={}))
        assert trakt.poll_device_token("cid", "secret", "dev")["status"] == expected


def test_trakt_prepare_config_refreshes_when_expired(monkeypatch):
    from app.ingest.adapters import trakt
    calls = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["grant"] = json["grant_type"]
        return _FakeResp(payload={
            "access_token": "new-acc", "refresh_token": "new-ref",
            "created_at": 2_000_000, "expires_in": 7776000,
        })

    monkeypatch.setattr(trakt.requests, "post", fake_post)
    adapter = trakt.TraktAdapter()
    cfg = {"client_id": "cid", "client_secret": "secret",
           "refresh_token": "ref", "access_token": "old", "token_expires_at": 1}
    new_cfg, changed = adapter.prepare_config(cfg)
    assert changed is True
    assert calls["grant"] == "refresh_token"
    assert new_cfg["access_token"] == "new-acc"
    assert new_cfg["refresh_token"] == "new-ref"
    assert new_cfg["token_expires_at"] == 2_000_000 + 7776000


def test_trakt_prepare_config_noop_when_fresh(monkeypatch):
    import time as _time
    from app.ingest.adapters import trakt

    def boom(*a, **k):
        raise AssertionError("should not refresh a fresh token")

    monkeypatch.setattr(trakt.requests, "post", boom)
    adapter = trakt.TraktAdapter()
    cfg = {"client_id": "cid", "client_secret": "secret", "refresh_token": "ref",
           "access_token": "ok", "token_expires_at": int(_time.time()) + 10_000_000}
    new_cfg, changed = adapter.prepare_config(cfg)
    assert changed is False
    assert new_cfg is cfg


def test_trakt_prepare_config_noop_without_secret():
    from app.ingest.adapters import trakt
    adapter = trakt.TraktAdapter()
    cfg = {"client_id": "cid", "access_token": "ok"}
    new_cfg, changed = adapter.prepare_config(cfg)
    assert changed is False
    assert new_cfg is cfg


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
