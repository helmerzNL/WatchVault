"""Tests for the Home-Assistant-hub re-attribution engine.

The move/collapse/recompute flow is driven against a fake connection (the DB-heavy
re-attribution helpers take no cursor argument, so we patch ``networks.connection``
to replay canned rows and record every executed statement)."""
import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import networks  # noqa: E402

DAY = dt.date(2025, 6, 1)
HUB = "hub-provider-id"
NLZIET = "nlziet-provider-id"


class _FakeCursor:
    """Replays canned fetchone/fetchall results in call order and records every
    executed statement. ``fetchone_rows`` is a flat queue; ``fetchall_rows`` is a
    queue of result lists (one per ``fetchall`` call)."""

    def __init__(self, fetchone_rows, fetchall_rows=None):
        self._one = list(fetchone_rows)
        self._all = list(fetchall_rows or [])
        self.executed = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._all.pop(0) if self._all else []


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self._cur


def _patch(monkeypatch, cur):
    monkeypatch.setattr(networks, "connection", lambda: _FakeConn(cur))


def _sqls(cur):
    return [e[0] for e in cur.executed]


def test_no_hub_provider_is_noop(monkeypatch):
    cur = _FakeCursor(fetchone_rows=[None])  # homeassistant lookup misses
    _patch(monkeypatch, cur)
    assert networks.reattribute_hub_events() == {
        "status": "no_hub", "moved": 0, "collapsed": 0}


def test_moves_parked_event_to_real_platform(monkeypatch):
    cur = _FakeCursor(
        fetchone_rows=[
            {"id": HUB},   # homeassistant provider lookup
            None,          # collapse check: no real event covers this watch
        ],
        fetchall_rows=[[
            {"id": "we1", "user_id": "u1", "title_id": "t1", "episode_id": "e1",
             "watched_date": DAY, "target_id": NLZIET},
        ]],
    )
    _patch(monkeypatch, cur)
    res = networks.reattribute_hub_events()
    assert res == {"status": "ok", "moved": 1, "collapsed": 0}
    # The event is re-pointed at the real provider and both providers recompute.
    assert any(s.startswith("UPDATE watch_events SET provider_id") for s in _sqls(cur))
    recomputes = [e[1] for e in cur.executed if "wv_recompute_agg_days" in e[0]]
    pids = {p[1] for p in recomputes}
    assert pids == {HUB, NLZIET}


def test_collapses_when_real_sync_already_covers_watch(monkeypatch):
    cur = _FakeCursor(
        fetchone_rows=[
            {"id": HUB},   # homeassistant provider lookup
            {"1": 1},      # collapse check: a real (non-hub) event already exists
        ],
        fetchall_rows=[[
            {"id": "we1", "user_id": "u1", "title_id": "t1", "episode_id": "e1",
             "watched_date": DAY, "target_id": NLZIET},
        ]],
    )
    _patch(monkeypatch, cur)
    res = networks.reattribute_hub_events()
    assert res == {"status": "ok", "moved": 0, "collapsed": 1}
    # Tombstoned, never re-pointed; only the hub rollup is drained.
    assert any("SET deleted_at = now()" in s for s in _sqls(cur))
    assert not any(s.startswith("UPDATE watch_events SET provider_id") for s in _sqls(cur))
    recomputes = [e[1] for e in cur.executed if "wv_recompute_agg_days" in e[0]]
    assert {p[1] for p in recomputes} == {HUB}


def test_no_candidates_is_noop(monkeypatch):
    cur = _FakeCursor(fetchone_rows=[{"id": HUB}], fetchall_rows=[[]])
    _patch(monkeypatch, cur)
    assert networks.reattribute_hub_events() == {
        "status": "ok", "moved": 0, "collapsed": 0}
