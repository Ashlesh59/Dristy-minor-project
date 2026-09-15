"""
backend/tests/test_daily_price.py
--------------------------------------------------------------------------
Unit and model integrity tests for DailyPrice (Phase 2A).
--------------------------------------------------------------------------
"""

import os
import shutil
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.exc import IntegrityError

from app import create_app
from config import Config
from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice


class DailyPriceModelTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="investiq_dp_test_")
        cls.test_db_path = os.path.join(cls.temp_dir, "dp_test.db")

        cls.app = create_app({
            "TESTING": True,
            "DEBUG": False,
            "SECRET_KEY": "test-dp-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{cls.test_db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RUN_MIGRATIONS": False,
        })

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        with self.app.app_context():
            db.create_all()
            # Seed test company & security
            company = Company(
                legal_name="Reliance Industries Limited",
                display_name="Reliance Industries Limited",
                normalized_name="reliance industries limited",
                country="IN",
            )
            db.session.add(company)
            db.session.flush()

            security = Security(
                company_id=company.id,
                symbol="RELIANCE",
                exchange="NSE",
                series="EQ",
                isin="INE002A01018",
                currency="INR",
                asset_type="Equity",
            )
            db.session.add(security)
            db.session.commit()
            self.security_id = security.id

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.session.remove()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

    def test_daily_price_creation_and_decimal_precision(self):
        with self.app.app_context():
            dp = DailyPrice(
                security_id=self.security_id,
                trading_date=date(2026, 9, 15),
                open_price=Decimal("2450.2500"),
                high_price=Decimal("2480.5000"),
                low_price=Decimal("2440.1250"),
                close_price=Decimal("2475.7500"),
                last_price=Decimal("2476.0000"),
                previous_close=Decimal("2445.0000"),
                vwap=Decimal("2460.3333"),
                volume=1500000,
                turnover=Decimal("3690500000.5000"),
                trade_count=45000,
                deliverable_quantity=750000,
                deliverable_percentage=Decimal("50.00"),
                source="NSE_UDIFF",
                source_file_sha256="A" * 64,
                source_row_number=1,
                is_adjusted=False,
            )
            db.session.add(dp)
            db.session.commit()

            saved = DailyPrice.query.first()
            self.assertIsNotNone(saved)
            self.assertEqual(saved.security_id, self.security_id)
            self.assertEqual(saved.trading_date, date(2026, 9, 15))
            self.assertEqual(saved.open_price, Decimal("2450.2500"))
            self.assertEqual(saved.high_price, Decimal("2480.5000"))
            self.assertEqual(saved.low_price, Decimal("2440.1250"))
            self.assertEqual(saved.close_price, Decimal("2475.7500"))
            self.assertEqual(saved.volume, 1500000)
            self.assertFalse(saved.is_adjusted)
            self.assertEqual(saved.security.symbol, "RELIANCE")

    def test_unique_constraint_security_date_source(self):
        with self.app.app_context():
            dp1 = DailyPrice(
                security_id=self.security_id,
                trading_date=date(2026, 9, 15),
                open_price=Decimal("2450.00"),
                high_price=Decimal("2480.00"),
                low_price=Decimal("2440.00"),
                close_price=Decimal("2475.00"),
                source="NSE_UDIFF",
                source_file_sha256="A" * 64,
            )
            db.session.add(dp1)
            db.session.commit()

            # Attempting to insert identical security_id + trading_date + source
            dp2 = DailyPrice(
                security_id=self.security_id,
                trading_date=date(2026, 9, 15),
                open_price=Decimal("2500.00"),
                high_price=Decimal("2550.00"),
                low_price=Decimal("2490.00"),
                close_price=Decimal("2520.00"),
                source="NSE_UDIFF",
                source_file_sha256="B" * 64,
            )
            db.session.add(dp2)
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_foreign_key_enforcement(self):
        with self.app.app_context():
            # Attempting to insert a daily price with non-existent security_id
            dp_invalid = DailyPrice(
                security_id=99999,
                trading_date=date(2026, 9, 15),
                open_price=Decimal("100.00"),
                high_price=Decimal("105.00"),
                low_price=Decimal("95.00"),
                close_price=Decimal("102.00"),
                source="NSE_UDIFF",
                source_file_sha256="C" * 64,
            )
            db.session.add(dp_invalid)
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_to_dict_serialization(self):
        with self.app.app_context():
            dp = DailyPrice(
                security_id=self.security_id,
                trading_date=date(2026, 9, 15),
                open_price=Decimal("2450.00"),
                high_price=Decimal("2480.00"),
                low_price=Decimal("2440.00"),
                close_price=Decimal("2475.00"),
                volume=1000,
                source="NSE_UDIFF",
                source_file_sha256="D" * 64,
            )
            db.session.add(dp)
            db.session.commit()

            d = dp.to_dict()
            self.assertEqual(d["security_id"], self.security_id)
            self.assertEqual(d["trading_date"], "2026-09-15")
            self.assertEqual(d["open_price"], "2450.0000")
            self.assertEqual(d["volume"], 1000)
            self.assertEqual(d["source"], "NSE_UDIFF")


if __name__ == "__main__":
    unittest.main()
