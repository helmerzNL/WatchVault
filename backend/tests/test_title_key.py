"""Tests for cross-provider title matching — pure functions, no database.

Verifies that a series suffixed with a parenthetical release year by one
provider (e.g. Plex "Show (2023)") collapses onto the same match key as the
year-less notation another provider uses (e.g. SkyShowtime "Show"), while
movies keep the year as part of their key (so same-name films of different
years stay distinct)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.util import title_key, normalize_text  # noqa: E402


def test_series_paren_year_stripped_matches_yearless():
    assert title_key("Silo (2023)", "series") == title_key("Silo", "series")


def test_series_paren_year_with_spacing_stripped():
    # Providers vary on inner spacing / trailing whitespace.
    assert title_key("Silo ( 2023 )", "series") == title_key("Silo", "series")
    assert title_key("Silo (2023)  ", "series") == title_key("Silo", "series")


def test_series_only_trailing_paren_year_stripped():
    # A parenthetical that is not a 4-digit year at the very end stays put.
    assert title_key("Cars (Pixar)", "series") == normalize_text("Cars (Pixar)")


def test_series_bare_trailing_number_not_stripped():
    # No parentheses -> not a provider year suffix; keep it (e.g. "Blade Runner 2049").
    assert title_key("Blade Runner 2049", "series") == normalize_text("Blade Runner 2049")
    assert title_key("Blade Runner 2049", "series") != title_key("Blade Runner", "series")


def test_movie_paren_year_is_kept():
    # Movie year disambiguates same-name films; it must remain in the key.
    assert title_key("Dune (1984)", "movie") != title_key("Dune (2021)", "movie")
    assert title_key("Dune (1984)", "movie") == normalize_text("Dune (1984)")


def test_movie_and_series_same_input_differ_when_year_present():
    assert title_key("Show (2023)", "movie") != title_key("Show (2023)", "series")
