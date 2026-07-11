"""Tests for `_resolve_title`'s cross-kind reconciliation — no database.

A live-TV / generic push (NLziet, SkyShowtime, Videoland) always arrives as a
bare ``kind='movie'`` with no tmdb_id. If the household has hand-curated the same
title under another category (moved it to "TV Kijken", or uploaded a poster on the
series row), the watch must bind to that curated row instead of spawning a
duplicate movie row without the poster. These drive `_resolve_title` with a
SQL-aware fake cursor so the branch logic is verified without a live Postgres.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.normalize import _resolve_title  # noqa: E402

_RECONCILE_MARK = "manual_kind OR manual_title OR manual_poster"
_EXACT_MARK = "WHERE kind = %s AND normalized_key = %s"


class FakeCursor:
    """Replays canned rows keyed on the SQL statement's shape."""
    def __init__(self, *, tmdb=None, exact=None, reconcile=None, inserted_id="new-id"):
        self.tmdb = tmdb
        self.exact = exact
        self.reconcile = reconcile
        self.inserted_id = inserted_id
        self.executed = []
        self._last = ""

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last = sql

    def fetchone(self):
        sql = self._last
        if "INSERT INTO titles" in sql:
            return {"id": self.inserted_id}
        if "WHERE tmdb_id =" in sql:
            return self.tmdb
        if _RECONCILE_MARK in sql:
            return self.reconcile
        if _EXACT_MARK in sql:
            return self.exact
        return None

    def ran(self, mark):
        return any(mark in sql for sql, _ in self.executed)


def test_bare_movie_reuses_curated_tv_row():
    cur = FakeCursor(reconcile={"id": "tv-row"})
    tid, created = _resolve_title(cur, "movie", "NOS Journaal", None, None, {})
    assert (tid, created) == ("tv-row", False)
    assert cur.ran(_RECONCILE_MARK)
    assert not cur.ran("INSERT INTO titles")   # no duplicate row spawned


def test_exact_match_short_circuits_before_reconcile():
    cur = FakeCursor(exact={"id": "movie-row"}, reconcile={"id": "should-not-win"})
    tid, created = _resolve_title(cur, "movie", "NOS Journaal", None, None, {})
    assert (tid, created) == ("movie-row", False)
    assert not cur.ran(_RECONCILE_MARK)


def test_reconcile_skipped_when_tmdb_id_present():
    # A TMDB-identified movie must never merge into a curated same-name row.
    cur = FakeCursor(reconcile={"id": "curated"})
    tid, created = _resolve_title(cur, "movie", "Fargo", 1997, 275, {})
    assert (tid, created) == ("new-id", True)
    assert not cur.ran(_RECONCILE_MARK)
    assert cur.ran("INSERT INTO titles")


def test_reconcile_skipped_for_incoming_series():
    # Real series imports keep their own row; only bare movie events reconcile.
    cur = FakeCursor(reconcile={"id": "curated-movie"})
    tid, created = _resolve_title(cur, "series", "Fargo", None, None, {})
    assert (tid, created) == ("new-id", True)
    assert not cur.ran(_RECONCILE_MARK)
    assert cur.ran("INSERT INTO titles")


def test_no_curated_row_falls_through_to_insert():
    # The reconcile SELECT filters on the manual flags, so an uncurated same-name
    # row is simply not returned -> a fresh movie row is created as before.
    cur = FakeCursor(reconcile=None)
    tid, created = _resolve_title(cur, "movie", "NOS Journaal", None, None, {})
    assert (tid, created) == ("new-id", True)
    assert cur.ran(_RECONCILE_MARK)
    assert cur.ran("INSERT INTO titles")
