"""Tests for the live scrobbling receiver — no database or network.

Covers the pure payload parsers (Plex webhook + generic JSON), the commit/state
decision helpers, and the provider/profile resolution branches (driven by a fake
cursor), plus a DB-free 401 check on the generic push endpoint."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.scrobble import (  # noqa: E402
    parse_plex_payload, parse_generic_payload, should_commit, state_for_event,
    _tmdb_from_guids, _progress, _resolve_provider_id, _resolve_profile_id,
    ScrobbleEvent,
)


# ── Plex parser ─────────────────────────────────────────────────────────────

def _plex_movie(event="media.play", offset=300_000, duration=600_000):
    return {
        "event": event,
        "Account": {"title": "Dad"},
        "Metadata": {
            "type": "movie", "title": "Dune: Part Two", "year": 2024,
            "ratingKey": "9001", "duration": duration, "viewOffset": offset,
            "Guid": [{"id": "imdb://tt1"}, {"id": "tmdb://693134"}],
        },
    }


def test_parse_plex_movie():
    evt = parse_plex_payload(_plex_movie())
    assert evt.source == "plex"
    assert evt.event == "play"
    assert evt.kind == "movie"
    assert evt.raw_title == "Dune: Part Two"
    assert evt.account_label == "Dad"
    assert evt.tmdb_id == 693134
    assert evt.year == 2024
    assert evt.progress_percent == 50.0  # 300s of 600s
    assert evt.dedup_key == "plex:9001"


def test_parse_plex_episode():
    payload = {
        "event": "media.resume",
        "Account": {"title": "Mom"},
        "Metadata": {
            "type": "episode", "title": "The Rains of Castamere",
            "grandparentTitle": "Game of Thrones", "grandparentRatingKey": "55",
            "parentIndex": 3, "index": 9, "year": 2013,
            "duration": 3_000_000, "viewOffset": 1_500_000,
        },
    }
    evt = parse_plex_payload(payload)
    assert evt.kind == "series"
    assert evt.raw_title == "Game of Thrones"
    assert evt.episode_name == "The Rains of Castamere"
    assert evt.season == 3
    assert evt.episode == 9
    assert evt.dedup_key == "plex:55:3:9"
    assert evt.progress_percent == 50.0


def test_parse_plex_scrobble_is_full_progress():
    # Plex sends no viewOffset on a scrobble event -> treat as 100%.
    payload = _plex_movie(event="media.scrobble", offset=None)
    payload["Metadata"].pop("viewOffset", None)
    evt = parse_plex_payload(payload)
    assert evt.event == "scrobble"
    assert evt.progress_percent == 100.0


def test_parse_plex_ignores_unknown_event_and_type():
    assert parse_plex_payload({"event": "media.rate", "Metadata": {"type": "movie"}}) is None
    assert parse_plex_payload({"event": "media.play", "Metadata": {"type": "track"}}) is None


def test_tmdb_from_guids():
    assert _tmdb_from_guids({"Guid": [{"id": "tmdb://42"}]}) == 42
    assert _tmdb_from_guids({"Guid": [{"id": "imdb://tt0"}]}) is None
    assert _tmdb_from_guids({}) is None


def test_progress_helper():
    assert _progress(150, 300) == 50.0
    assert _progress(None, 300) is None
    assert _progress(150, 0) is None
    assert _progress(900, 300) == 100.0  # clamped


# ── Generic parser ──────────────────────────────────────────────────────────

def test_parse_generic_minimal_movie():
    evt = parse_generic_payload({"title": "Heat", "event": "play"})
    assert evt.source == "homeassistant"   # default source
    assert evt.kind == "movie"
    assert evt.dedup_key == "homeassistant:heat:None:None"


def test_parse_generic_episode_with_platform_and_progress():
    evt = parse_generic_payload({
        "title": "Severance", "event": "stop", "source": "homeassistant",
        "account": "Helmer", "platform": "appletv", "season": 1, "episode": 5,
        "position_seconds": 1620, "duration_seconds": 1800,
    })
    assert evt.kind == "series"            # season/episode implies series
    assert evt.platform_key == "appletv"
    assert evt.account_label == "Helmer"
    assert evt.progress_percent == 90.0    # derived from position/duration
    assert evt.dedup_key == "homeassistant:severance:1:5"


def test_parse_generic_requires_title_and_known_event():
    assert parse_generic_payload({"event": "play"}) is None
    assert parse_generic_payload({"title": "X", "event": "bogus"}) is None


def test_parse_generic_explicit_dedup_key_wins():
    evt = parse_generic_payload({"title": "X", "event": "play", "dedup_key": "k-1"})
    assert evt.dedup_key == "k-1"


# ── Decision helpers ────────────────────────────────────────────────────────

def test_state_for_event():
    assert state_for_event("play") == "playing"
    assert state_for_event("pause") == "paused"
    assert state_for_event("stop") == "stopped"
    assert state_for_event("scrobble") == "playing"


def test_should_commit_threshold_and_scrobble():
    base = dict(source="plex", raw_title="X", dedup_key="k")
    assert should_commit(ScrobbleEvent(event="scrobble", **base), 90) is True
    assert should_commit(ScrobbleEvent(event="stop", progress_percent=95, **base), 90) is True
    assert should_commit(ScrobbleEvent(event="stop", progress_percent=89, **base), 90) is False
    assert should_commit(ScrobbleEvent(event="play", progress_percent=None, **base), 90) is False
    assert should_commit(ScrobbleEvent(event="pause", progress_percent=90, **base), 90) is True


# ── Provider / profile resolution (fake cursor) ─────────────────────────────

class FakeCursor:
    """Minimal cursor recording executes and replaying canned fetchone rows."""
    def __init__(self, rows):
        self._rows = list(rows)
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None


def test_resolve_provider_platform_wins():
    evt = ScrobbleEvent(source="plex", event="play", raw_title="X", dedup_key="k",
                        platform_key="netflix")
    cur = FakeCursor([{"id": "prov-netflix"}])
    assert _resolve_provider_id(cur, evt) == "prov-netflix"
    # First lookup is the platform key.
    assert cur.executed[0][1] == ("netflix",)


def test_resolve_provider_falls_back_to_source():
    evt = ScrobbleEvent(source="plex", event="play", raw_title="X", dedup_key="k")
    cur = FakeCursor([{"id": "prov-plex"}])     # platform_key None -> skipped
    assert _resolve_provider_id(cur, evt) == "prov-plex"
    assert cur.executed[0][1] == ("plex",)


def test_resolve_profile_mapping_wins():
    evt = ScrobbleEvent(source="plex", event="play", raw_title="X", dedup_key="k",
                        account_label="Dad")
    cur = FakeCursor([{"user_id": "profile-dad"}])
    assert _resolve_profile_id(cur, "hh-1", evt, "token-user") == "profile-dad"


def test_resolve_profile_falls_back_to_token_user():
    evt = ScrobbleEvent(source="plex", event="play", raw_title="X", dedup_key="k",
                        account_label="Unknown")
    cur = FakeCursor([None])   # no mapping row
    assert _resolve_profile_id(cur, "hh-1", evt, "token-user") == "token-user"


def test_resolve_profile_no_account_uses_token_user():
    evt = ScrobbleEvent(source="plex", event="play", raw_title="X", dedup_key="k")
    cur = FakeCursor([])
    assert _resolve_profile_id(cur, "hh-1", evt, "token-user") == "token-user"
    assert cur.executed == []   # no query when there's no account label


# ── Endpoint auth (DB-free 401) ─────────────────────────────────────────────

def test_generic_push_requires_auth():
    from app import create_app
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/scrobble/generic", json={"title": "X", "event": "play"})
    assert resp.status_code == 401
