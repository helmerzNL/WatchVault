"""Tests for the precomputed title-completion tracker — no live database.

Drives ``recompute_title_progress`` with a scripted fake cursor so the
status-derivation rules (series finished vs in-progress, movie finished vs
in-progress, and the "drop the row" paths) are verified without Postgres."""
import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.progress import (  # noqa: E402
    recompute_title_progress, recompute_title_progress_all_users,
)

NOW = dt.datetime(2025, 6, 1, 20, 0, 0)


class FakeCursor:
    """Replays canned fetchone/fetchall results in call order and records every
    executed statement for assertions."""
    def __init__(self, fetchone_rows, fetchall_rows=None):
        self._one = list(fetchone_rows)
        self._all = list(fetchall_rows or [])
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._all.pop(0) if self._all else []


def _sqls(cur):
    return [e[0] for e in cur.executed]


# ── Guard clauses ───────────────────────────────────────────────────────────

def test_missing_ids_return_none_without_touching_db():
    cur = FakeCursor([])
    assert recompute_title_progress(cur, "", "t1") is None
    assert recompute_title_progress(cur, "u1", "") is None
    assert cur.executed == []


def test_deleted_title_removes_progress_row():
    # titles lookup returns None -> the progress row is cleaned up.
    cur = FakeCursor(fetchone_rows=[None])
    assert recompute_title_progress(cur, "u1", "t1") is None
    assert any("DELETE FROM title_progress" in s for s in _sqls(cur))


# ── Series ──────────────────────────────────────────────────────────────────

def test_series_finished_when_all_episodes_watched():
    cur = FakeCursor(fetchone_rows=[
        {"kind": "series"},          # titles.kind
        {"last": NOW},               # max watched_at
        {"last": None},              # max scrobble updated_at
        {"n": 10},                   # total episodes
        {"n": 10},                   # watched episodes
    ])
    status = recompute_title_progress(cur, "u1", "t1")
    assert status == "finished"
    ins = next(e for e in cur.executed if "INSERT INTO title_progress" in e[0])
    # params: (user, title, status, watched, total, last_activity)
    assert ins[1][2] == "finished"
    assert ins[1][3] == 10 and ins[1][4] == 10
    assert ins[1][5] == NOW


def test_series_in_progress_when_partially_watched():
    cur = FakeCursor(fetchone_rows=[
        {"kind": "series"},
        {"last": NOW},
        {"last": None},
        {"n": 10},                   # total
        {"n": 3},                    # watched
    ])
    status = recompute_title_progress(cur, "u1", "t1")
    assert status == "in_progress"
    ins = next(e for e in cur.executed if "INSERT INTO title_progress" in e[0])
    assert ins[1][3] == 3 and ins[1][4] == 10


def test_series_in_progress_from_live_session_before_enrichment():
    # No episodes known yet (total=0, watched=0) but a live scrobble session
    # exists -> still in_progress so it shows up while playing.
    cur = FakeCursor(fetchone_rows=[
        {"kind": "series"},
        {"last": None},              # no committed event
        {"last": NOW},               # live session updated_at
        {"n": 0},                    # total (not enriched yet)
        {"n": 0},                    # watched
    ])
    assert recompute_title_progress(cur, "u1", "t1") == "in_progress"


def test_series_without_data_or_live_is_removed():
    cur = FakeCursor(fetchone_rows=[
        {"kind": "series"},
        {"last": None},
        {"last": None},
        {"n": 10},
        {"n": 0},
    ])
    assert recompute_title_progress(cur, "u1", "t1") is None
    assert any("DELETE FROM title_progress" in s for s in _sqls(cur))
    assert not any("INSERT INTO title_progress" in s for s in _sqls(cur))


# ── Movies ──────────────────────────────────────────────────────────────────

def test_movie_finished_when_committed_event_exists():
    cur = FakeCursor(fetchone_rows=[
        {"kind": "movie"},
        {"last": NOW},               # max watched_at
        {"last": None},              # scrobble
        {"exists": 1},               # watch_event exists (LIMIT 1)
    ])
    status = recompute_title_progress(cur, "u1", "t1")
    assert status == "finished"
    ins = next(e for e in cur.executed if "INSERT INTO title_progress" in e[0])
    # Movies keep total/watched at 0.
    assert ins[1][3] == 0 and ins[1][4] == 0


def test_movie_in_progress_from_live_session_only():
    cur = FakeCursor(fetchone_rows=[
        {"kind": "movie"},
        {"last": None},              # no committed event
        {"last": NOW},               # live session
        None,                        # no watch_event row
    ])
    assert recompute_title_progress(cur, "u1", "t1") == "in_progress"


def test_movie_without_event_or_live_is_removed():
    cur = FakeCursor(fetchone_rows=[
        {"kind": "movie"},
        {"last": None},
        {"last": None},
        None,
    ])
    assert recompute_title_progress(cur, "u1", "t1") is None
    assert any("DELETE FROM title_progress" in s for s in _sqls(cur))


def test_last_activity_prefers_latest_of_event_and_live():
    earlier = dt.datetime(2025, 1, 1, 10, 0, 0)
    cur = FakeCursor(fetchone_rows=[
        {"kind": "movie"},
        {"last": earlier},           # committed event
        {"last": NOW},               # newer live tick
        {"exists": 1},
    ])
    recompute_title_progress(cur, "u1", "t1")
    ins = next(e for e in cur.executed if "INSERT INTO title_progress" in e[0])
    assert ins[1][5] == NOW  # max of the two


# ── All-users fan-out ───────────────────────────────────────────────────────

def test_recompute_all_users_iterates_distinct_users():
    # First fetchall = the union of user_ids; then each user drives its own
    # recompute (movie finished path: kind, watched_at, scrobble, exists).
    cur = FakeCursor(
        fetchone_rows=[
            {"kind": "movie"}, {"last": NOW}, {"last": None}, {"exists": 1},
            {"kind": "movie"}, {"last": NOW}, {"last": None}, {"exists": 1},
        ],
        fetchall_rows=[[{"user_id": "u1"}, {"user_id": "u2"}]],
    )
    recompute_title_progress_all_users(cur, "t1")
    inserts = [e for e in cur.executed if "INSERT INTO title_progress" in e[0]]
    assert {e[1][0] for e in inserts} == {"u1", "u2"}


def test_recompute_all_users_noop_without_title():
    cur = FakeCursor(fetchone_rows=[])
    recompute_title_progress_all_users(cur, "")
    assert cur.executed == []
