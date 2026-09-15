"""
tests/test_market_data_routes.py
--------------------------------------------------------------------------
Route and integration tests for /api/securities/<id>/market-data/latest
and /api/securities/<id>/market-data/history endpoints.
--------------------------------------------------------------------------
"""

import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
import tempfile

from app import create_app
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice


class TestMarketDataRoutes(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(prefix="test_md_routes_", suffix=".db")
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.db_path}",
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        })
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed authenticated user
        self.user = User(
            name="Tester One",
            email="tester@investiq.test",
        )
        self.user.set_password("SecurePassword123!")
        db.session.add(self.user)
        db.session.commit()

        # Seed Company & Security
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

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user.id

    def test_auth_required_latest_endpoint(self):
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/latest")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data["success"])

    def test_auth_required_history_endpoint(self):
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data["success"])

    def test_missing_or_inactive_security_returns_404(self):
        self._login()
        # Non-existent security
        res = self.client.get("/api/securities/999999/market-data/latest")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(res.get_json()["success"])

        # Inactive security
        self.security.is_active = False
        db.session.commit()
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/latest")
        self.assertEqual(res.status_code, 404)

    def test_latest_endpoint_with_no_price_data_returns_200_null(self):
        self._login()
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/latest")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsNone(data["market_data"])
        self.assertIn("No price data has been imported", data["freshness"]["message"])
        self.assertEqual(data["security"]["symbol"], "RELIANCE")

    def test_latest_endpoint_success_and_decimal_serialization(self):
        self._login()
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

        res = self.client.get(f"/api/securities/{self.security.id}/market-data/latest")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        md = data["market_data"]
        # Decimal values returned as exact strings
        self.assertEqual(md["trading_date"], "2026-09-15")
        self.assertEqual(md["open"], "1450.25")
        self.assertEqual(md["high"], "1472.50")
        self.assertEqual(md["low"], "1441.10")
        self.assertEqual(md["close"], "1468.30")
        self.assertEqual(md["previous_close"], "1445.20")
        self.assertEqual(md["change"], "23.10")
        self.assertIsInstance(md["volume"], int)
        self.assertEqual(md["volume"], 1234567)
        self.assertEqual(md["turnover"], "1800000000.00")
        self.assertEqual(md["source"], "NSE_UDIFF")
        self.assertFalse(md["is_adjusted"])

        fresh = data["freshness"]
        self.assertEqual(fresh["data_type"], "end_of_day")
        self.assertEqual(fresh["last_trading_date"], "2026-09-15")
        self.assertFalse(fresh["is_real_time"])

    def test_history_endpoint_predefined_range(self):
        self._login()
        base_date = date(2026, 9, 15)
        for i in range(15):
            d = base_date - timedelta(days=i)
            db.session.add(DailyPrice(
                security_id=self.security.id,
                trading_date=d,
                open_price=Decimal("1400.00") + i,
                high_price=Decimal("1420.00") + i,
                low_price=Decimal("1390.00") + i,
                close_price=Decimal("1410.00") + i,
                volume=100000 + i,
                source="NSE_UDIFF",
                source_file_sha256="TEST_SHA256",
            ))
        db.session.commit()

        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history?range=1m")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["range"]["requested"], "1m")
        self.assertEqual(len(data["prices"]), 15)
        # Check chronological order (oldest to newest)
        first_date = data["prices"][0]["date"]
        last_date = data["prices"][-1]["date"]
        self.assertLess(first_date, last_date)
        self.assertEqual(last_date, "2026-09-15")

        # Metadata
        self.assertEqual(data["metadata"]["data_type"], "end_of_day")
        self.assertEqual(data["metadata"]["source"], "NSE_UDIFF")
        self.assertFalse(data["metadata"]["is_adjusted"])

    def test_history_endpoint_custom_iso_range(self):
        self._login()
        for i in range(10):
            d = date(2026, 9, 1) + timedelta(days=i)
            db.session.add(DailyPrice(
                security_id=self.security.id,
                trading_date=d,
                open_price=Decimal("100.00"),
                high_price=Decimal("110.00"),
                low_price=Decimal("95.00"),
                close_price=Decimal("105.00"),
                volume=5000,
                source="NSE_UDIFF",
                source_file_sha256="TEST_SHA256",
            ))
        db.session.commit()

        res = self.client.get(
            f"/api/securities/{self.security.id}/market-data/history?start=2026-09-02&end=2026-09-06"
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["prices"]), 5)
        self.assertEqual(data["prices"][0]["date"], "2026-09-02")
        self.assertEqual(data["prices"][-1]["date"], "2026-09-06")

    def test_history_endpoint_validation_errors(self):
        self._login()

        # Ambiguous combination: range preset + start
        res = self.client.get(
            f"/api/securities/{self.security.id}/market-data/history?range=1y&start=2026-01-01"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Cannot specify", res.get_json()["message"])

        # Invalid range key
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history?range=1d")
        self.assertEqual(res.status_code, 400)

        # Invalid date format
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history?start=invalid-date")
        self.assertEqual(res.status_code, 400)

        # Start date after end date
        res = self.client.get(
            f"/api/securities/{self.security.id}/market-data/history?start=2026-09-15&end=2026-09-01"
        )
        self.assertEqual(res.status_code, 400)

        # Invalid limit
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history?limit=-5")
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
