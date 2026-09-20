"""
backend/tests/test_financial_data_resolution.py
--------------------------------------------------------------------------
Test suite for resilient multi-tier financial data resolution, live quotes,
historical candles, and dynamic company discovery.
--------------------------------------------------------------------------
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from config import Config
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.research import Research
from models.daily_price import DailyPrice
from services.financial_service import get_stock_quote, get_stock_history, search_symbols
from services.market_data_service import MarketDataService
from services.company_search_service import CompanySearchService


class FinancialDataResolutionTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="investiq_fin_test_")
        cls.test_db_path = os.path.join(cls.temp_dir, "fin_test.db")

        cls.test_config = {
            "TESTING": True,
            "ENABLE_LIVE_FALLBACK": True,
            "DEBUG": True,
            "SECRET_KEY": "test-fin-resolution-secret-key",
            "SESSION_COOKIE_SECURE": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{cls.test_db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RUN_MIGRATIONS": False,
            "WTF_CSRF_ENABLED": False,
        }

        cls.app = create_app(cls.test_config)
        cls.client = cls.app.test_client()

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
            user = User(name="Test Investor", email="investor@investiq.com")
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.session.remove()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

    def _login(self):
        return self.client.post("/api/auth/login", json={
            "email": "investor@investiq.com",
            "password": "Password123!"
        })

    def test_live_quote_retrieval_and_fields(self):
        with patch("services.financial_service.requests.get") as mock_get:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {
                "chart": {
                    "result": [{
                        "meta": {
                            "regularMarketPrice": 225.50,
                            "chartPreviousClose": 220.00,
                            "regularMarketDayHigh": 228.00,
                            "regularMarketDayLow": 219.00,
                            "regularMarketVolume": 50000000,
                            "currency": "USD",
                            "regularMarketTime": 1758100000,
                        }
                    }]
                }
            }
            mock_get.return_value = mock_res

            quote = get_stock_quote("AAPL")
            self.assertEqual(quote["symbol"], "AAPL")
            self.assertEqual(quote["price"], "225.5")
            self.assertEqual(quote["previous_close"], "220.0")
            self.assertEqual(quote["change"], "5.5")
            self.assertEqual(quote["currency"], "USD")

    def test_live_market_data_fallback_when_no_daily_prices(self):
        with self.app.app_context():
            c = Company(legal_name="Apple Inc.", display_name="Apple Inc.", normalized_name="apple inc", country="US", is_active=True)
            db.session.add(c)
            db.session.flush()
            s = Security(company_id=c.id, symbol="AAPL", exchange="NASDAQ", series="EQ", currency="USD", is_active=True)
            db.session.add(s)
            db.session.commit()
            sec_id = s.id

        with patch("services.financial_service.requests.get") as mock_get:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {
                "chart": {
                    "result": [{
                        "meta": {
                            "regularMarketPrice": 225.50,
                            "chartPreviousClose": 220.00,
                            "regularMarketDayHigh": 228.00,
                            "regularMarketDayLow": 219.00,
                            "regularMarketVolume": 50000000,
                            "currency": "USD",
                            "regularMarketTime": 1758100000,
                        },
                        "timestamp": [1758000000, 1758100000],
                        "indicators": {
                            "quote": [{
                                "open": [220.0, 222.0],
                                "high": [224.0, 228.0],
                                "low": [218.0, 219.0],
                                "close": [222.0, 225.5],
                                "volume": [45000000, 50000000]
                            }]
                        }
                    }]
                }
            }
            mock_get.return_value = mock_res

            with self.app.app_context():
                latest = MarketDataService.get_latest_market_data(sec_id)
                self.assertTrue(latest["success"])
                self.assertIsNotNone(latest["market_data"])
                self.assertEqual(latest["market_data"]["close"], "225.5")
                self.assertEqual(latest["market_data"]["change"], "5.5")

                history = MarketDataService.get_price_history(sec_id, range_key="1m")
                self.assertTrue(history["success"])
                self.assertGreaterEqual(len(history["prices"]), 2)
                self.assertEqual(history["prices"][-1]["close"], 225.5)

    def test_global_company_search_and_auto_registration(self):
        with patch("services.financial_service.requests.get") as mock_get:
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {
                "quotes": [{
                    "symbol": "NVDA",
                    "shortname": "NVIDIA Corporation",
                    "exchDisp": "NASDAQ",
                    "quoteType": "EQUITY"
                }]
            }
            mock_get.return_value = mock_res

            with self.app.app_context():
                # Search for Nvidia which is not locally seeded
                results = CompanySearchService.search("Nvidia")
                self.assertGreaterEqual(len(results), 1)
                self.assertEqual(results[0]["symbol"], "NVDA")
                self.assertEqual(results[0]["company_name"], "NVIDIA Corporation")

                # Verify it was auto-registered in database
                sec = Security.query.filter_by(symbol="NVDA").first()
                self.assertIsNotNone(sec)
                self.assertEqual(sec.company.display_name, "NVIDIA Corporation")


if __name__ == "__main__":
    unittest.main()
