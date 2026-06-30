"""WatchVault Flask application factory."""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from flask import Flask, jsonify
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

from .config import get_config


class WVJSONProvider(DefaultJSONProvider):
    """ISO-8601 datetimes and stringified UUIDs."""
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, (dt.datetime, dt.date)):
            return o.isoformat()
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, set):
            return sorted(o)
        return DefaultJSONProvider.default(o)


def create_app() -> Flask:
    cfg = get_config()
    logging.basicConfig(level=getattr(logging, cfg.LOG_LEVEL, logging.INFO))

    app = Flask(__name__)
    app.json = WVJSONProvider(app)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB uploads

    # Blueprints
    from .api import meta, stats, search, ingest, profiles, plugins, sync, people, attribution
    from .auth import routes as auth_routes

    app.register_blueprint(meta.bp)
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(ingest.bp)
    app.register_blueprint(stats.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(profiles.bp)
    app.register_blueprint(plugins.bp)
    app.register_blueprint(sync.bp)
    app.register_blueprint(people.bp)
    app.register_blueprint(attribution.bp)

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException):
        return jsonify({"error": exc.name, "message": exc.description}), exc.code

    @app.errorhandler(Exception)
    def handle_error(exc: Exception):  # noqa: BLE001
        app.logger.exception("Unhandled error")
        msg = str(exc) if cfg.APP_ENV != "production" else "internal server error"
        return jsonify({"error": "internal_error", "message": msg}), 500

    return app
