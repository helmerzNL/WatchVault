"""Health & public meta endpoints (no auth)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from ..config import get_config
from ..db import query_one

bp = Blueprint("meta", __name__, url_prefix="/api")

VERSION = "1.0.0"


@bp.get("/health")
def health():
    db_ok = True
    try:
        query_one("SELECT 1 AS ok")
    except Exception:  # noqa: BLE001
        db_ok = False
    return jsonify({"status": "ok" if db_ok else "degraded", "db": db_ok,
                    "version": VERSION})


@bp.get("/meta/config")
def config():
    cfg = get_config()
    return jsonify({"version": VERSION, "rp_id": cfg.RP_ID, "app": cfg.RP_NAME})
