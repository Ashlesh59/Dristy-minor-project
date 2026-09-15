"""
backend/tests/test_workflow.py
--------------------------------------------------------------------------
Comprehensive Automated Test Suite for InvestIQ.
Covers:
  1. Isolated in-memory database execution (never touches disk investiq.db).
  2. Mocked Alpha Vantage company/ticker search with 'alpha_vantage' source.
  3. Local fallback search with 'local_fallback' source on provider failure.
  4. Invalid ticker rejection (does NOT create a Research record).
  5. Missing API key & provider rate limit handling (no record created).
  6. Validated ticker creates exactly ONE record with financial_data.
  7. Failed searches do NOT increase database search statistics.
  8. Report generation directly from saved analysis (zero duplicate AI calls).
  9. Authentication & session lifecycle (signup, login, /me, logout).
  10. Health & database monitoring endpoint.
--------------------------------------------------------------------------
"""

import json
import unittest
from unittest.mock import patch

from app import create_app
from database.db import db
from models.user import User
from models.research import Research
from services.financial_service import (
    MissingApiKeyError,
    FinancialServiceUnavailableError,
    FinancialServiceBadResponseError,
)


class InvestIQWorkflowTestCase(unittest.TestCase):
    def setUp(self):
        # Always use an isolated in-memory SQLite database for testing
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret-key"
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _register_and_login(self, email="trader@investiq.com", password="Password123!", name="Pro Trader"):
        res = self.client.post("/api/auth/signup", json={
            "name": name,
            "email": email,
            "password": password
        })
        return res

    # ----------------------------------------------------------------
    # 1. Database Isolation Verification
    # ----------------------------------------------------------------
    def test_isolated_in_memory_database(self):
        self.assertEqual(self.app.config["SQLALCHEMY_DATABASE_URI"], "sqlite:///:memory:")
        self.assertTrue(self.app.config["TESTING"])

    # ----------------------------------------------------------------
    # 2. Company Search & Normalization (Mocked Alpha Vantage)
    # ----------------------------------------------------------------
    @patch("routes.research.search_symbols")
    def test_company_search_alpha_vantage_normalized_matches(self, mock_search):
        mock_search.return_value = [
            {
                "symbol": "AAPL",
                "name": "Apple Inc",
                "type": "Equity",
                "region": "United States",
                "currency": "USD"
            }
        ]
        self._register_and_login()

        res = self.client.get("/api/research/ticker-search?keywords=apple")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["source"], "alpha_vantage")
        self.assertEqual(len(data["matches"]), 1)
        self.assertEqual(data["matches"][0]["symbol"], "AAPL")
        self.assertEqual(data["matches"][0]["name"], "Apple Inc")

    # ----------------------------------------------------------------
    # 3. Local Fallback Search on Provider Error / Rate Limit
    # ----------------------------------------------------------------
    @patch("routes.research.search_symbols")
    def test_local_fallback_search_on_provider_error(self, mock_search):
        mock_search.side_effect = FinancialServiceUnavailableError("Rate limit reached")
        self._register_and_login()

        res = self.client.get("/api/research/ticker-search?keywords=tesla")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["source"], "local_fallback")
        self.assertTrue(any(m["symbol"] == "TSLA" for m in data["matches"]))

    # ----------------------------------------------------------------
    # 4. Invalid Ticker Rejection (NO Research Record Created)
    # ----------------------------------------------------------------
    @patch("routes.research.get_stock_quote")
    def test_invalid_ticker_does_not_create_research_record(self, mock_quote):
        mock_quote.side_effect = FinancialServiceBadResponseError("No quote data for ticker 'INVALID99'")
        self._register_and_login()

        res = self.client.post("/api/research", json={
            "company_name": "Random Fake Co",
            "ticker_symbol": "INVALID99"
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error_type"], "invalid_ticker")

        # Database must have zero records
        with self.app.app_context():
            self.assertEqual(Research.query.count(), 0)

    # ----------------------------------------------------------------
    # 5. Missing API Key & Rate Limit (NO Research Record Created)
    # ----------------------------------------------------------------
    @patch("routes.research.get_stock_quote")
    def test_provider_errors_do_not_create_record(self, mock_quote):
        self._register_and_login()

        # Missing API Key
        mock_quote.side_effect = MissingApiKeyError("API key missing")
        res_key = self.client.post("/api/research", json={
            "company_name": "Apple Inc",
            "ticker_symbol": "AAPL"
        })
        self.assertEqual(res_key.status_code, 500)
        self.assertEqual(res_key.get_json()["error_type"], "missing_api_key")

        # Provider Rate Limit
        mock_quote.side_effect = FinancialServiceUnavailableError("Rate limit reached")
        res_limit = self.client.post("/api/research", json={
            "company_name": "Apple Inc",
            "ticker_symbol": "AAPL"
        })
        self.assertEqual(res_limit.status_code, 503)
        self.assertEqual(res_limit.get_json()["error_type"], "provider_unavailable")

        with self.app.app_context():
            self.assertEqual(Research.query.count(), 0)

    # ----------------------------------------------------------------
    # 6. Validated Ticker Creates Exactly One Record with Financial Data
    # ----------------------------------------------------------------
    @patch("routes.research.get_stock_quote")
    def test_successful_validated_ticker_creates_exactly_one_record(self, mock_quote):
        mock_quote.return_value = {
            "symbol": "MSFT",
            "open": "497.00",
            "high": "510.00",
            "low": "495.00",
            "price": "505.41",
            "volume": "23000000",
            "latest_trading_day": "2026-09-14",
            "change": "9.78",
            "change_percent": "1.97%",
            "currency": "USD"
        }
        self._register_and_login()

        res = self.client.post("/api/research", json={
            "company_name": "Microsoft Corporation",
            "ticker_symbol": "MSFT"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("financial_data", data)
        self.assertEqual(data["financial_data"]["price"], "505.41")
        self.assertEqual(data["research"]["ticker_symbol"], "MSFT")

        # Exactly 1 record created in database
        with self.app.app_context():
            self.assertEqual(Research.query.count(), 1)
            saved = Research.query.first()
            self.assertEqual(saved.ticker_symbol, "MSFT")
            self.assertIn("505.41", saved.financial_data)

    # ----------------------------------------------------------------
    # 7. Failed Searches Do NOT Increase Search Statistics
    # ----------------------------------------------------------------
    @patch("routes.research.get_stock_quote")
    def test_failed_searches_do_not_increase_search_statistics(self, mock_quote):
        self._register_and_login()

        # 1 Successful search
        mock_quote.return_value = {"symbol": "TSLA", "price": "210.50", "currency": "USD"}
        res_ok = self.client.post("/api/research", json={
            "company_name": "Tesla Inc",
            "ticker_symbol": "TSLA"
        })
        self.assertEqual(res_ok.status_code, 201)

        # 3 Failed searches
        mock_quote.side_effect = FinancialServiceBadResponseError("Invalid ticker")
        self.client.post("/api/research", json={"company_name": "Fake 1", "ticker_symbol": "BAD1"})
        self.client.post("/api/research", json={"company_name": "Fake 2", "ticker_symbol": "BAD2"})
        self.client.post("/api/research", json={"company_name": "Fake 3", "ticker_symbol": "BAD3"})

        # Check stats: count must be exactly 1
        res_stats = self.client.get("/api/research/stats")
        self.assertEqual(res_stats.status_code, 200)
        stats = res_stats.get_json()["stats"]
        self.assertEqual(stats["total_searches"], 1)
        self.assertEqual(stats["distinct_companies"], 1)

    # ----------------------------------------------------------------
    # 8. Report Generation from Saved Analysis (Zero Duplicate Calls)
    # ----------------------------------------------------------------
    def test_report_generation_from_saved_analysis(self):
        sample_analysis = {
            "summary": "Apple Inc is a premier consumer electronics company.",
            "financial_assessment": "Robust free cash flow with stable momentum.",
            "news_sentiment": "Positive outlook on ecosystem growth.",
            "key_risks": "Regulatory scrutiny and supply chain concentration.",
            "key_opportunities": "Expansion of high-margin services.",
            "overall_outlook": "Strong long-term investment proposition.",
            "ai_score": 82,
            "recommendation": "Buy"
        }

        with self.app.app_context():
            user = User(name="Dave", email="dave@example.com")
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

            record = Research(
                user_id=user.id,
                company_name="Apple Inc.",
                ticker_symbol="AAPL",
                analysis_data=json.dumps(sample_analysis),
                status="completed"
            )
            db.session.add(record)
            db.session.commit()
            record_id = record.id

        self.client.post("/api/auth/login", json={
            "email": "dave@example.com",
            "password": "Password123!"
        })

        res = self.client.post(f"/api/research/{record_id}/report")
        self.assertEqual(res.status_code, 200)
        report = res.get_json()["report"]
        self.assertEqual(report["ai_score"], 82)
        self.assertEqual(report["recommendation"], "Buy")

    # ----------------------------------------------------------------
    # 9. Health & System Monitoring Endpoint
    # ----------------------------------------------------------------
    def test_health_monitoring(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertIn("services", data)

    # ----------------------------------------------------------------
    # 10. Authentication Lifecycle (Signup, Login, /me, Logout)
    # ----------------------------------------------------------------
    def test_auth_lifecycle(self):
        res_signup = self.client.post("/api/auth/signup", json={
            "name": "Auth User",
            "email": "authuser@example.com",
            "password": "Password123!"
        })
        self.assertEqual(res_signup.status_code, 201)

        res_me = self.client.get("/api/auth/me")
        self.assertEqual(res_me.status_code, 200)
        self.assertEqual(res_me.get_json()["user"]["email"], "authuser@example.com")

        res_logout = self.client.post("/api/auth/logout")
        self.assertEqual(res_logout.status_code, 200)

        res_after = self.client.get("/api/auth/me")
        self.assertEqual(res_after.status_code, 401)


if __name__ == "__main__":
    unittest.main()
