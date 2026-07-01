"""Canonical genre names + alias resolution.

Different providers report genres in different languages/spellings: Jellyfin
returns names localized to its server language (a Dutch server sends "Misdaad",
"Komedie"), while TMDB/Trakt return canonical English ("Crime", "Comedy"). Left
alone the ``genres`` table accumulates one row per language for the same concept,
so the Search dropdown shows "Misdaad" and "Crime" as separate options.

This module maps every known localized/variant spelling back to a single
canonical English name (the same keys the frontend i18n genre map translates
from). ``upsert_genre`` normalizes through :func:`canonical_genre` so ingests
converge, and migration ``0020`` reconciles rows already split in the database
using the exact same mapping (kept here as the single source of truth).
"""
from __future__ import annotations

# Canonical English name -> its translations in [nl, fr, es, it, de].
# Mirrors the GENRES map in frontend/src/lib/i18n.tsx.
_TRANSLATIONS: dict[str, list[str]] = {
    "Action": ["Actie", "Action", "Acción", "Azione", "Action"],
    "Adventure": ["Avontuur", "Aventure", "Aventura", "Avventura", "Abenteuer"],
    "Animation": ["Animatie", "Animation", "Animación", "Animazione", "Animation"],
    "Comedy": ["Komedie", "Comédie", "Comedia", "Commedia", "Komödie"],
    "Crime": ["Misdaad", "Crime", "Crimen", "Crimine", "Krimi"],
    "Documentary": ["Documentaire", "Documentaire", "Documental", "Documentario", "Dokumentarfilm"],
    "Drama": ["Drama", "Drame", "Drama", "Dramma", "Drama"],
    "Family": ["Familie", "Familial", "Familia", "Famiglia", "Familie"],
    "Fantasy": ["Fantasy", "Fantastique", "Fantasía", "Fantasy", "Fantasy"],
    "History": ["Historisch", "Histoire", "Historia", "Storia", "Historie"],
    "Horror": ["Horror", "Horreur", "Terror", "Horror", "Horror"],
    "Music": ["Muziek", "Musique", "Música", "Musica", "Musik"],
    "Mystery": ["Mysterie", "Mystère", "Misterio", "Mistero", "Mystery"],
    "Romance": ["Romantiek", "Romance", "Romance", "Romantico", "Liebesfilm"],
    "Science Fiction": ["Sciencefiction", "Science-fiction", "Ciencia ficción", "Fantascienza", "Science Fiction"],
    "TV Movie": ["Tv-film", "Téléfilm", "Película de TV", "Film TV", "TV-Film"],
    "Thriller": ["Thriller", "Thriller", "Suspense", "Thriller", "Thriller"],
    "War": ["Oorlog", "Guerre", "Bélica", "Guerra", "Krieg"],
    "Western": ["Western", "Western", "Western", "Western", "Western"],
    "Action & Adventure": ["Actie & Avontuur", "Action & Aventure", "Acción y aventura", "Azione e avventura", "Action & Abenteuer"],
    "Kids": ["Kinderen", "Enfants", "Infantil", "Bambini", "Kinder"],
    "News": ["Nieuws", "Actualités", "Noticias", "Notizie", "Nachrichten"],
    "Reality": ["Reality", "Téléréalité", "Reality", "Reality", "Reality"],
    "Sci-Fi & Fantasy": ["Sci-Fi & Fantasy", "Sci-Fi & Fantastique", "Sci-Fi y fantasía", "Sci-Fi e fantasy", "Sci-Fi & Fantasy"],
    "Soap": ["Soap", "Feuilleton", "Telenovela", "Soap", "Seifenoper"],
    "Talk": ["Talkshow", "Talk-show", "Programa de entrevistas", "Talk show", "Talk"],
    "War & Politics": ["Oorlog & Politiek", "Guerre & Politique", "Guerra y política", "Guerra e politica", "Krieg & Politik"],
}


def _build_alias_map() -> dict[str, str]:
    """lower(alias) -> canonical English name (canonical maps to itself too)."""
    amap: dict[str, str] = {}
    for canonical, translations in _TRANSLATIONS.items():
        for alias in [canonical, *translations]:
            key = alias.strip().lower()
            if key:
                amap.setdefault(key, canonical)
    return amap


ALIAS_TO_CANONICAL: dict[str, str] = _build_alias_map()


def canonical_genre(name: str) -> str:
    """Return the canonical English genre name for ``name``.

    Unknown genres (custom/provider-specific tags not in the map) are returned
    trimmed but otherwise unchanged, so nothing is lost.
    """
    if not name:
        return name
    trimmed = name.strip()
    return ALIAS_TO_CANONICAL.get(trimmed.lower(), trimmed)
