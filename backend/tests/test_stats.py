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

from app.api.stats import _hours  # noqa: E402


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
