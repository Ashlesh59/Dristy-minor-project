"""
Unit tests for CorporateAction, CorporateActionImportRun, AdjustedDailyPrice, and AdjustmentRun models.
"""
import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.exc import IntegrityError

from app import create_app
from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.corporate_action import CorporateAction
from models.corporate_action_import_run import CorporateActionImportRun
from models.adjusted_daily_price import AdjustedDailyPrice
from models.adjustment_run import AdjustmentRun


class TestCorporateActionModels(unittest.TestCase):
    def setUp(self):
        self.test_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_ca_models.db"))
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

        test_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.test_db_path}",
            "SECRET_KEY": "test-key",
            "WTF_CSRF_ENABLED": False,
        }
        self.app = create_app(test_config)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed company and security
        self.company = Company(
            legal_name="Reliance Industries Limited",
            display_name="Reliance Industries",
            normalized_name="reliance industries limited",
            country="IN",
        )
        db.session.add(self.company)
        db.session.commit()

        self.security = Security(
            company_id=self.company.id,
            symbol="RELIANCE",
            exchange="NSE",
            series="EQ",
            isin="INE002A01018",
            currency="INR",
        )
        db.session.add(self.security)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_corporate_action_creation(self):
        ca = CorporateAction(
            security_id=self.security.id,
            action_type="stock_split",
            announcement_date=date(2026, 8, 1),
            ex_date=date(2026, 9, 1),
            record_date=date(2026, 9, 2),
            action_description="Split from Rs 10 to Rs 2",
            ratio_from=Decimal("10.000000"),
            ratio_to=Decimal("2.000000"),
            source="NSE_CA",
            source_event_key="event_key_1",
            source_file_sha256="TEST_SHA256",
            processing_status="verified",
        )
        db.session.add(ca)
        db.session.commit()

        loaded = db.session.get(CorporateAction, ca.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.action_type, "stock_split")
        self.assertEqual(loaded.ratio_from, Decimal("10.000000"))
        self.assertEqual(loaded.ratio_to, Decimal("2.000000"))
        self.assertEqual(loaded.security.symbol, "RELIANCE")

    def test_corporate_action_unique_event_key(self):
        ca1 = CorporateAction(
            security_id=self.security.id,
            action_type="bonus",
            ex_date=date(2026, 9, 1),
            action_description="Bonus 1:1",
            source="NSE_CA",
            source_event_key="dup_key",
            source_file_sha256="TEST_SHA256",
        )
        db.session.add(ca1)
        db.session.commit()

        ca2 = CorporateAction(
            security_id=self.security.id,
            action_type="bonus",
            ex_date=date(2026, 9, 1),
            action_description="Bonus 1:1 duplicate",
            source="NSE_CA",
            source_event_key="dup_key",
            source_file_sha256="TEST_SHA256",
        )
        db.session.add(ca2)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_adjusted_daily_price_uniqueness(self):
        dp = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 8, 30),
            open_price=Decimal("1000.00"),
            high_price=Decimal("1010.00"),
            low_price=Decimal("990.00"),
            close_price=Decimal("1005.00"),
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
        )
        db.session.add(dp)
        db.session.commit()

        adj1 = AdjustedDailyPrice(
            daily_price_id=dp.id,
            security_id=self.security.id,
            trading_date=dp.trading_date,
            adjusted_open=Decimal("200.00"),
            adjusted_high=Decimal("202.00"),
            adjusted_low=Decimal("198.00"),
            adjusted_close=Decimal("201.00"),
            cumulative_price_factor=Decimal("0.2000000000"),
            cumulative_volume_factor=Decimal("5.0000000000"),
            adjustment_version="split_bonus_v1",
        )
        db.session.add(adj1)
        db.session.commit()

        # Duplicate version for same daily_price_id should fail unique constraint
        adj2 = AdjustedDailyPrice(
            daily_price_id=dp.id,
            security_id=self.security.id,
            trading_date=dp.trading_date,
            adjusted_open=Decimal("200.00"),
            adjusted_high=Decimal("202.00"),
            adjusted_low=Decimal("198.00"),
            adjusted_close=Decimal("201.00"),
            cumulative_price_factor=Decimal("0.2000000000"),
            cumulative_volume_factor=Decimal("5.0000000000"),
            adjustment_version="split_bonus_v1",
        )
        db.session.add(adj2)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()


if __name__ == "__main__":
    unittest.main()
