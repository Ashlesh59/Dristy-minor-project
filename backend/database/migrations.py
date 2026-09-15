"""
database/migrations.py
--------------------------------------------------------------------------
db.create_all() (called in app.py) only CREATES tables that don't exist
yet -- it never ALTERs an existing table to add a column a model gained
later. Since this project already has a live investiq.db with real
user/research rows in it, simply changing the models wouldn't actually
add the new columns to that file, and every insert/query touching them
would fail.

This module runs a handful of idempotent `ALTER TABLE ... ADD COLUMN`
statements for exactly the columns added after the initial schema, and
nothing else -- no dropped tables, no rewritten data, no
db.drop_all()/recreate. Each one first checks PRAGMA table_info(...)
so re-running this on a database that's already been migrated (e.g.
every time the app restarts) is a safe no-op.
--------------------------------------------------------------------------
"""

from sqlalchemy import text


# (table, column, SQL type) -- every column added to a model after the
# very first schema, in the order they should be applied.
NEW_COLUMNS = [
    ("users", "company", "VARCHAR(200)"),
    ("users", "job_role", "VARCHAR(120)"),
    ("users", "phone", "VARCHAR(30)"),
    ("users", "country", "VARCHAR(100)"),
    ("users", "timezone", "VARCHAR(100)"),
    ("research", "financial_data", "TEXT"),
    ("research", "news_data", "TEXT"),
    ("research", "analysis_data", "TEXT"),
    ("research", "report_data", "TEXT"),
    ("research", "ai_score", "INTEGER"),
    ("research", "recommendation", "VARCHAR(50)"),
]


def _existing_columns(connection, table_name):
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    return {row[1] for row in rows}


def run_migrations(db):
    """
    Call once at startup, after db.create_all(), with the app's own
    `db` (SQLAlchemy) instance and inside an app context. Safe to call
    every time the app starts, on a brand-new database or an existing
    one.
    """
    engine = db.engine
    with engine.begin() as connection:
        # If the table itself doesn't exist yet (e.g. a genuinely fresh
        # database), db.create_all() already created it with every
        # current column, so there's nothing to add here -- skip it
        # rather than erroring.
        table_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }

        for table, column, col_type in NEW_COLUMNS:
            if table not in table_names:
                continue
            if column in _existing_columns(connection, table):
                continue
            connection.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            )
