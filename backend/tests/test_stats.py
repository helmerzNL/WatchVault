"""Stats serialization tests — no database or network required.

Guards the regression where aggregate ``sum(bigint)`` columns return a
``Decimal`` that Flask serialises as a JSON *string*, which then crashed the
frontend's ``fmtHours`` (``"3.5".toFixed`` is not a function).
"""
import pathlib
import sys
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.stats import _hours, _fold_digital_library  # noqa: E402


def test_hours_returns_float_for_decimal_seconds():
    # A Decimal (as psycopg returns for sum over a bigint column) must become a
    # plain float so it serialises as a JSON number, not a string.
    result = _hours(Decimal("12600"))  # 3.5h
    assert isinstance(result, float)
    assert result == 3.5


def test_hours_handles_none_and_int():
    assert _hours(None) == 0.0
    assert isinstance(_hours(None), float)
    assert _hours(7200) == 2.0  # 2h
    assert _hours(Decimal("5400"), 1) == 1.5  # honors ndigits


def test_fold_digital_library_merges_plex_and_jellyfin():
    rows = [
        {"key": "plex", "name": "Plex", "color": "#a", "events": 3, "seconds": 100.0},
        {"key": "jellyfin", "name": "Jellyfin", "color": "#b", "events": 2, "seconds": 50.0},
        {"key": "netflix", "name": "Netflix", "color": "#c", "events": 5, "seconds": 200.0},
    ]
    out = _fold_digital_library(rows, (), ("events", "seconds"))
    assert len(out) == 2  # plex+jellyfin collapsed, netflix untouched
    dl = next(r for r in out if r["key"] == "digital_library")
    assert dl["events"] == 5 and dl["seconds"] == 150.0
    assert dl["name"] == "Digital Library"
    nf = next(r for r in out if r["key"] == "netflix")
    assert nf["events"] == 5 and nf["seconds"] == 200.0


def test_fold_digital_library_groups_per_period():
    rows = [
        {"period": "2025-01", "key": "plex", "name": "Plex", "color": "#a",
         "events": 1, "seconds": 10.0},
        {"period": "2025-01", "key": "jellyfin", "name": "Jellyfin", "color": "#b",
         "events": 2, "seconds": 20.0},
        {"period": "2025-02", "key": "plex", "name": "Plex", "color": "#a",
         "events": 3, "seconds": 30.0},
    ]
    out = _fold_digital_library(rows, ("period",), ("events", "seconds"))
    assert len(out) == 2
    jan = next(r for r in out if r["period"] == "2025-01")
    assert jan["key"] == "digital_library" and jan["events"] == 3 and jan["seconds"] == 30.0
    feb = next(r for r in out if r["period"] == "2025-02")
    assert feb["key"] == "digital_library" and feb["events"] == 3
