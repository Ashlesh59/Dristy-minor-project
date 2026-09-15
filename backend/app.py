"""
app.py
--------------------------------------------------------------------------
Entry point of the InvestIQ backend.
--------------------------------------------------------------------------
"""

# load_dotenv() must run before anything else that might read an
# environment variable (Config, financial_service.py, news_service.py
# all use os.environ.get(...)). Calling it as the very first thing in
# this file -- before even the Config import below -- guarantees
# ALPHA_VANTAGE_API_KEY from backend/.env is already in os.environ by
# the time anything asks for it, regardless of import order elsewhere.
# In production, real environment variables would already be set by
# the hosting platform and load_dotenv() simply has nothing to do
# (it's a no-op if no .env file exists), so this is safe either way.
from dotenv import load_dotenv
load_dotenv()

import os

from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from database.db import db
from database.migrations import run_migrations

import models  # noqa: F401
from routes.auth import auth_bp
from routes.research import research_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # SECURITY FIX (Phase 11): fail loudly rather than silently
    # deploying with the well-known dev fallback secret (which is
    # now public in this project's own history) once DEBUG is off.
    # SECRET_KEY signs session cookies -- deploying with a guessable
    # one would let an attacker forge a valid session for any user_id.
    if not app.config["DEBUG"] and app.config["SECRET_KEY"] == "dev-secret-key-change-later":
        raise RuntimeError(
            "SECRET_KEY must be set via the environment before running with "
            "DEBUG=False. Refusing to start with the default development key."
        )

    # supports_credentials=True is required for Phase 4: the frontend
    # will eventually need to send `credentials: "include"` in its
    # fetch() calls so the browser attaches/accepts the session cookie
    # set by POST /api/auth/login. Without this, the browser silently
    # drops that cookie on cross-origin requests and login would
    # appear to "not stick." This doesn't change behavior for the
    # existing /api/test or /api/auth/signup calls, which don't use
    # cookies at all.
    #
    # SECURITY FIX (Phase 11): supports_credentials=True combined with
    # no explicit `origins` means flask-cors reflects back whatever
    # Origin header the request sent -- i.e. ANY website can make an
    # authenticated (cookie-carrying) request to this API and read the
    # response. That's fine for local development (and preserves the
    # exact behavior every prior phase has already been tested
    # against), but is a real cross-origin credential-theft risk in
    # production. In production, an explicit allow-list is now
    # required instead of silently staying wide-open.
    if app.config["DEBUG"]:
        CORS(app, supports_credentials=True)
    else:
        allowed_origins = [
            origin.strip()
            for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        ]
        if not allowed_origins:
            raise RuntimeError(
                "CORS_ALLOWED_ORIGINS must be set to a comma-separated list of "
                "allowed frontend origins before running with DEBUG=False."
            )
        CORS(app, supports_credentials=True, origins=allowed_origins)

    # By default, Flask propagates unhandled exceptions straight to
    # Werkzeug's interactive debugger whenever DEBUG=True (which is
    # this project's default), bypassing any @app.errorhandler(...)
    # entirely. That's normally convenient for local development, but
    # it also means the safe-JSON-500 guarantee below wouldn't
    # actually hold except in production. Setting this explicitly
    # ensures unexpected errors always come back as safe JSON, in
    # every environment, not only when DEBUG happens to be off.
    app.config["PROPAGATE_EXCEPTIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        # Adds any columns models gained after the original schema
        # (e.g. Research.financial_data, User.company) to an existing
        # investiq.db without touching current rows -- see
        # database/migrations.py. db.create_all() alone would silently
        # skip these on a database that already has the users/research
        # tables.
        run_migrations(db)

    @app.route("/api/test", methods=["GET"])
    def test_connection():
        return jsonify({
            "message": "InvestIQ Backend Connected Successfully"
        })

    # ------------------------------------------------------------
    # HEALTH CHECK (Phase 10)
    # ------------------------------------------------------------
    # Deliberately lightweight -- no database query, no auth, no
    # external service call -- so it's cheap enough to be polled
    # frequently (e.g. by a hosting platform's uptime check) and can't
    # itself become a source of failures. It answers "is the Flask
    # process up and responding," not "is every dependency healthy."
    @app.route("/api/health", methods=["GET"])
    def health_check():
        return jsonify({
            "success": True,
            "status": "healthy"
        }), 200

    app.register_blueprint(auth_bp)
    app.register_blueprint(research_bp)

    # ------------------------------------------------------------
    # GLOBAL ERROR HANDLERS (Phase 10)
    # ------------------------------------------------------------
    # Every route added so far already handles its own expected error
    # cases (400/401/404/409/etc.) explicitly with its own jsonify(...)
    # response. These handlers are the safety net underneath all of
    # that: for anything NOT already caught by a route -- a bad URL, a
    # wrong HTTP method, or a genuine unhandled bug -- Flask would
    # otherwise fall back to its default HTML error page (or, in
    # debug mode, an interactive traceback), neither of which is safe
    # or useful for an API client. These make sure every response,
    # even for something that goes wrong unexpectedly, is still the
    # same safe JSON shape the rest of the API already uses, with no
    # stack trace or internal detail included.
    @app.errorhandler(404)
    def handle_not_found(error):
        return jsonify({
            "success": False,
            "message": "The requested resource was not found."
        }), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        return jsonify({
            "success": False,
            "message": "This HTTP method is not allowed for this endpoint."
        }), 405

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        # Only ever log the real error internally -- never put it (or
        # any part of it) in the response sent back to the client.
        app.logger.error("Unhandled exception: %s: %s", type(error).__name__, error)
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred. Please try again later."
        }), 500

    return app


if __name__ == "__main__":
    app = create_app()

    # SECURITY FIX (Phase 11): this used to hardcode debug=True,
    # which meant Config.DEBUG (and therefore FLASK_DEBUG) had no
    # actual effect on whether the interactive Werkzeug debugger was
    # enabled -- it was ALWAYS on when running `python app.py`,
    # regardless of environment. Now it follows the same DEBUG value
    # the rest of the app already uses for CORS/cookie/error-handling
    # decisions above, so setting FLASK_DEBUG=False (or leaving it
    # unset, now that the safe default is False) actually disables it.
    #
    # PORT is read from the environment with the existing 5000 as a
    # fallback, since many hosting platforms assign the port to listen
    # on via an environment variable rather than a fixed number.
    app.run(
        host="0.0.0.0",
        debug=app.config["DEBUG"],
        port=int(os.environ.get("PORT", 5000)),
    )
