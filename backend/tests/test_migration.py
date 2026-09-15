"""
backend/tests/test_migration.py
--------------------------------------------------------------------------
Schema Migration & SQLite Foreign-Key Enforcement Tests.
Verifies:
  1. Idempotent column and index additions to existing tables.
  2. Legacy row preservation without data corruption.
  3. Strict foreign-key constraint enforcement on SQLite connections.
--------------------------------------------------------------------------
"""

import os
import shutil
import sqlite3
import tempfile
import unittest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import create_app
from config import Config
from database.db import db
from database.migrations import run_migrations, _existing_columns
from models.user import User
from models.company import Company
from models.security import Security
from models.research import Research


class SchemaMigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="investiq_mig_test_")
        self.test_db_path = os.path.join(self.temp_dir, "mig_test.db")

        # Step 1: Initialize raw legacy database manually with old schema
        raw_conn = sqlite3.connect(self.test_db_path)
        raw_cursor = raw_conn.cursor()
        raw_cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(120) NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)
        raw_cursor.execute("""
            CREATE TABLE research (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_name VARCHAR(200) NOT NULL,
                ticker_symbol VARCHAR(20) NOT NULL,
                research_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)
        # Insert a legacy research record
        raw_cursor.execute("""
            INSERT INTO users (name, email, password_hash, created_at, updated_at)
            VALUES ('Legacy User', 'legacy@investiq.com', 'hash123', '2026-01-01', '2026-01-01')
        """)
        raw_cursor.execute("""
            INSERT INTO research (user_id, company_name, ticker_symbol, research_type, status, created_at, updated_at)
            VALUES (1, 'Legacy Old Co', 'OLD', 'general', 'completed', '2026-01-01', '2026-01-01')
        """)
        raw_conn.commit()
        raw_conn.close()

        # Step 2: Configure and start Flask app pointing to this legacy database
        self.app = create_app({
            "TESTING": True,
            "DEBUG": False,
            "SECRET_KEY": "mig-test-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.test_db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RUN_MIGRATIONS": False,  # We test manual migration invocation
        })

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_legacy_migration_lifecycle_and_foreign_keys(self):
        with self.app.app_context():
            # 1. Create any missing new tables (companies, securities)
            db.create_all()

            # 2. Run migration
            run_migrations(db)

            # 3. Confirm legacy record still exists intact
            legacy = Research.query.first()
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.company_name, "Legacy Old Co")
            self.assertEqual(legacy.ticker_symbol, "OLD")
            self.assertIsNone(legacy.company_id)
            self.assertIsNone(legacy.security_id)

            # 4. Confirm new columns exist in SQLite PRAGMA
            with db.engine.connect() as conn:
                cols = _existing_columns(conn, "research")
                self.assertIn("company_id", cols)
                self.assertIn("security_id", cols)
                self.assertIn("financial_data", cols)

                # 5. Confirm indexes exist
                indexes = {
                    row[1]
                    for row in conn.execute(text("PRAGMA index_list(research)")).fetchall()
                }
                self.assertIn("ix_research_company_id", indexes)
                self.assertIn("ix_research_security_id", indexes)

            # 6. Confirm valid foreign-key insertion works
            company = Company(
                legal_name="New Co",
                display_name="New Co",
                normalized_name="new co",
                country="IN",
            )
            db.session.add(company)
            db.session.flush()

            security = Security(
                company_id=company.id,
                symbol="NEWCO",
                exchange="NSE",
                series="EQ",
            )
            db.session.add(security)
            db.session.flush()

            new_res = Research(
                user_id=1,
                company_id=company.id,
                security_id=security.id,
                company_name="New Co",
                ticker_symbol="NEWCO",
            )
            db.session.add(new_res)
            db.session.commit()

            self.assertEqual(Research.query.count(), 2)

            # 7. Confirm invalid foreign-key insertion is strictly rejected
            invalid_res = Research(
                user_id=1,
                company_id=99999,  # Nonexistent company ID
                security_id=88888, # Nonexistent security ID
                company_name="Bad Co",
                ticker_symbol="BAD",
            )
            db.session.add(invalid_res)
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

            # 8. Confirm re-running migration is a safe no-op
            run_migrations(db)
            self.assertEqual(Research.query.count(), 2)


if __name__ == "__main__":
    unittest.main()
