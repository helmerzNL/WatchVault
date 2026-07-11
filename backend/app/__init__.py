"""WatchVault Flask application factory."""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from flask import Flask, jsonify, request
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
    from .api import meta, stats, search, ingest, profiles, plugins, sync, people, attribution, scrobble, tags, titles_edit
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
    app.register_blueprint(scrobble.bp)
    app.register_blueprint(tags.bp)
    app.register_blueprint(titles_edit.bp)

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException):
        # 4xx are expected client errors; 5xx signal a real server fault that would
        # otherwise be returned with no trace — log those with request context.
        if exc.code and exc.code >= 500:
            app.logger.exception("HTTP %s on %s %s", exc.code, request.method, request.path)
        return jsonify({"error": exc.name, "message": exc.description}), exc.code

    @app.errorhandler(Exception)
    def handle_error(exc: Exception):  # noqa: BLE001
        # Include the request method + path so the logged traceback points at the
        # endpoint that failed (e.g. a UniqueViolation from a title edit).
        app.logger.exception("Unhandled error on %s %s", request.method, request.path)
        msg = str(exc) if cfg.APP_ENV != "production" else "internal server error"
        return jsonify({"error": "internal_error", "message": msg}), 500

    return app
