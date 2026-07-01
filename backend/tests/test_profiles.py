"""Profile edit tests — display_name composition, poster_url local paths, and the
avatar-upload auth guard. All DB-free (pure helpers + a no-cookie 401 check)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api._common import poster_url  # noqa: E402
from app.api.profiles import compose_display_name  # noqa: E402


def test_compose_display_name_joins_first_last():
    assert compose_display_name("Ada", "Lovelace", "old") == "Ada Lovelace"


def test_compose_display_name_first_only():
    assert compose_display_name("Ada", "", "old") == "Ada"
    assert compose_display_name("Ada", None, "old") == "Ada"


def test_compose_display_name_falls_back_when_empty():
    assert compose_display_name("", "", "Existing Name") == "Existing Name"
    assert compose_display_name(None, None, None) is None


def test_compose_display_name_trims_whitespace():
    assert compose_display_name("  Ada  ", "  Lovelace  ", "x") == "Ada Lovelace"


def test_poster_url_passes_through_local_media_path():
    assert poster_url("/api/media/avatars/abc.png") == "/api/media/avatars/abc.png"


def test_poster_url_passes_through_http():
    assert poster_url("http://x/y.jpg") == "http://x/y.jpg"


def test_poster_url_builds_tmdb_path():
    # A TMDB poster path (leading slash) still builds the full CDN URL.
    assert poster_url("/p.jpg") == "https://image.tmdb.org/t/p/w342/p.jpg"
    assert poster_url("p.jpg").startswith("https://image.tmdb.org/")


def test_poster_url_none():
    assert poster_url(None) is None


def test_avatar_upload_requires_auth():
    from app import create_app
    client = create_app().test_client()
    resp = client.post("/api/profiles/some-id/avatar")
    assert resp.status_code == 401
