"""TMDB metadata provider plugin.

Privacy: only public title/person *search* terms are sent to TMDB — never any
personal watch history. The app runs fine without an API key configured (every
method returns empty and enrichment is skipped).

Multilingual: details are fetched with ``append_to_response=translations`` so a
single request yields the overview/biography in every language WatchVault
supports (en, nl, fr, es, it, de).
"""
from __future__ import annotations

from typing import Any, Optional

import requests

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"

# ISO-639-1 codes the app exposes in its language picker.
TARGET_LANGS = ["en", "nl", "fr", "es", "it", "de"]


class Plugin:
    def __init__(self, settings: dict | None = None, secrets: dict | None = None) -> None:
        self.settings = settings or {}
        self.secrets = secrets or {}
        self.api_key = (self.secrets.get("api_key") or "").strip()
        self.language = self.settings.get("language", "en-US")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, params: dict | None = None) -> Optional[dict]:
        if not self.api_key:
            return None
        p = {"api_key": self.api_key, "language": self.language}
        if params:
            p.update(params)
        try:
            resp = requests.get(f"{API_BASE}{path}", params=p, timeout=20)
            if resp.status_code != 200:
                return None
            return resp.json()
        except requests.RequestException:
            return None

    # ── Capabilities ───────────────────────────────────────────────────────

    def search(self, query: str, year: int | None = None, kind: str = "movie") -> list[dict]:
        endpoint = "/search/tv" if kind == "series" else "/search/movie"
        params: dict[str, Any] = {"query": query, "include_adult": "false"}
        if year:
            params["year" if kind != "series" else "first_air_date_year"] = year
        data = self._get(endpoint, params)
        if not data:
            return []
        return data.get("results", [])

    def search_person(self, name: str) -> list[dict]:
        data = self._get("/search/person", {"query": name, "include_adult": "false"})
        if not data:
            return []
        return data.get("results", [])

    def movie_details(self, tmdb_id: int) -> Optional[dict]:
        data = self._get(f"/movie/{tmdb_id}",
                         {"append_to_response": "credits,translations"})
        return self._normalize(data, "movie") if data else None

    def tv_details(self, tmdb_id: int) -> Optional[dict]:
        data = self._get(f"/tv/{tmdb_id}",
                         {"append_to_response": "credits,translations"})
        return self._normalize(data, "series") if data else None

    def tv_season(self, tmdb_id: int, season_number: int) -> Optional[dict]:
        """Full episode list for one season of a series."""
        data = self._get(f"/tv/{tmdb_id}/season/{season_number}")
        if not data:
            return None
        return {
            "season_number": data.get("season_number"),
            "name": data.get("name"),
            "overview": data.get("overview"),
            "poster_path": data.get("poster_path"),
            "air_date": data.get("air_date") or None,
            "episodes": [
                {"episode_number": e.get("episode_number"), "name": e.get("name"),
                 "overview": e.get("overview"), "air_date": e.get("air_date") or None,
                 "runtime_minutes": e.get("runtime"), "still_path": e.get("still_path"),
                 "tmdb_id": e.get("id"), "vote_average": e.get("vote_average")}
                for e in data.get("episodes", [])
            ],
        }

    def person_details(self, tmdb_id: int) -> Optional[dict]:
        data = self._get(f"/person/{tmdb_id}", {"append_to_response": "translations"})
        return self._normalize_person(data) if data else None

    # ── Normalization to the central model shape ───────────────────────────

    @staticmethod
    def _lang_map(data: dict, base_lang: str, field: str = "overview") -> dict:
        """Collect a {lang: text} map from append_to_response=translations."""
        out: dict[str, str] = {}
        base = data.get(field)
        if base and base.strip() and base_lang in TARGET_LANGS:
            out[base_lang] = base.strip()
        translations = (data.get("translations") or {}).get("translations", [])
        for tr in translations:
            lang = tr.get("iso_639_1")
            if lang not in TARGET_LANGS or lang in out:
                continue
            text = (tr.get("data") or {}).get(field)
            if text and text.strip():
                out[lang] = text.strip()
        return out

    def _normalize(self, data: dict, kind: str) -> dict:
        credits = data.get("credits", {})
        cast = [
            {"tmdb_id": c.get("id"), "name": c.get("name"),
             "character": c.get("character"), "ord": c.get("order", 999),
             "profile_path": c.get("profile_path")}
            for c in credits.get("cast", [])[:15]
        ]
        crew = [
            {"tmdb_id": c.get("id"), "name": c.get("name"),
             "job": c.get("job"), "profile_path": c.get("profile_path")}
            for c in credits.get("crew", [])
            if c.get("job") in ("Director", "Creator", "Writer")
        ]
        if kind == "series":
            year = (data.get("first_air_date") or "")[:4]
            runtime = (data.get("episode_run_time") or [None])[0]
        else:
            year = (data.get("release_date") or "")[:4]
            runtime = data.get("runtime")
        base_lang = (self.language or "en")[:2]
        overviews = self._lang_map(data, base_lang)
        result = {
            "tmdb_id": data.get("id"),
            "title": data.get("title") or data.get("name"),
            "original_title": data.get("original_title") or data.get("original_name"),
            "overview": overviews.get("en") or data.get("overview"),
            "overviews": overviews,
            "year": int(year) if year.isdigit() else None,
            "release_date": data.get("release_date") or data.get("first_air_date") or None,
            "runtime_minutes": runtime,
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "genres": [g.get("name") for g in data.get("genres", [])],
            "imdb_id": data.get("imdb_id"),
            "cast": cast,
            "crew": crew,
            "authoritative": True,
        }
        if kind == "series":
            result["number_of_seasons"] = data.get("number_of_seasons")
            result["number_of_episodes"] = data.get("number_of_episodes")
            result["networks"] = [
                {"id": n.get("id"), "name": n.get("name"),
                 "logo_path": n.get("logo_path")}
                for n in data.get("networks", [])
                if n.get("name")
            ]
            result["seasons"] = [
                {"season_number": s.get("season_number"), "name": s.get("name"),
                 "overview": s.get("overview"), "poster_path": s.get("poster_path"),
                 "air_date": s.get("air_date") or None, "episode_count": s.get("episode_count")}
                for s in data.get("seasons", [])
                if s.get("season_number") is not None
            ]
        return result

    def _normalize_person(self, data: dict) -> dict:
        base_lang = (self.language or "en")[:2]
        biographies = self._lang_map(data, base_lang, field="biography")
        return {
            "tmdb_id": data.get("id"),
            "name": data.get("name"),
            "biography": biographies.get("en") or data.get("biography"),
            "biographies": biographies,
            "birthday": data.get("birthday") or None,
            "deathday": data.get("deathday") or None,
            "place_of_birth": data.get("place_of_birth"),
            "known_for": data.get("known_for_department"),
            "also_known_as": data.get("also_known_as") or [],
            "profile_path": data.get("profile_path"),
        }
