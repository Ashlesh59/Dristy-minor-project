"""
database/migrations.py
--------------------------------------------------------------------------
Lightweight, idempotent SQLite schema migration runner.
Applies ALTER TABLE ... ADD COLUMN statements and creates missing indexes
without dropping tables or rewriting historical rows.
--------------------------------------------------------------------------
"""

from sqlalchemy import text


# (table, column, SQL type) -- columns added to existing tables
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
    ("research", "company_id", "INTEGER REFERENCES companies(id)"),
    ("research", "security_id", "INTEGER REFERENCES securities(id)"),
]

# Indexes to ensure on migrated tables
NEW_INDEXES = [
    ("ix_research_company_id", "research", "company_id"),
    ("ix_research_security_id", "research", "security_id"),
    ("ix_daily_prices_security_trading_date", "daily_prices", "security_id, trading_date"),
    ("ix_daily_prices_trading_date", "daily_prices", "trading_date"),
    ("ix_daily_prices_source", "daily_prices", "source"),
    ("ix_corporate_actions_security_ex_date", "corporate_actions", "security_id, ex_date"),
    ("ix_corporate_actions_action_type", "corporate_actions", "action_type"),
    ("ix_corporate_actions_processing_status", "corporate_actions", "processing_status"),
    ("ix_adjusted_daily_prices_security_date_version", "adjusted_daily_prices", "security_id, trading_date, adjustment_version"),
]



def _existing_columns(connection, table_name):
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def run_migrations(db):
    """
    Call once at startup, after db.create_all(), inside an app context.
    Idempotent and safe to run on fresh or existing databases.
    """
    engine = db.engine
    with engine.begin() as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }

        # 1. Add missing columns
        for table, column, col_type in NEW_COLUMNS:
            if table not in table_names:
                continue
            if column in _existing_columns(connection, table):
                continue
            connection.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            )

        # 2. Create missing indexes
        for idx_name, table, column in NEW_INDEXES:
            if table not in table_names:
                continue
            connection.execute(
                text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
            )
