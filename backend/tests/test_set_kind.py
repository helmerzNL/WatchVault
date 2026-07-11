"""Tests for `apply_kind_change` — the category-change / merge logic — no database.

Changing a title's category is unique on `(kind, normalized_key)`, so a blind
UPDATE 500s when a same-name row of the target category already exists (the
"TV Kijken" case). `apply_kind_change` must instead merge into that row. Driven by
a SQL-aware fake cursor so the branch logic is verified without a live Postgres.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.titles_edit import apply_kind_change  # noqa: E402

_NORMKEY_MARK = "SELECT normalized_key FROM titles"
_COLLISION_MARK = "id <> %s"
_MERGE_MARK = "wv_merge_titles"
_UPDATE_MARK = "UPDATE titles SET kind"


class FakeCursor:
    """Replays canned rows keyed on the SQL statement's shape."""
    def __init__(self, *, normkey_row=None, collision=None):
        self.normkey_row = normkey_row
        self.collision = collision
        self.executed = []
        self._last = ""

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last = sql

    def fetchone(self):
        sql = self._last
        if _NORMKEY_MARK in sql:
            return self.normkey_row
        if _COLLISION_MARK in sql:
            return self.collision
        return None

    def ran(self, mark):
        return any(mark in sql for sql, _ in self.executed)

    def params_for(self, mark):
        return next((p for sql, p in self.executed if mark in sql), None)


def test_collision_merges_into_existing_row():
    cur = FakeCursor(normkey_row={"normalized_key": "nos journaal"},
                     collision={"id": "tv-1"})
    res = apply_kind_change(cur, "movie-1", "tv")
    assert res == {"title_id": "tv-1", "merged": True}
    # Current (movie) row is folded into the existing tv row, which stays canonical.
    assert cur.params_for(_MERGE_MARK) == ("tv-1", "movie-1")
    # The lock/update targets the survivor, never the merged-away source.
    assert cur.params_for(_UPDATE_MARK)[-1] == "tv-1"


def test_no_collision_updates_in_place():
    cur = FakeCursor(normkey_row={"normalized_key": "x"}, collision=None)
    res = apply_kind_change(cur, "movie-1", "tv")
    assert res == {"title_id": "movie-1", "merged": False}
    assert not cur.ran(_MERGE_MARK)
    assert cur.params_for(_UPDATE_MARK)[-1] == "movie-1"


def test_missing_title_returns_none():
    cur = FakeCursor(normkey_row=None)
    assert apply_kind_change(cur, "missing", "tv") is None
    assert not cur.ran(_UPDATE_MARK)
    assert not cur.ran(_MERGE_MARK)


def test_series_keeps_unknown_override_other_kinds_clear_it():
    # clear_unknown is the 2nd UPDATE param: False for series, True otherwise.
    cur = FakeCursor(normkey_row={"normalized_key": "x"}, collision=None)
    apply_kind_change(cur, "t-1", "series")
    assert cur.params_for(_UPDATE_MARK)[:2] == ("series", False)

    cur = FakeCursor(normkey_row={"normalized_key": "x"}, collision=None)
    apply_kind_change(cur, "t-1", "tv")
    assert cur.params_for(_UPDATE_MARK)[:2] == ("tv", True)
