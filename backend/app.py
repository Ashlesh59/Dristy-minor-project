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
from routes.companies import companies_bp
from routes.securities import securities_bp



def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    # Apply test configuration before any validation, database initialization, or migrations
    if test_config:
        app.config.update(test_config)

    # ------------------------------------------------------------
    # PHASE 0: TEST-RUN SENTINEL & DATABASE SAFETY CHECK
    # ------------------------------------------------------------
    # If INVESTIQ_TEST_RUN=1 is active, we enforce that testing mode is
    # strictly engaged and that the configured database is NOT the
    # development/production investiq.db file.
    if os.environ.get("INVESTIQ_TEST_RUN") == "1":
        if not app.config.get("TESTING"):
            raise RuntimeError(
                "INVESTIQ_TEST_RUN sentinel is active but TESTING is not True."
            )
        
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if not db_uri:
            raise RuntimeError(
                "INVESTIQ_TEST_RUN sentinel is active but SQLALCHEMY_DATABASE_URI is empty."
            )

        dev_db_path = os.path.abspath(os.path.join(Config.BASE_DIR, "database", "investiq.db"))
        
        # Check if URI resolves to the development investiq.db file
        if db_uri.startswith("sqlite:///"):
            raw_path = db_uri.replace("sqlite:///", "")
            if raw_path != ":memory:":
                resolved_path = os.path.abspath(raw_path)
                if os.path.normcase(resolved_path) == os.path.normcase(dev_db_path) or "investiq.db" in os.path.basename(resolved_path):
                    raise RuntimeError(
                        f"INVESTIQ_TEST_RUN violation: Configured test database resolves to "
                        f"development database ({resolved_path}). Refusing to run tests on live data."
                    )
        elif db_uri != "sqlite:///:memory:":
            raise RuntimeError(
                f"INVESTIQ_TEST_RUN violation: Test database must be an isolated temporary SQLite database or :memory:, got: {db_uri}"
            )

    is_testing = app.config.get("TESTING", False)

    # SECURITY FIX (Phase 11 & Phase D1): fail loudly rather than silently
    # deploying with missing or unsafe variables in production.
    if not is_testing and not app.config["DEBUG"]:
        if app.config["SECRET_KEY"] == "dev-secret-key-change-later":
            raise RuntimeError(
                "SECRET_KEY must be set via the environment before running with "
                "DEBUG=False. Refusing to start with the default development key."
            )
        if not os.environ.get("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL is required in production (DEBUG=False).")
        if not os.environ.get("GEMINI_API_KEY"):
            raise RuntimeError("GEMINI_API_KEY is required in production (DEBUG=False).")

    # CORS configuration
    if app.config["DEBUG"] or is_testing:
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

    # Exception propagation
    app.config["PROPAGATE_EXCEPTIONS"] = False

    db.init_app(app)

    with app.app_context():
        db.create_all()
        # Migration execution is controlled by RUN_MIGRATIONS (False in test mode)
        if app.config.get("RUN_MIGRATIONS", True):
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
        db_status = "connected"
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:
            db_status = "unavailable"

        return jsonify({
            "success": True,
            "status": "healthy" if db_status == "connected" else "degraded",
            "database": db_status,
            "services": {
                "alpha_vantage": bool(os.environ.get("ALPHA_VANTAGE_API_KEY")),
                "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            },
            "environment": "development" if app.config["DEBUG"] else "production"
        }), 200

    app.register_blueprint(auth_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(securities_bp)


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
