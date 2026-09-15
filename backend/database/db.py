"""
database/db.py
--------------------------------------------------------------------------
Creates the single, shared SQLAlchemy instance for the whole app.
--------------------------------------------------------------------------
"""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
