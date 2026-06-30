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


def test_parse_generic_update_tick():
    # `update` is a periodic real-time progress tick — a valid event (not None).
    evt = parse_generic_payload({
        "event": "update", "title": "X",
        "position_seconds": 30, "duration_seconds": 100,
    })
    assert evt is not None
    assert evt.event == "update"
    assert evt.progress_percent == 30.0


# ── Decision helpers ────────────────────────────────────────────────────────

def test_state_for_event():
    assert state_for_event("play") == "playing"
    assert state_for_event("pause") == "paused"
    assert state_for_event("stop") == "stopped"
    assert state_for_event("scrobble") == "playing"
    assert state_for_event("update") == "playing"


def test_should_commit_threshold_and_scrobble():
    base = dict(source="plex", raw_title="X", dedup_key="k")
    assert should_commit(ScrobbleEvent(event="scrobble", **base), 90) is True
    assert should_commit(ScrobbleEvent(event="stop", progress_percent=95, **base), 90) is True
    assert should_commit(ScrobbleEvent(event="stop", progress_percent=89, **base), 90) is False
    assert should_commit(ScrobbleEvent(event="play", progress_percent=None, **base), 90) is False
    assert should_commit(ScrobbleEvent(event="pause", progress_percent=90, **base), 90) is True


def test_should_commit_update_tick():
    # An `update` tick commits once it crosses the threshold; below it, it doesn't.
    base = dict(source="homeassistant", raw_title="X", dedup_key="k")
    assert should_commit(ScrobbleEvent(event="update", progress_percent=89, **base), 90) is False
    assert should_commit(ScrobbleEvent(event="update", progress_percent=90, **base), 90) is True
    assert should_commit(ScrobbleEvent(event="update", progress_percent=95, **base), 90) is True


def test_update_is_not_a_reset_event():
    # `update` must NOT reset committed_at (only fresh play/resume start a new
    # session). This pins the reset-set contract used by handle_scrobble.
    assert "update" not in ("play", "resume")


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


# ── Self-deadlock fix: single-transaction commit (DB-free) ──────────────────
#
# The bug: handle_scrobble held an open transaction with an uncommitted INSERT on
# the titles unique index (a first-seen title), then ingest_events opened a SECOND
# pooled connection and re-resolved the same title — which blocked in Postgres
# waiting for the first transaction to commit, while the first waited in Python for
# ingest_events to return. The fix threads the open cursor into ingest_events so the
# whole commit is one transaction (no second connection). These tests pin that
# contract without a live database.

from app.ingest import normalize as _normalize  # noqa: E402
from app.ingest import scrobble as _scrobble     # noqa: E402
from app.ingest.models import NormalizedEvent    # noqa: E402


class SmartCursor:
    """In-memory cursor that emulates just enough SQL for the ingest/scrobble
    paths: it tracks created titles (by kind+normalized_key) and inserted
    watch_events (by dedup_hash) so first-seen vs. dedup behavior is observable."""
    def __init__(self):
        self.titles: dict[tuple, str] = {}
        self.dedup_hashes: set[str] = set()
        self.title_seq = 0
        self.executed: list[str] = []
        self._last = None

    def execute(self, sql, params=None):
        self.executed.append(sql)
        s = " ".join(sql.split())
        self._last = None
        if "FROM providers" in s:
            self._last = {"id": "prov-1"}
        elif "scrobble_account_map" in s:
            self._last = {"user_id": "profile-1"}
        elif "INSERT INTO scrobble_sessions" in s:
            self._last = {"id": "sess-1", "committed_at": None}
        elif "FROM titles WHERE tmdb_id" in s:
            self._last = None
        elif "FROM titles WHERE kind" in s:
            kind, norm = params
            self._last = ({"id": self.titles[(kind, norm)]}
                          if (kind, norm) in self.titles else None)
        elif s.startswith("INSERT INTO titles"):
            kind, _title, _year, _tmdb, _ext, norm = params
            self.title_seq += 1
            tid = f"title-{self.title_seq}"
            self.titles[(kind, norm)] = tid
            self._last = {"id": tid}
        elif "FROM title_episodes" in s:
            self._last = None
        elif s.startswith("INSERT INTO title_episodes"):
            self._last = {"id": "ep-1"}
        elif "INSERT INTO watch_events" in s:
            dh = params[-1]
            if dh in self.dedup_hashes:
                self._last = None          # ON CONFLICT DO NOTHING -> no row
            else:
                self.dedup_hashes.add(dh)
                self._last = {"id": f"we-{len(self.dedup_hashes)}"}
        # everything else (UPDATEs, agg recompute, background_jobs) returns nothing

    def fetchone(self):
        return self._last

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _new_movie_event(title="Brand New Movie"):
    from app.util import now_utc
    return NormalizedEvent(
        raw_title=title, clean_title=title, watched_at=now_utc(),
        kind="movie", completed=True, raw={"source": "homeassistant", "scrobble": True},
    )


def test_ingest_events_with_cursor_opens_no_second_connection(monkeypatch):
    # The literal deadlock regression guard: when a cursor is threaded in,
    # ingest_events must NOT open another pooled connection.
    def _boom(*a, **k):
        raise AssertionError("ingest_events opened a second connection")
    monkeypatch.setattr(_normalize, "connection", _boom)

    cur = SmartCursor()
    summary = _normalize.ingest_events("user-1", "prov-1", None,
                                       [_new_movie_event()], cur=cur)
    assert summary["inserted"] == 1
    assert summary["titles_created"] == 1
    # The new title was created exactly once, on the same cursor.
    assert len(cur.titles) == 1


def test_ingest_events_threaded_creates_title_once_then_dedups():
    cur = SmartCursor()
    ev = _new_movie_event()
    first = _normalize.ingest_events("user-1", "prov-1", None, [ev], cur=cur)
    second = _normalize.ingest_events("user-1", "prov-1", None, [ev], cur=cur)
    assert first["inserted"] == 1 and first["titles_created"] == 1
    # Same title + day -> identical dedup_hash -> no duplicate watch_event, no new title.
    assert second["inserted"] == 0 and second["duplicates"] == 1
    assert second["titles_created"] == 0
    assert len(cur.titles) == 1
    assert len(cur.dedup_hashes) == 1


def test_handle_scrobble_new_title_commits_in_one_transaction(monkeypatch):
    # Prove handle_scrobble threads its OWN open cursor into ingest_events (so the
    # title INSERT and the watch_event land in one transaction) and returns promptly
    # with committed=True for a first-seen title.
    cur = SmartCursor()

    class FakeConn:
        def cursor(self):
            return cur
        def commit(self):
            pass
        def rollback(self):
            pass

    import contextlib

    @contextlib.contextmanager
    def fake_connection():
        yield FakeConn()

    monkeypatch.setattr(_scrobble, "connection", fake_connection)

    captured = {}

    def fake_ingest(user_id, provider_id, source_connection_id, events, cur=None):
        captured["cur"] = cur
        return {"inserted": 1, "duplicates": 0, "titles_created": 1,
                "titles_touched": 1, "series_title_ids": []}

    monkeypatch.setattr(_scrobble, "ingest_events", fake_ingest)

    evt = parse_generic_payload({"title": "Brand New Movie", "event": "scrobble"})
    result = _scrobble.handle_scrobble("hh-1", evt, "token-user")

    assert result["committed"] is True
    # Same cursor object was threaded through -> single transaction, no 2nd connection.
    assert captured["cur"] is cur
    # lock_timeout hardening is set at the start of the transaction.
    assert any("lock_timeout" in s for s in cur.executed)


# ── Keep now-playing visible after commit (this change) ─────────────────────
#
# A live scrobble that crosses the >=90% threshold commits to watch_events ONCE,
# but the now-playing card must stay visible while playback continues — it only
# disappears on a real `stop` event. These tests pin that contract DB-free.

import contextlib  # noqa: E402


def _fake_conn(cur):
    """Wrap a fake cursor in a `connection()`-style context manager whose
    conn.cursor() yields it (also usable as `with conn.cursor() as cur`)."""
    class FakeConn:
        def cursor(self):
            return cur
        def commit(self):
            pass
        def rollback(self):
            pass

    @contextlib.contextmanager
    def fake_connection():
        yield FakeConn()

    return fake_connection


def _norm(sql):
    return " ".join(sql.split())


def test_handle_scrobble_commit_keeps_playing_state(monkeypatch):
    # (a) After a >=90% commit the session is NOT forced to state='stopped':
    # state stays 'playing' and the commit happens exactly once.
    cur = SmartCursor()
    monkeypatch.setattr(_scrobble, "connection", _fake_conn(cur))
    monkeypatch.setattr(
        _scrobble, "ingest_events",
        lambda *a, **k: {"inserted": 1, "duplicates": 0, "titles_created": 0,
                         "titles_touched": 1, "series_title_ids": []})

    evt = parse_generic_payload({"title": "Dune", "event": "update",
                                 "position_seconds": 95, "duration_seconds": 100})
    result = _scrobble.handle_scrobble("hh-1", evt, "token-user")

    assert result["committed"] is True
    assert result["state"] == "playing"      # update -> playing, kept at commit
    # The commit UPDATE marks committed_at only; it must NOT force state='stopped'.
    assert not any("state = 'stopped'" in _norm(s) for s in cur.executed)
    # Exactly one commit-marking UPDATE ran.
    assert sum("SET committed_at = now()" in _norm(s) for s in cur.executed) == 1


class CommittedSessionCursor(SmartCursor):
    """Like SmartCursor but the session UPSERT reports an already-committed row,
    so handle_scrobble takes the already_committed (no re-ingest) path."""
    def execute(self, sql, params=None):
        super().execute(sql, params)
        if "INSERT INTO scrobble_sessions" in _norm(sql):
            self._last = {"id": "sess-1", "committed_at": "2024-01-01T00:00:00"}


def test_handle_scrobble_committed_update_tick_does_not_reingest(monkeypatch):
    # (b) A later identical `update` tick on an already-committed session does NOT
    # re-ingest, and the session stays visible-eligible (state 'playing', not stopped).
    cur = CommittedSessionCursor()
    monkeypatch.setattr(_scrobble, "connection", _fake_conn(cur))

    def _boom(*a, **k):
        raise AssertionError("ingest_events ran for an already-committed session")
    monkeypatch.setattr(_scrobble, "ingest_events", _boom)

    evt = parse_generic_payload({"title": "Dune", "event": "update",
                                 "position_seconds": 95, "duration_seconds": 100})
    result = _scrobble.handle_scrobble("hh-1", evt, "token-user")

    assert result["committed"] is False
    assert result["state"] == "playing"      # still <> 'stopped' -> stays visible
    # No second commit-marking UPDATE happened.
    assert not any("SET committed_at = now()" in _norm(s) for s in cur.executed)


def test_now_playing_query_drops_committed_at_filter(monkeypatch):
    # (c) The now-playing query no longer filters on committed_at, so a
    # committed-but-still-playing session is returned; only state='stopped' hides it.
    from app import create_app
    from app.auth import sessions as _sessions
    from app.api import scrobble as _api

    fake_user = {"id": "u-1", "household_id": "hh-1", "permissions": {"*"}}
    monkeypatch.setattr(_sessions, "resolve_current_user", lambda: fake_user)

    captured = {}

    fake_row = {
        "id": "sess-1", "title_id": "title-42", "profile_name": "Alice",
        "user_id": "u-1", "account_label": None, "source": "homeassistant",
        "provider_name": "Plex", "provider_color": "#e5a00d", "raw_title": "Dune",
        "kind": "movie", "season": None, "episode": None, "episode_name": None,
        "year": 2024, "poster_path": None, "progress_percent": 95,
        "state": "playing", "updated_at": None,
    }

    def fake_query_all(sql, params=None):
        captured["sql"] = _norm(sql)
        captured["params"] = params
        return [fake_row]
    monkeypatch.setattr(_api, "query_all", fake_query_all)

    client = create_app().test_client()
    resp = client.get("/api/scrobble/now-playing")

    assert resp.status_code == 200
    assert "s.state <> 'stopped'" in captured["sql"]
    assert "committed_at IS NULL" not in captured["sql"]
    assert "ORDER BY s.updated_at DESC" in captured["sql"]
    # A session paused for >10 minutes is hidden from the dashboard.
    assert "s.state = 'paused'" in captured["sql"]
    assert "interval '10 minutes'" in captured["sql"]
    # The card is clickable: now-playing exposes the resolved title_id so the
    # frontend can link to /title/<id>.
    body = resp.get_json()
    assert body[0]["title_id"] == "title-42"


def test_expire_stale_already_committed_marks_stopped_without_reingest(monkeypatch):
    # (d) A stale session that is ALREADY committed (its ticks silently stopped, no
    # `stop` event) is just marked stopped — no second ingest_events / watch_event.
    stale_row = {
        "id": "sess-9", "committed_at": "2024-01-01T00:00:00",
        "progress_percent": 95, "user_id": "u-1", "provider_id": "p-1",
        "episode_name": None, "raw_title": "Dune", "kind": "movie",
        "year": 2024, "season": None, "episode": None,
        "duration_seconds": 100, "tmdb_id": None, "source": "homeassistant",
    }

    class ExpireCursor:
        def __init__(self):
            self.executed = []
        def execute(self, sql, params=None):
            self.executed.append((_norm(sql), params))
        def fetchall(self):
            return [stale_row]
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    cur = ExpireCursor()
    monkeypatch.setattr(_scrobble, "connection", _fake_conn(cur))

    def _boom(*a, **k):
        raise AssertionError("ingest_events ran for an already-committed stale session")
    monkeypatch.setattr(_scrobble, "ingest_events", _boom)

    result = _scrobble.expire_stale_sessions()

    assert result["expired"] == 1
    assert result["committed"] == 0
    # The stale SELECT no longer filters on committed_at (it includes committed rows).
    assert any("FROM scrobble_sessions" in sql and "committed_at IS NULL" not in sql
               for sql, _ in cur.executed if "SELECT" in sql)
    # The session was retired via state='stopped', not re-committed.
    assert any("SET state = 'stopped'" in sql for sql, _ in cur.executed)


def test_handle_scrobble_upsert_updates_attribution_on_later_tick(monkeypatch):
    # Corrected attribution must propagate to scrobble_sessions on later ticks:
    # a session first seen as a movie that later reports kind='series' (same
    # dedup_key) must have kind/season/episode/episode_name overwritten so the
    # now-playing card stops showing stale attribution.
    cur = SmartCursor()
    monkeypatch.setattr(_scrobble, "connection", _fake_conn(cur))
    monkeypatch.setattr(
        _scrobble, "ingest_events",
        lambda *a, **k: {"inserted": 1, "duplicates": 0, "titles_created": 0,
                         "titles_touched": 1, "series_title_ids": []})

    first = parse_generic_payload({"title": "Loki", "event": "play",
                                   "position_seconds": 10, "duration_seconds": 100})
    _scrobble.handle_scrobble("hh-1", first, "token-user")

    second = parse_generic_payload({"title": "Loki", "event": "update",
                                    "kind": "series", "season": 1, "episode": 3,
                                    "episode_name": "Lamentis",
                                    "position_seconds": 20, "duration_seconds": 100})
    _scrobble.handle_scrobble("hh-1", second, "token-user")

    upserts = [_norm(s) for s in cur.executed if "INSERT INTO scrobble_sessions" in _norm(s)]
    assert upserts, "expected a scrobble_sessions UPSERT"
    upsert = upserts[-1]
    # The DO UPDATE SET overwrites the live attribution columns (not COALESCE'd).
    assert "kind = EXCLUDED.kind" in upsert
    assert "season = EXCLUDED.season" in upsert
    assert "episode = EXCLUDED.episode" in upsert
    assert "episode_name = EXCLUDED.episode_name" in upsert
