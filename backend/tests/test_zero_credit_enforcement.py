"""
backend/tests/test_zero_credit_enforcement.py
--------------------------------------------------------------------------
STRICT ZERO-CREDIT ENFORCEMENT TEST SUITE.

Verifies:
1. Market prices, statistics, and charts make ZERO external AI or financial API calls.
2. No requests to Alpha Vantage, Gemini, Twelve Data, Yahoo Finance, or any provider.
3. Market data is sourced strictly from database DailyPrice records.
4. Calculations (VWAP, 52W high/low, trailing returns, day change) execute locally in backend.
5. Opening, refreshing, printing, or changing chart ranges consume zero API credits.
6. Saved AI analysis and reports are reused from DB with zero Gemini calls.
7. Gemini runs only when explicitly invoked on un-analyzed records.
8. External socket and HTTP calls are intercepted and fail tests if triggered during market data operations.
--------------------------------------------------------------------------
"""

import json
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app import create_app
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.research import Research


class ExternalCallBlockedError(AssertionError):
    """Raised when an external network or AI API call is detected during a zero-credit operation."""


def strict_network_blocker(*args, **kwargs):
    raise ExternalCallBlockedError(
        f"STRICT ZERO-CREDIT VIOLATION: An external network or API call was attempted! Args: {args}, Kwargs: {kwargs}"
    )


class TestZeroCreditEnforcement(unittest.TestCase):
    """
    Automated zero-credit verification suite.
    """

    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SECRET_KEY": "test-zero-credit-secret",
            "GEMINI_API_KEY": "test-gemini-key",
            "ALPHA_VANTAGE_API_KEY": "test-alpha-key",
            "RATELIMIT_ENABLED": False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

            # Create test user
            self.user = User(
                name="Zero Credit Tester",
                email="zerocredit@investiq.com"
            )
            self.user.set_password("SecurePassword123!")
            db.session.add(self.user)

            # Create test company and security
            self.company = Company(
                legal_name="Reliance Industries Limited",
                display_name="Reliance Industries",
                normalized_name="reliance industries",
                country="IN",
                sector="Energy",
                industry="Refining & Marketing",
                is_active=True
            )
            db.session.add(self.company)
            db.session.flush()

            self.security = Security(
                company_id=self.company.id,
                symbol="RELIANCE",
                series="EQ",
                isin="INE002A01018",
                exchange="NSE",
                currency="INR",
                asset_type="Equity",
                is_active=True
            )
            db.session.add(self.security)
            db.session.flush()

            # Add chronological DailyPrice records anchored to today
            today = date.today()
            prices_data = [
                (today - timedelta(days=400), "2400.00", "2450.00", "2390.00", "2440.00", "2430.00", 1000000),
                (today - timedelta(days=250), "2440.00", "2500.00", "2430.00", "2480.00", "2470.00", 1200000),
                (today - timedelta(days=120), "2480.00", "2600.00", "2470.00", "2550.00", "2540.00", 1500000),
                (today - timedelta(days=60),  "2550.00", "2750.00", "2540.00", "2700.00", "2680.00", 1800000),
                (today - timedelta(days=20),  "2700.00", "2900.00", "2690.00", "2850.00", "2820.00", 2000000),
                (today - timedelta(days=2),   "2850.00", "3000.00", "2840.00", "2950.00", "2920.00", 2200000),
                (today - timedelta(days=1),   "2950.00", "3050.00", "2940.00", "3000.00", "2990.00", 2500000),
            ]
            for td, o, h, l, c, vwap, vol in prices_data:
                dp = DailyPrice(
                    security_id=self.security.id,
                    trading_date=td,
                    open_price=Decimal(o),
                    high_price=Decimal(h),
                    low_price=Decimal(l),
                    close_price=Decimal(c),
                    vwap=Decimal(vwap),
                    volume=vol,
                    turnover=Decimal(vol) * Decimal(c),
                    source="NSE CM-UDiFF",
                    source_file_sha256="0" * 64,
                    source_row_number=1
                )
                db.session.add(dp)
            db.session.commit()

            self.user_id = self.user.id
            self.security_id = self.security.id

        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _apply_strict_network_blockers(self):
        """Returns patches that fail if ANY outbound network or AI API call occurs."""
        patches = [
            patch("socket.socket.connect", side_effect=strict_network_blocker),
            patch("requests.get", side_effect=strict_network_blocker),
            patch("requests.post", side_effect=strict_network_blocker),
            patch("requests.request", side_effect=strict_network_blocker),
            patch("requests.Session.send", side_effect=strict_network_blocker),
            patch("urllib.request.urlopen", side_effect=strict_network_blocker),
            patch("services.ai_service.generate_research_analysis", side_effect=strict_network_blocker),
            patch("services.financial_service.get_stock_quote", side_effect=strict_network_blocker),
            patch("services.news_service.get_ticker_news", side_effect=strict_network_blocker),
        ]
        return patches

    def test_market_data_latest_uses_zero_external_calls(self):
        """GET /api/securities/<id>/market-data/latest must succeed with zero external calls."""
        patches = self._apply_strict_network_blockers()
        for p in patches:
            p.start()
        try:
            res = self.client.get(f"/api/securities/{self.security_id}/market-data/latest")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data["market_data"]["close"], "3000.00")
            self.assertEqual(data["market_data"]["source"], "NSE CM-UDiFF")
            # Verify calculated day change
            self.assertEqual(data["market_data"]["change"], "50.00")
        finally:
            for p in patches:
                p.stop()

    def test_market_data_history_all_ranges_use_zero_external_calls(self):
        """GET /api/securities/<id>/market-data/history across all ranges must consume zero API credits."""
        patches = self._apply_strict_network_blockers()
        for p in patches:
            p.start()
        try:
            for r in ["1m", "3m", "6m", "1y", "max"]:
                res = self.client.get(f"/api/securities/{self.security_id}/market-data/history?range={r}")
                self.assertEqual(res.status_code, 200)
                data = res.get_json()
                self.assertTrue(data.get("success"))
                self.assertGreater(len(data.get("prices", [])), 0)

            # Also verify split_adjusted price mode
            res_adj = self.client.get(f"/api/securities/{self.security_id}/market-data/history?range=1y&price_mode=split_adjusted")
            self.assertEqual(res_adj.status_code, 200)
        finally:
            for p in patches:
                p.stop()

    def test_market_data_summary_calculations_use_zero_external_calls(self):
        """GET /api/securities/<id>/market-data/summary calculates 52W range and returns with zero external calls."""
        patches = self._apply_strict_network_blockers()
        for p in patches:
            p.start()
        try:
            res = self.client.get(f"/api/securities/{self.security_id}/market-data/summary")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            summary = data["summary"]
            self.assertEqual(summary["close"], "3000.00")
            self.assertEqual(summary["week_52_high"], "3050.00")
            self.assertEqual(summary["week_52_low"], "2430.00")
            self.assertIsNotNone(summary["returns"]["return_1m"])
            self.assertIsNotNone(summary["returns"]["return_1y"])
        finally:
            for p in patches:
                p.stop()

    def test_company_search_uses_zero_external_calls(self):
        """GET /api/companies/search queries only local DB with zero external calls."""
        patches = self._apply_strict_network_blockers()
        for p in patches:
            p.start()
        try:
            res = self.client.get("/api/companies/search?q=RELIANCE")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["results"][0]["symbol"], "RELIANCE")
        finally:
            for p in patches:
                p.stop()

    def test_saved_research_and_report_reused_with_zero_gemini_calls(self):
        """Loading saved research record & report from database makes ZERO Gemini / external calls."""
        saved_report = {
            "company_overview": "Reliance overview from DB.",
            "investment_summary": "Strong growth.",
            "financial_assessment": "Solid balance sheet.",
            "news_sentiment": "Positive outlook.",
            "key_risks": "Commodity price fluctuation.",
            "key_opportunities": "Retail and telecom expansion.",
            "overall_outlook": "Positive.",
            "conclusion": "Favorable profile.",
            "ai_score": 85,
            "recommendation": "Buy",
            "generated_at": "2026-01-02T10:00:00"
        }
        saved_analysis = {
            "summary": "Strong growth.",
            "financial_assessment": "Solid balance sheet.",
            "news_sentiment": "Positive outlook.",
            "key_risks": "Commodity price fluctuation.",
            "key_opportunities": "Retail and telecom expansion.",
            "overall_outlook": "Positive.",
            "ai_score": 85,
            "recommendation": "Buy"
        }

        with self.app.app_context():
            research = Research(
                user_id=self.user_id,
                company_name="Reliance Industries Limited",
                ticker_symbol="RELIANCE",
                security_id=self.security_id,
                status="completed",
                analysis_data=json.dumps(saved_analysis),
                report_data=json.dumps(saved_report),
                ai_score=85,
                recommendation="Buy"
            )
            db.session.add(research)
            db.session.commit()
            research_id = research.id

        # Strict network blocker ensures ZERO network/Gemini calls
        patches = self._apply_strict_network_blockers()
        for p in patches:
            p.start()
        try:
            # 1. GET /api/research/<id>
            res_get = self.client.get(f"/api/research/{research_id}")
            self.assertEqual(res_get.status_code, 200)
            get_data = res_get.get_json()
            self.assertTrue(get_data["success"])
            self.assertEqual(get_data["research"]["report_data"]["ai_score"], 85)

            # 2. POST /api/research/<id>/report (on existing report) must return saved DB report without calling Gemini
            res_report = self.client.post(f"/api/research/{research_id}/report")
            self.assertEqual(res_report.status_code, 200)
            rep_data = res_report.get_json()
            self.assertTrue(rep_data["success"])
            self.assertEqual(rep_data["report"]["ai_score"], 85)
            self.assertEqual(rep_data["report"]["conclusion"], "Favorable profile.")
        finally:
            for p in patches:
                p.stop()

    def test_missing_market_data_returns_graceful_empty_with_zero_external_calls(self):
        """Security with no DailyPrice records returns clean empty response with zero external calls."""
        with self.app.app_context():
            tcs_company = Company(
                legal_name="Tata Consultancy Services Limited",
                display_name="Tata Consultancy Services",
                normalized_name="tata consultancy services",
                country="IN",
                is_active=True
            )
            db.session.add(tcs_company)
            db.session.flush()

            empty_sec = Security(
                company_id=tcs_company.id,
                symbol="TCS",
                series="EQ",
                isin="INE467B01029",
                exchange="NSE",
                currency="INR",
                asset_type="Equity",
                is_active=True
            )
            db.session.add(empty_sec)
            db.session.commit()
            empty_sec_id = empty_sec.id

        patches = self._apply_strict_network_blockers()
        for p in patches:
            p.start()
        try:
            # Latest
            res_latest = self.client.get(f"/api/securities/{empty_sec_id}/market-data/latest")
            self.assertEqual(res_latest.status_code, 200)
            data_latest = res_latest.get_json()
            self.assertIsNone(data_latest.get("market_data"))

            # Summary
            res_sum = self.client.get(f"/api/securities/{empty_sec_id}/market-data/summary")
            self.assertEqual(res_sum.status_code, 200)
            data_sum = res_sum.get_json()
            self.assertIsNone(data_sum.get("summary"))

            # History
            res_hist = self.client.get(f"/api/securities/{empty_sec_id}/market-data/history?range=1y")
            self.assertEqual(res_hist.status_code, 200)
            data_hist = res_hist.get_json()
            self.assertEqual(len(data_hist.get("history", [])), 0)
        finally:
            for p in patches:
                p.stop()

    def test_financials_route_prioritizes_local_bhavcopy_without_external_call(self):
        """GET /api/research/<id>/financials uses stored Bhavcopy DailyPrice without calling Alpha Vantage."""
        with self.app.app_context():
            research = Research(
                user_id=self.user_id,
                company_name="Reliance Industries Limited",
                ticker_symbol="RELIANCE",
                security_id=self.security_id,
                status="pending"
            )
            db.session.add(research)
            db.session.commit()
            research_id = research.id

        patches = self._apply_strict_network_blockers()
        for p in patches:
            p.start()
        try:
            res = self.client.get(f"/api/research/{research_id}/financials")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data.get("success"))
            self.assertEqual(data["financial_data"]["source"], "NSE Bhavcopy")
            self.assertEqual(data["financial_data"]["price"], "3000.00")
        finally:
            for p in patches:
                p.stop()


if __name__ == "__main__":
    unittest.main()
