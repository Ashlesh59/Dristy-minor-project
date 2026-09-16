"""
backend/tests/test_market_summary.py
--------------------------------------------------------------------------
Unit tests for Market Data Summary, 52-week range, and period returns calculations.
--------------------------------------------------------------------------
"""

import unittest
from datetime import date, timedelta
from decimal import Decimal

from app import create_app
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.research import Research
from services.market_data_service import MarketDataService


class TestMarketSummary(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-market-summary-secret",
            "RATELIMIT_ENABLED": False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # Create test user
            self.user = User(name="Test User", email="trader@investiq.com")
            self.user.set_password("SecurePass123!")
            db.session.add(self.user)

            # Create company & security
            self.company = Company(
                legal_name="Reliance Industries Limited",
                display_name="Reliance Industries",
                normalized_name="reliance industries",
                country="IN",
                is_active=True,
            )
            db.session.add(self.company)
            db.session.flush()

            self.security = Security(
                company_id=self.company.id,
                symbol="RELIANCE",
                exchange="NSE",
                series="EQ",
                isin="INE002A01018",
                currency="INR",
                asset_type="Equity",
                is_active=True,
            )
            db.session.add(self.security)
            db.session.commit()

            self.user_id = self.user.id
            self.company_id = self.company.id
            self.security_id = self.security.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id

    def test_market_summary_calculations(self):
        """Verifies 52-week high/low and 1M/3M/6M/1Y returns calculations."""
        with self.app.app_context():
            # Populate 400 days of price history
            base_date = date(2026, 9, 15)

            prices = []
            # Day 0 (today / latest): close 3000, high 3050, low 2950, open 2980, prev_close 2950
            # Day 30 (1M ago): close 2500 -> return = (3000 - 2500)/2500 * 100 = 20.00%
            # Day 90 (3M ago): close 2000 -> return = (3000 - 2000)/2000 * 100 = 50.00%
            # Day 180 (6M ago): close 2400 -> return = (3000 - 2400)/2400 * 100 = 25.00%
            # Day 365 (1Y ago): close 1500 -> return = (3000 - 1500)/1500 * 100 = 100.00%
            # Day 390 (>1Y ago, outside 52-week window): high 4500 (must NOT be counted in 52-week high)

            for day_offset in range(400):
                d = base_date - timedelta(days=day_offset)
                if day_offset == 0:
                    c, h, l, op, pc = Decimal("3000.00"), Decimal("3050.00"), Decimal("2950.00"), Decimal("2980.00"), Decimal("2950.00")
                elif day_offset == 30:
                    c, h, l, op, pc = Decimal("2500.00"), Decimal("2550.00"), Decimal("2450.00"), Decimal("2480.00"), Decimal("2450.00")
                elif day_offset == 90:
                    c, h, l, op, pc = Decimal("2000.00"), Decimal("2050.00"), Decimal("1950.00"), Decimal("1980.00"), Decimal("1950.00")
                elif day_offset == 180:
                    c, h, l, op, pc = Decimal("2400.00"), Decimal("2450.00"), Decimal("2350.00"), Decimal("2380.00"), Decimal("2350.00")
                elif day_offset == 200:
                    # Lowest price inside 52-week window: low 1400.00
                    c, h, l, op, pc = Decimal("1450.00"), Decimal("1500.00"), Decimal("1400.00"), Decimal("1480.00"), Decimal("1490.00")
                elif day_offset == 250:
                    # Highest price inside 52-week window: high 3200.00
                    c, h, l, op, pc = Decimal("3150.00"), Decimal("3200.00"), Decimal("3100.00"), Decimal("3120.00"), Decimal("3100.00")
                elif day_offset == 365:
                    c, h, l, op, pc = Decimal("1500.00"), Decimal("1550.00"), Decimal("1450.00"), Decimal("1480.00"), Decimal("1450.00")
                elif day_offset == 390:
                    # Outside 52-week window
                    c, h, l, op, pc = Decimal("4000.00"), Decimal("4500.00"), Decimal("1100.00"), Decimal("3900.00"), Decimal("3800.00")
                else:
                    c, h, l, op, pc = Decimal("2200.00"), Decimal("2250.00"), Decimal("2150.00"), Decimal("2180.00"), Decimal("2150.00")

                dp = DailyPrice(
                    security_id=self.security_id,
                    trading_date=d,
                    open_price=op,
                    high_price=h,
                    low_price=l,
                    close_price=c,
                    previous_close=pc,
                    volume=1000000,
                    turnover=Decimal("3000000000.00"),
                    vwap=Decimal("3010.50"),
                    source="NSE_UDIFF",
                    source_file_sha256="0" * 64,
                )
                prices.append(dp)

            db.session.bulk_save_objects(prices)
            db.session.commit()

            summary = MarketDataService.get_market_summary(self.security_id)
            self.assertTrue(summary["success"])
            md = summary["market_data"]

            self.assertEqual(md["close"], "3000.00")
            self.assertEqual(md["open"], "2980.00")
            self.assertEqual(md["high"], "3050.00")
            self.assertEqual(md["low"], "2950.00")
            self.assertEqual(md["previous_close"], "2950.00")
            self.assertEqual(md["change"], "50.00")
            self.assertEqual(md["change_percent"], "1.6949")
            self.assertEqual(md["volume"], 1000000)
            self.assertEqual(md["vwap"], "3010.50")

            # 52-Week Range verification (excludes day 390 high 4500 and low 1100)
            self.assertEqual(md["week_52_high"], "3200.00")
            self.assertEqual(md["week_52_low"], "1400.00")

            # Returns verification
            returns = md["returns"]
            self.assertEqual(returns["return_1m"], "20.00")
            self.assertEqual(returns["return_3m"], "50.00")
            self.assertEqual(returns["return_6m"], "25.00")
            self.assertEqual(returns["return_1y"], "100.00")

    def test_market_summary_single_record(self):
        """Single day record should return day price for 52W high/low and None for returns."""
        with self.app.app_context():
            dp = DailyPrice(
                security_id=self.security_id,
                trading_date=date(2026, 9, 15),
                open_price=Decimal("1500.00"),
                high_price=Decimal("1550.00"),
                low_price=Decimal("1480.00"),
                close_price=Decimal("1520.00"),
                previous_close=Decimal("1500.00"),
                volume=50000,
                source="NSE_UDIFF",
                source_file_sha256="0" * 64,
            )
            db.session.add(dp)
            db.session.commit()

            summary = MarketDataService.get_market_summary(self.security_id)
            md = summary["market_data"]
            self.assertEqual(md["week_52_high"], "1550.00")
            self.assertEqual(md["week_52_low"], "1480.00")
            self.assertIsNone(md["returns"]["return_1m"])
            self.assertIsNone(md["returns"]["return_3m"])
            self.assertIsNone(md["returns"]["return_6m"])
            self.assertIsNone(md["returns"]["return_1y"])

    def test_market_summary_no_records(self):
        """When no price records exist, market_data is None with clear message."""
        with self.app.app_context():
            summary = MarketDataService.get_market_summary(self.security_id)
            self.assertTrue(summary["success"])
            self.assertIsNone(summary["market_data"])
            self.assertEqual(
                summary["freshness"]["message"],
                "No price data has been imported for this security yet."
            )

    def test_market_summary_endpoints(self):
        """Tests GET /api/securities/<id>/market-data/summary and latest endpoints."""
        self._login()
        with self.app.app_context():
            dp = DailyPrice(
                security_id=self.security_id,
                trading_date=date(2026, 9, 15),
                open_price=Decimal("2000.00"),
                high_price=Decimal("2050.00"),
                low_price=Decimal("1980.00"),
                close_price=Decimal("2020.00"),
                previous_close=Decimal("2000.00"),
                volume=10000,
                source="NSE_UDIFF",
                source_file_sha256="0" * 64,
            )
            db.session.add(dp)
            db.session.commit()

        # Test summary endpoint
        res = self.client.get(f"/api/securities/{self.security_id}/market-data/summary")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["summary"]["close"], "2020.00")
        self.assertEqual(data["summary"]["week_52_high"], "2050.00")

        # Test latest endpoint
        res_latest = self.client.get(f"/api/securities/{self.security_id}/market-data/latest")
        self.assertEqual(res_latest.status_code, 200)
        data_latest = res_latest.get_json()
        self.assertEqual(data_latest["market_data"]["week_52_high"], "2050.00")

    def test_get_research_returns_security_id(self):
        """Tests GET /api/research/<id> returns security_id directly and with legacy fallback."""
        self._login()
        with self.app.app_context():
            # Standard research with security_id
            r1 = Research(
                user_id=self.user_id,
                company_id=self.company_id,
                security_id=self.security_id,
                company_name="Reliance Industries",
                ticker_symbol="RELIANCE",
                status="completed",
            )
            # Legacy research without security_id
            r2 = Research(
                user_id=self.user_id,
                company_id=self.company_id,
                security_id=None,
                company_name="Reliance Industries",
                ticker_symbol="RELIANCE",
                status="completed",
            )
            db.session.add_all([r1, r2])
            db.session.commit()
            r1_id, r2_id = r1.id, r2.id

        res1 = self.client.get(f"/api/research/{r1_id}")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()["research"]["security_id"], self.security_id)

        res2 = self.client.get(f"/api/research/{r2_id}")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["research"]["security_id"], self.security_id)


if __name__ == "__main__":
    unittest.main()
