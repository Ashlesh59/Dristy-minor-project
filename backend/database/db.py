"""
database/db.py
--------------------------------------------------------------------------
Creates the single, shared SQLAlchemy instance for the whole app.
Enforces SQLite foreign-key constraints on all active connections.
--------------------------------------------------------------------------
"""

import sqlite3
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enables foreign-key constraints for SQLite connections."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()
