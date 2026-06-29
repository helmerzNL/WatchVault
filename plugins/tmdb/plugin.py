"""TMDB metadata provider plugin.

Privacy: only public title/person *search* terms are sent to TMDB — never any
personal watch history. The app runs fine without an API key configured (every
method returns empty and enrichment is skipped).
"""
from __future__ import annotations

from typing import Any, Optional

import requests

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"


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

    def movie_details(self, tmdb_id: int) -> Optional[dict]:
        data = self._get(f"/movie/{tmdb_id}", {"append_to_response": "credits"})
        return self._normalize(data, "movie") if data else None

    def tv_details(self, tmdb_id: int) -> Optional[dict]:
        data = self._get(f"/tv/{tmdb_id}", {"append_to_response": "credits"})
        return self._normalize(data, "series") if data else None

    def person_details(self, tmdb_id: int) -> Optional[dict]:
        return self._get(f"/person/{tmdb_id}")

    # ── Normalization to the central model shape ───────────────────────────

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
        return {
            "tmdb_id": data.get("id"),
            "title": data.get("title") or data.get("name"),
            "original_title": data.get("original_title") or data.get("original_name"),
            "overview": data.get("overview"),
            "year": int(year) if year.isdigit() else None,
            "runtime_minutes": runtime,
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "genres": [g.get("name") for g in data.get("genres", [])],
            "imdb_id": data.get("imdb_id"),
            "cast": cast,
            "crew": crew,
        }
