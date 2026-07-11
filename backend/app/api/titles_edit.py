"""Manual title & poster overrides.

A household member can rename a film/series (including "Unknown" ones) and
upload a custom poster. Once a field carries a manual override it is locked: the
TMDB/Trakt enrichment path (``catalog.apply_title_details``) skips it, so metadata
can never replace a hand-set value. Removing an override restores the previous
(enriched) value from ``metadata->'manual_orig'`` and clears ``enriched_at`` so a
fresh enrichment pass can take over again on the next open.

Titles are a global catalogue, so any member with ``ingest.write`` may edit them;
this mirrors the other title-mutation endpoints (enrich, platform-override).
"""
from __future__ import annotations

import json
import os
import uuid

from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from ..config import get_config
from ..db import connection, query_one
from ..auth.sessions import require_perm
from ._common import poster_url

bp = Blueprint("titles_edit", __name__, url_prefix="/api")

_POSTER_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_POSTER_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_TITLE_MAX_LEN = 500


def _posters_dir() -> str:
    d = os.path.join(get_config().DATA_DIR, "media", "posters")
    os.makedirs(d, exist_ok=True)
    return d


def _remove_local_poster(path) -> None:
    """Best-effort delete of a previously uploaded local poster file."""
    if path and isinstance(path, str) and path.startswith("/api/media/posters/"):
        try:
            os.remove(os.path.join(_posters_dir(), os.path.basename(path)))
        except OSError:
            pass


def _manual_orig(meta: dict) -> dict:
    orig = meta.get("manual_orig")
    return dict(orig) if isinstance(orig, dict) else {}


@bp.patch("/titles/<title_id>/rename")
@require_perm("ingest.write")
def rename_title(title_id: str):
    """Set a manual title override. Locks ``title`` against enrichment."""
    body = request.get_json(silent=True) or {}
    new_title = (body.get("title") or "").strip()
    if not new_title:
        return jsonify({"error": "title required"}), 400
    if len(new_title) > _TITLE_MAX_LEN:
        return jsonify({"error": "title too long"}), 400

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT title, metadata, manual_title FROM titles WHERE id = %s",
                    (title_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        meta = dict(row.get("metadata") or {})
        orig = _manual_orig(meta)
        # Stash the pre-override value only on the first override so a later
        # "remove" restores the genuine enriched/imported title.
        if not row["manual_title"]:
            orig["title"] = row["title"]
        meta["manual_orig"] = orig
        cur.execute(
            "UPDATE titles SET title = %s, manual_title = true, "
            "metadata = %s::jsonb, updated_at = now() WHERE id = %s",
            (new_title, json.dumps(meta), title_id))
    return jsonify({"ok": True, "title": new_title, "manual_title": True})


@bp.delete("/titles/<title_id>/rename")
@require_perm("ingest.write")
def clear_title_override(title_id: str):
    """Remove the manual title override: restore the stashed value and re-enable
    enrichment (``enriched_at = NULL``)."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT title, metadata, manual_title FROM titles WHERE id = %s",
                    (title_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        if not row["manual_title"]:
            return jsonify({"ok": True, "title": row["title"], "manual_title": False})
        meta = dict(row.get("metadata") or {})
        orig = _manual_orig(meta)
        restored = orig.pop("title", None) or row["title"]
        if orig:
            meta["manual_orig"] = orig
        else:
            meta.pop("manual_orig", None)
        cur.execute(
            "UPDATE titles SET title = %s, manual_title = false, "
            "metadata = %s::jsonb, enriched_at = NULL, updated_at = now() "
            "WHERE id = %s",
            (restored, json.dumps(meta), title_id))
    return jsonify({"ok": True, "title": restored, "manual_title": False})


@bp.post("/titles/<title_id>/poster")
@require_perm("ingest.write")
def upload_poster(title_id: str):
    """Upload a custom poster. Locks ``poster_path`` against enrichment."""
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    f = request.files["file"]
    ext = _POSTER_EXT.get((f.mimetype or "").lower())
    if not ext:
        return jsonify({"error": "unsupported image type"}), 400
    data = f.read()
    if not data:
        return jsonify({"error": "empty file"}), 400
    if len(data) > _POSTER_MAX_BYTES:
        return jsonify({"error": "file too large"}), 413

    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT poster_path, metadata, manual_poster FROM titles WHERE id = %s",
            (title_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404

        fname = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(_posters_dir(), fname), "wb") as out:
            out.write(data)
        stored = f"/api/media/posters/{fname}"

        meta = dict(row.get("metadata") or {})
        orig = _manual_orig(meta)
        if not row["manual_poster"]:
            # First override: remember the enriched poster so "remove" restores it.
            orig["poster_path"] = row["poster_path"]
        else:
            # Replacing an existing manual poster: drop the superseded local file.
            _remove_local_poster(row["poster_path"])
        meta["manual_orig"] = orig
        cur.execute(
            "UPDATE titles SET poster_path = %s, manual_poster = true, "
            "metadata = %s::jsonb, updated_at = now() WHERE id = %s",
            (stored, json.dumps(meta), title_id))
    return jsonify({"ok": True, "poster": poster_url(stored), "manual_poster": True})


@bp.delete("/titles/<title_id>/poster")
@require_perm("ingest.write")
def clear_poster_override(title_id: str):
    """Remove the manual poster override: delete the uploaded file, restore the
    stashed poster and re-enable enrichment (``enriched_at = NULL``) so metadata
    can refill it on the next open."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT poster_path, metadata, manual_poster FROM titles WHERE id = %s",
            (title_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        if not row["manual_poster"]:
            return jsonify({"ok": True, "poster": poster_url(row["poster_path"]),
                            "manual_poster": False})
        _remove_local_poster(row["poster_path"])
        meta = dict(row.get("metadata") or {})
        orig = _manual_orig(meta)
        restored = orig.pop("poster_path", None)
        if orig:
            meta["manual_orig"] = orig
        else:
            meta.pop("manual_orig", None)
        cur.execute(
            "UPDATE titles SET poster_path = %s, manual_poster = false, "
            "metadata = %s::jsonb, enriched_at = NULL, updated_at = now() "
            "WHERE id = %s",
            (restored, json.dumps(meta), title_id))
    return jsonify({"ok": True, "poster": poster_url(restored), "manual_poster": False})


_KINDS = ("movie", "series", "tv")


def apply_kind_change(cur, title_id: str, kind: str) -> dict | None:
    """Set a title's category by hand, merging into an existing same-name row of
    the target category when one exists.

    Titles are unique on ``(kind, normalized_key)``, so a bare
    ``UPDATE titles SET kind=…`` collides (UniqueViolation → 500) when another row
    already holds ``(kind, normalized_key)`` — the common case being a hand-curated
    "TV Kijken" (``tv``) entry alongside the movie row of the same programme. When
    that target row exists it stays canonical (it is already the desired kind, and
    ``tv`` rows are only ever created by hand, so its curation must win); the
    current row is folded into it via ``wv_merge_titles`` (watch events, episodes,
    live sessions and progress move over, empty scalars fill, the dup is deleted).

    Returns ``{"title_id", "merged"}`` — ``title_id`` is the surviving row (the
    canonical one on a merge) so the caller can redirect the UI — or ``None`` when
    the title does not exist. Runs entirely on the caller-owned cursor/transaction.
    """
    cur.execute("SELECT normalized_key FROM titles WHERE id = %s", (title_id,))
    row = cur.fetchone()
    if not row:
        return None
    # The Unknown override only makes sense for series; drop it otherwise so a
    # movie/tv title never lingers as a forced-Unknown series.
    clear_unknown = kind != "series"
    cur.execute(
        "SELECT id FROM titles WHERE kind = %s AND normalized_key = %s AND id <> %s "
        "LIMIT 1",
        (kind, row["normalized_key"], title_id))
    collision = cur.fetchone()
    if collision:
        canonical = str(collision["id"])
        cur.execute("SELECT wv_merge_titles(%s::uuid, %s::uuid)", (canonical, title_id))
        cur.execute(
            "UPDATE titles SET kind = %s, manual_kind = true, "
            "manual_unknown = CASE WHEN %s THEN NULL ELSE manual_unknown END, "
            "updated_at = now() WHERE id = %s",
            (kind, clear_unknown, canonical))
        return {"title_id": canonical, "merged": True}
    cur.execute(
        "UPDATE titles SET kind = %s, manual_kind = true, "
        "manual_unknown = CASE WHEN %s THEN NULL ELSE manual_unknown END, "
        "updated_at = now() WHERE id = %s",
        (kind, clear_unknown, title_id))
    return {"title_id": title_id, "merged": False}


@bp.put("/titles/<title_id>/kind")
@require_perm("ingest.write")
def set_kind(title_id: str):
    """Change a title's category by hand between Film, Series and "TV Kijken".

    Body ``{"kind": "movie"|"series"|"tv"}``. Setting the category by hand locks
    it (``manual_kind = true``) so TMDB/Trakt enrichment can no longer flip it.
    Switching away from ``series`` also clears any manual "Unknown" override, as
    the Unknown bucket only applies to series. When a row of the target category
    with the same name already exists, this title is merged into it (see
    ``apply_kind_change``) and the response's ``title_id`` is the survivor.
    """
    body = request.get_json(silent=True) or {}
    kind = (body.get("kind") or "").strip().lower()
    if kind not in _KINDS:
        return jsonify({"error": "kind must be one of movie, series, tv"}), 400

    with connection() as conn, conn.cursor() as cur:
        result = apply_kind_change(cur, title_id, kind)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True, "kind": kind, "manual_kind": True, **result})


@bp.get("/media/posters/<name>")
def serve_poster(name: str):
    safe = secure_filename(name)
    if not safe:
        return jsonify({"error": "not found"}), 404
    return send_from_directory(_posters_dir(), safe, max_age=3600)


@bp.put("/titles/<title_id>/unknown")
@require_perm("ingest.write")
def set_unknown(title_id: str):
    """Move a title into or out of the derived "Unknown" category by hand.

    Body ``{"unknown": true|false|null}`` — ``true`` forces Unknown, ``false``
    forces "known", and ``null`` clears the override so the automatic rule
    (a series with no recognized season/episode) applies again.
    """
    body = request.get_json(silent=True) or {}
    if "unknown" not in body:
        return jsonify({"error": "unknown flag required"}), 400
    value = body["unknown"]
    if value is not None and not isinstance(value, bool):
        return jsonify({"error": "unknown must be a boolean or null"}), 400

    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM titles WHERE id = %s", (title_id,))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
        cur.execute(
            "UPDATE titles SET manual_unknown = %s, updated_at = now() WHERE id = %s",
            (value, title_id))
        cur.execute("SELECT wv_title_is_unknown(%s) AS u", (title_id,))
        effective = bool(cur.fetchone()["u"])
    return jsonify({"ok": True, "unknown": effective, "manual_unknown": value})

