"""Household media tags: create/manage shared tags and attach them to titles,
episodes and whole seasons.

Tags are scoped to a household (everyone in a household shares the same set).
Titles are a global catalogue, so every read/write filters the link tables by the
caller's household via the owning ``tags.household_id`` — a household can only ever
see or mutate its own tags and their attachments.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import connection, query_all, query_one
from ..auth.sessions import current_user, require_perm

bp = Blueprint("tags", __name__, url_prefix="/api")


def _household_id() -> str:
    return str(current_user()["household_id"])


def _tag_row(r: dict) -> dict:
    return {"id": str(r["id"]), "name": r["name"], "color": r["color"]}


def _owned_tag(cur, tag_id: str, household_id: str):
    """Return the tag row iff it belongs to this household, else None."""
    cur.execute("SELECT id FROM tags WHERE id = %s AND household_id = %s",
                (tag_id, household_id))
    return cur.fetchone()


# ── Helpers shared with the title-detail endpoint ──────────────────────────

def tags_for_title(title_id: str, household_id: str) -> list[dict]:
    rows = query_all(
        "SELECT tg.id, tg.name, tg.color FROM title_tags tt "
        "JOIN tags tg ON tg.id = tt.tag_id "
        "WHERE tt.title_id = %s AND tg.household_id = %s ORDER BY lower(tg.name)",
        (title_id, household_id))
    return [_tag_row(r) for r in rows]


def season_tags_map(title_id: str, household_id: str) -> dict[int, list[dict]]:
    rows = query_all(
        "SELECT st.season, tg.id, tg.name, tg.color FROM season_tags st "
        "JOIN tags tg ON tg.id = st.tag_id "
        "WHERE st.title_id = %s AND tg.household_id = %s ORDER BY lower(tg.name)",
        (title_id, household_id))
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(int(r["season"]), []).append(_tag_row(r))
    return out


def episode_tags_map(title_id: str, household_id: str) -> dict[str, list[dict]]:
    rows = query_all(
        "SELECT et.episode_id, tg.id, tg.name, tg.color FROM episode_tags et "
        "JOIN tags tg ON tg.id = et.tag_id "
        "JOIN title_episodes te ON te.id = et.episode_id "
        "WHERE te.title_id = %s AND tg.household_id = %s ORDER BY lower(tg.name)",
        (title_id, household_id))
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r["episode_id"]), []).append(_tag_row(r))
    return out


# ── Tag management (create / list / update / delete) ───────────────────────

@bp.get("/tags")
@require_perm("catalog.read")
def list_tags():
    """All tags for the household with how many titles/seasons/episodes use each."""
    hid = _household_id()
    rows = query_all(
        "SELECT tg.id, tg.name, tg.color, "
        "  (SELECT count(*) FROM title_tags tt WHERE tt.tag_id = tg.id) "
        "  + (SELECT count(*) FROM season_tags st WHERE st.tag_id = tg.id) "
        "  + (SELECT count(*) FROM episode_tags et WHERE et.tag_id = tg.id) AS uses "
        "FROM tags tg WHERE tg.household_id = %s ORDER BY lower(tg.name)",
        (hid,))
    return jsonify([{**_tag_row(r), "uses": int(r["uses"])} for r in rows])


@bp.post("/tags")
@require_perm("ingest.write")
def create_tag():
    hid = _household_id()
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    color = (body.get("color") or "").strip() or None
    if not name:
        return jsonify({"error": "name required"}), 400
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM tags WHERE household_id = %s AND lower(name) = lower(%s)",
            (hid, name))
        if cur.fetchone():
            return jsonify({"error": "exists"}), 409
        cur.execute(
            "INSERT INTO tags (household_id, name, color) VALUES (%s, %s, %s) "
            "RETURNING id, name, color",
            (hid, name, color))
        row = cur.fetchone()
    return jsonify(_tag_row(row)), 201


@bp.put("/tags/<tag_id>")
@require_perm("ingest.write")
def update_tag(tag_id: str):
    hid = _household_id()
    body = request.get_json(silent=True) or {}
    with connection() as conn, conn.cursor() as cur:
        if not _owned_tag(cur, tag_id, hid):
            return jsonify({"error": "not found"}), 404
        name = body.get("name")
        color = body.get("color")
        if name is not None:
            name = name.strip()
            if not name:
                return jsonify({"error": "name required"}), 400
            cur.execute(
                "SELECT id FROM tags WHERE household_id = %s AND lower(name) = lower(%s) "
                "AND id <> %s", (hid, name, tag_id))
            if cur.fetchone():
                return jsonify({"error": "exists"}), 409
        cur.execute(
            "UPDATE tags SET name = COALESCE(%s, name), color = %s "
            "WHERE id = %s RETURNING id, name, color",
            (name, (color.strip() or None) if isinstance(color, str) else None if color is None else color,
             tag_id))
        row = cur.fetchone()
    return jsonify(_tag_row(row))


@bp.delete("/tags/<tag_id>")
@require_perm("ingest.write")
def delete_tag(tag_id: str):
    hid = _household_id()
    with connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM tags WHERE id = %s AND household_id = %s RETURNING id",
                    (tag_id, hid))
        if not cur.fetchone():
            return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


# ── Attach / detach to a title, episode or season ──────────────────────────

def _attach(link_sql: str, args: tuple, tag_id: str) -> tuple:
    hid = _household_id()
    with connection() as conn, conn.cursor() as cur:
        if not _owned_tag(cur, tag_id, hid):
            return jsonify({"error": "tag not found"}), 404
        cur.execute(link_sql, args)
    return jsonify({"ok": True}), 200


@bp.post("/titles/<title_id>/tags/<tag_id>")
@require_perm("ingest.write")
def tag_title(title_id: str, tag_id: str):
    return _attach(
        "INSERT INTO title_tags (title_id, tag_id) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING", (title_id, tag_id), tag_id)


@bp.delete("/titles/<title_id>/tags/<tag_id>")
@require_perm("ingest.write")
def untag_title(title_id: str, tag_id: str):
    return _attach("DELETE FROM title_tags WHERE title_id = %s AND tag_id = %s",
                   (title_id, tag_id), tag_id)


@bp.post("/episodes/<episode_id>/tags/<tag_id>")
@require_perm("ingest.write")
def tag_episode(episode_id: str, tag_id: str):
    return _attach(
        "INSERT INTO episode_tags (episode_id, tag_id) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING", (episode_id, tag_id), tag_id)


@bp.delete("/episodes/<episode_id>/tags/<tag_id>")
@require_perm("ingest.write")
def untag_episode(episode_id: str, tag_id: str):
    return _attach("DELETE FROM episode_tags WHERE episode_id = %s AND tag_id = %s",
                   (episode_id, tag_id), tag_id)


@bp.post("/titles/<title_id>/seasons/<int:season>/tags/<tag_id>")
@require_perm("ingest.write")
def tag_season(title_id: str, season: int, tag_id: str):
    return _attach(
        "INSERT INTO season_tags (title_id, season, tag_id) VALUES (%s, %s, %s) "
        "ON CONFLICT DO NOTHING", (title_id, season, tag_id), tag_id)


@bp.delete("/titles/<title_id>/seasons/<int:season>/tags/<tag_id>")
@require_perm("ingest.write")
def untag_season(title_id: str, season: int, tag_id: str):
    return _attach(
        "DELETE FROM season_tags WHERE title_id = %s AND season = %s AND tag_id = %s",
        (title_id, season, tag_id), tag_id)
