"""
config.py
--------------------------------------------------------------------------
Central place for application configuration.
--------------------------------------------------------------------------
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-later")

    # SECURITY FIX (Phase 11): previously defaulted to "True", meaning
    # debug mode -- and Werkzeug's interactive in-browser debugger,
    # which can allow arbitrary code execution if ever reachable --
    # would silently turn on in any deployment that forgot to set
    # FLASK_DEBUG explicitly. Defaulting to "False" means the SAFE
    # option is what happens automatically; local development now
    # requires deliberately setting FLASK_DEBUG=True (e.g. in
    # backend/.env, alongside ALPHA_VANTAGE_API_KEY/GEMINI_API_KEY)
    # to opt back into the previous auto-reload/debugger convenience.
    DEBUG = os.environ.get("FLASK_DEBUG", "False") == "True"

    # ------------------------------------------------------------
    # DATABASE CONFIGURATION (Phase 2 & Phase D1)
    # ------------------------------------------------------------
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = database_url
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
            BASE_DIR, "database", "investiq.db"
        )
        SQLALCHEMY_ENGINE_OPTIONS = {}

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RUN_MIGRATIONS = True


    # ------------------------------------------------------------
    # SESSION COOKIE SECURITY (Phase 11)
    # ------------------------------------------------------------
    # HTTPONLY: stops any JavaScript (including injected via an XSS
    # bug elsewhere) from reading the session cookie -- it can only be
    # sent by the browser over HTTP(S), never accessed via
    # document.cookie. This was already Flask's own default, but is
    # made explicit here so it's visible in an audit rather than
    # relying on a library default.
    SESSION_COOKIE_HTTPONLY = True

    # SAMESITE=Lax: the standard safe default: the cookie is still
    # sent on normal top-level navigation (so a plain link to the app
    # works) but withheld from most cross-site requests, which is a
    # real mitigation against CSRF. This matches the cookie behavior
    # this project has already been tested against (curl's cookie jar
    # doesn't apply SameSite rules, so this is not a behavior change
    # for the testing done in every prior phase).
    SESSION_COOKIE_SAMESITE = "Lax"

    # SECURE: only send the session cookie over HTTPS. Tied to DEBUG
    # so it stays False for local http://127.0.0.1 development (no
    # behavior change there) but automatically becomes True the
    # moment the app runs with DEBUG=False, i.e. in production -- a
    # deployment doesn't have to remember to set this separately.
    SESSION_COOKIE_SECURE = not DEBUG
