"""
tests/test_market_data_service.py
--------------------------------------------------------------------------
Unit tests for MarketDataService: calculation accuracy, Decimal precision,
division-by-zero protection, date range handling, and ordering.
--------------------------------------------------------------------------
"""

import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
import tempfile

from app import create_app
from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from services.market_data_service import (
    MarketDataService,
    MarketDataServiceError,
    SecurityNotFoundError,
    InvalidRangeError,
)


class TestMarketDataService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(prefix="test_md_svc_", suffix=".db")
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.db_path}",
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        })
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Company and Security
        self.company = Company(
            legal_name="Reliance Industries Limited",
            display_name="Reliance Industries",
            normalized_name="reliance industries",
            country="IN",
            is_active=True,
        )
        db.session.add(self.company)
        db.session.commit()

        self.security = Security(
            company_id=self.company.id,
            symbol="RELIANCE",
            exchange="NSE",
            series="EQ",
            currency="INR",
            is_active=True,
        )
        db.session.add(self.security)
        db.session.commit()

        self.service = MarketDataService(db.session)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    def test_missing_or_inactive_security(self):
        with self.assertRaises(SecurityNotFoundError):
            self.service.get_latest_market_data(999999)

        # Inactive security
        self.security.is_active = False
        db.session.commit()
        with self.assertRaises(SecurityNotFoundError):
            self.service.get_latest_market_data(self.security.id)

    def test_missing_market_data_returns_none(self):
        res = self.service.get_latest_market_data(self.security.id)
        self.assertTrue(res["success"])
        self.assertEqual(res["security"]["security_id"], self.security.id)
        self.assertIsNone(res["market_data"])
        self.assertIsNone(res["freshness"]["last_trading_date"])

    def test_latest_market_data_with_explicit_previous_close(self):
        # Insert single record with previous_close populated
        dp = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 9, 15),
            open_price=Decimal("1450.25"),
            high_price=Decimal("1472.50"),
            low_price=Decimal("1441.10"),
            close_price=Decimal("1468.30"),
            previous_close=Decimal("1445.20"),
            volume=1234567,
            turnover=Decimal("1800000000.00"),
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
            is_adjusted=False,
        )
        db.session.add(dp)
        db.session.commit()

        res = self.service.get_latest_market_data(self.security.id)
        self.assertTrue(res["success"])
        md = res["market_data"]
        self.assertEqual(md["close"], "1468.30")
        self.assertEqual(md["change"], "23.10")
        self.assertEqual(md["change_percent"], "1.5984")

    def test_previous_price_fallback_from_historical_record(self):
        # Day 1: 2026-09-14
        dp1 = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 9, 14),
            open_price=Decimal("1400.00"),
            high_price=Decimal("1420.00"),
            low_price=Decimal("1395.00"),
            close_price=Decimal("1415.00"),
            previous_close=None,
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
            is_adjusted=False,
        )
        # Day 2: 2026-09-15 (previous_close is None on row)
        dp2 = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 9, 15),
            open_price=Decimal("1420.00"),
            high_price=Decimal("1440.00"),
            low_price=Decimal("1410.00"),
            close_price=Decimal("1435.00"),
            previous_close=None,
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
            is_adjusted=False,
        )
        db.session.add_all([dp1, dp2])
        db.session.commit()

        res = self.service.get_latest_market_data(self.security.id)
        self.assertTrue(res["success"])
        md = res["market_data"]
        self.assertEqual(md["trading_date"], "2026-09-15")
        self.assertEqual(md["previous_close"], "1415.00")
        self.assertEqual(md["change"], "20.00")
        self.assertEqual(md["change_percent"], "1.4134")

    def test_division_by_zero_protection(self):
        # Previous close is zero
        dp_zero = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 9, 15),
            open_price=Decimal("10.00"),
            high_price=Decimal("15.00"),
            low_price=Decimal("10.00"),
            close_price=Decimal("12.00"),
            previous_close=Decimal("0.00"),
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
            is_adjusted=False,
        )
        db.session.add(dp_zero)
        db.session.commit()

        res = self.service.get_latest_market_data(self.security.id)
        self.assertTrue(res["success"])
        md = res["market_data"]
        self.assertEqual(md["change"], "12.00")
        self.assertIsNone(md["change_percent"])

    def test_price_history_chronological_ordering(self):
        # Insert out of order dates
        dates = [
            date(2026, 9, 15),
            date(2026, 9, 10),
            date(2026, 9, 12),
            date(2026, 9, 11),
            date(2026, 9, 14),
        ]
        for idx, d in enumerate(dates):
            db.session.add(DailyPrice(
                security_id=self.security.id,
                trading_date=d,
                open_price=Decimal("100.00") + idx,
                high_price=Decimal("110.00") + idx,
                low_price=Decimal("95.00") + idx,
                close_price=Decimal("105.00") + idx,
                volume=1000,
                source="NSE_UDIFF",
                source_file_sha256="TEST_SHA256",
            ))
        db.session.commit()

        res = self.service.get_price_history(self.security.id, range_key="1m")
        prices = res["prices"]
        self.assertEqual(len(prices), 5)
        # Verify oldest to newest
        extracted_dates = [p["date"] for p in prices]
        self.assertEqual(extracted_dates, sorted([d.isoformat() for d in dates]))

    def test_price_history_range_filters(self):
        base_date = date(2026, 9, 15)
        # Insert 100 daily records spanning ~100 days
        for i in range(100):
            d = base_date - timedelta(days=i)
            db.session.add(DailyPrice(
                security_id=self.security.id,
                trading_date=d,
                open_price=Decimal("100.00"),
                high_price=Decimal("105.00"),
                low_price=Decimal("98.00"),
                close_price=Decimal("102.00"),
                volume=5000,
                source="NSE_UDIFF",
                source_file_sha256="TEST_SHA256",
            ))
        db.session.commit()

        # 1 Month query
        res_1m = self.service.get_price_history(self.security.id, range_key="1m")
        self.assertLessEqual(len(res_1m["prices"]), 32)
        self.assertGreater(len(res_1m["prices"]), 0)
        self.assertEqual(res_1m["range"]["requested"], "1m")

        # Custom start and end date
        res_custom = self.service.get_price_history(
            self.security.id,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 10),
        )
        prices_custom = res_custom["prices"]
        self.assertEqual(len(prices_custom), 10)
        self.assertEqual(prices_custom[0]["date"], "2026-09-01")
        self.assertEqual(prices_custom[-1]["date"], "2026-09-10")

    def test_price_history_validation_rejections(self):
        # Predefined range + start date conflict
        with self.assertRaises(InvalidRangeError):
            self.service.get_price_history(self.security.id, range_key="1y", start_date=date(2026, 1, 1))

        # Invalid range key
        with self.assertRaises(InvalidRangeError):
            self.service.get_price_history(self.security.id, range_key="10y")

        # Start date after end date
        with self.assertRaises(InvalidRangeError):
            self.service.get_price_history(
                self.security.id,
                start_date=date(2026, 9, 15),
                end_date=date(2026, 9, 1),
            )

    def test_database_level_limit_and_truncation_flag(self):
        base_date = date(2026, 9, 15)
        for i in range(20):
            d = base_date - timedelta(days=i)
            db.session.add(DailyPrice(
                security_id=self.security.id,
                trading_date=d,
                open_price=Decimal("100.00"),
                high_price=Decimal("105.00"),
                low_price=Decimal("98.00"),
                close_price=Decimal("102.00"),
                volume=5000,
                source="NSE_UDIFF",
                source_file_sha256="TEST_SHA256",
            ))
        db.session.commit()

        res = self.service.get_price_history(self.security.id, range_key="max", limit=5)
        self.assertEqual(len(res["prices"]), 5)
        self.assertTrue(res["range"]["truncated"])


if __name__ == "__main__":
    unittest.main()
