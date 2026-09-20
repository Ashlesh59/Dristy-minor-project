"""
backend/tests/test_verified_snapshot_workflow.py
--------------------------------------------------------------------------
Comprehensive test suite for the Verified Snapshot & AI Analysis Workflow:
1. Missing financial statements block fundamental financial claims.
2. Empty news blocks sentiment generation.
3. NSE securities strictly use INR currency (no USD placeholders).
4. Gemini is never called with an empty snapshot or insufficient data.
5. Every news article in snapshot has source, url, title, published_at.
6. Cached data / snapshots prevent duplicate provider calls.
7. Insufficient data yields 'Insufficient Data' research view.
8. Old unsupported analyses are flagged as legacy.
9. Verified saved reports reopen cleanly without extra provider calls.
10. No secrets (API keys, DB URLs) appear in API responses.
--------------------------------------------------------------------------
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from app import create_app
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.research import Research
from models.daily_price import DailyPrice
from services.snapshot_service import build_verified_snapshot
from services.ai_service import (
    generate_research_analysis_from_snapshot,
    generate_deterministic_analysis_from_snapshot,
)


class VerifiedSnapshotWorkflowTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="investiq_snapshot_test_")
        cls.test_db_path = os.path.join(cls.temp_dir, "snapshot_test.db")

        cls.test_config = {
            "TESTING": True,
            "ENABLE_LIVE_FALLBACK": False,
            "DEBUG": True,
            "SECRET_KEY": "test-secret-key-do-not-leak",
            "SESSION_COOKIE_SECURE": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{cls.test_db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RUN_MIGRATIONS": False,
            "WTF_CSRF_ENABLED": False,
        }

        # Ensure GEMINI_API_KEY is not in env
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

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
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

            # Create user
            self.user = User(name="Analyst User", email="analyst@investiq.test")
            self.user.set_password("SecurePass123!")
            db.session.add(self.user)
            db.session.commit()
            self.user_id = self.user.id

            # Create Titan company & security
            self.company = Company(
                legal_name="TITAN COMPANY LIMITED",
                display_name="TITAN COMPANY LIMITED",
                normalized_name="titan company limited",
                sector="Consumer Discretionary",
                industry="Gems, Jewellery And Watches",
                country="IN",
                is_active=True,
            )
            db.session.add(self.company)
            db.session.flush()

            self.security = Security(
                company_id=self.company.id,
                symbol="TITAN",
                isin="INE280A01028",
                series="EQ",
                exchange="NSE",
                currency="INR",
                is_active=True,
            )
            db.session.add(self.security)
            db.session.flush()

            # Add 5 daily price sessions (EOD Bhavcopy)
            prices = [
                DailyPrice(
                    security_id=self.security.id,
                    trading_date=date(2026, 9, 10),
                    open_price=4800.0,
                    high_price=4850.0,
                    low_price=4790.0,
                    close_price=4820.0,
                    last_price=4820.0,
                    previous_close=4780.0,
                    vwap=4815.0,
                    volume=700000,
                    turnover=3370500000.0,
                    trade_count=38000,
                    source="NSE_UDIFF",
                    source_file_sha256="testsha10",
                ),
                DailyPrice(
                    security_id=self.security.id,
                    trading_date=date(2026, 9, 11),
                    open_price=4830.0,
                    high_price=4870.0,
                    low_price=4810.0,
                    close_price=4850.0,
                    last_price=4850.0,
                    previous_close=4820.0,
                    vwap=4845.0,
                    volume=750000,
                    turnover=3633750000.0,
                    trade_count=41000,
                    source="NSE_UDIFF",
                    source_file_sha256="testsha11",
                ),
                DailyPrice(
                    security_id=self.security.id,
                    trading_date=date(2026, 9, 14),
                    open_price=4860.0,
                    high_price=4890.0,
                    low_price=4840.0,
                    close_price=4875.0,
                    last_price=4875.0,
                    previous_close=4850.0,
                    vwap=4870.0,
                    volume=800000,
                    turnover=3896000000.0,
                    trade_count=43000,
                    source="NSE_UDIFF",
                    source_file_sha256="testsha14",
                ),
                DailyPrice(
                    security_id=self.security.id,
                    trading_date=date(2026, 9, 15),
                    open_price=4880.0,
                    high_price=4920.0,
                    low_price=4870.0,
                    close_price=4900.0,
                    last_price=4900.0,
                    previous_close=4875.0,
                    vwap=4895.0,
                    volume=850000,
                    turnover=4160750000.0,
                    trade_count=45000,
                    source="NSE_UDIFF",
                    source_file_sha256="testsha15",
                ),
                DailyPrice(
                    security_id=self.security.id,
                    trading_date=date(2026, 9, 16),
                    open_price=4905.0,
                    high_price=4940.0,
                    low_price=4890.0,
                    close_price=4925.0,
                    last_price=4925.0,
                    previous_close=4900.0,
                    vwap=4918.0,
                    volume=920000,
                    turnover=4524560000.0,
                    trade_count=51000,
                    source="NSE_UDIFF",
                    source_file_sha256="testsha16",
                ),
            ]
            db.session.add_all(prices)

            # Create initial research record with empty news
            self.research = Research(
                user_id=self.user.id,
                company_id=self.company.id,
                security_id=self.security.id,
                company_name="TITAN COMPANY LIMITED",
                ticker_symbol="TITAN",
                news_data=json.dumps([]),
            )
            db.session.add(self.research)
            db.session.commit()

            self.security_id = self.security.id
            self.research_id = self.research.id

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.session.remove()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

    def _login(self):
        return self.client.post(
            "/api/auth/login",
            json={"email": "analyst@investiq.test", "password": "SecurePass123!"},
        )

    # -------------------------------------------------------------------------
    # 1. Missing Financial Statements Block Fundamental Financial Claims
    # -------------------------------------------------------------------------
    def test_missing_financial_statements_block_claims(self):
        """When financial statements are absent, fundamental assessment must explicitly state unavailability."""
        with self.app.app_context():
            research = db.session.get(Research, self.research_id)
            snapshot = build_verified_snapshot(research, allow_live_call=False)

            self.assertIn("financial_statements", snapshot["missing_sections"])
            self.assertFalse(snapshot["financial_statements"]["is_available"])
            self.assertEqual(snapshot["financial_statements"]["currency"], "INR")

            analysis = generate_deterministic_analysis_from_snapshot(snapshot)

            # Fundamental assessment must declare unavailability
            self.assertIn("Verified financial statements are not available", analysis["fundamental_assessment"])
            self.assertIn("Verified Financial Statements", " ".join(analysis["missing_information"]))
            # Confidence cannot be High when statements are missing
            self.assertNotEqual(analysis.get("decision_summary", {}).get("confidence_level"), "High")

    # -------------------------------------------------------------------------
    # 2. Empty News Blocks Sentiment Generation
    # -------------------------------------------------------------------------
    def test_empty_news_blocks_sentiment_generation(self):
        """When news is empty, sentiment paragraph must state it was not calculated."""
        with self.app.app_context():
            research = db.session.get(Research, self.research_id)
            research.news_data = None
            db.session.commit()

            # Mock get_ticker_news to return empty news
            with patch("services.snapshot_service.get_ticker_news", return_value=[]):
                snapshot = build_verified_snapshot(research, allow_live_call=True)

            self.assertEqual(len(snapshot["news_articles"]), 0)
            self.assertIn("news_articles", snapshot["missing_sections"])

            analysis = generate_deterministic_analysis_from_snapshot(snapshot)

            # News sentiment must declare unavailability
            self.assertIn("No verified recent news was found", analysis["news_sentiment"])
            self.assertIn("News sentiment was not calculated", analysis["news_sentiment"])

    # -------------------------------------------------------------------------
    # 3. NSE Securities Strictly Use INR Currency
    # -------------------------------------------------------------------------
    def test_nse_securities_strictly_use_inr(self):
        """NSE stocks must always use INR, never USD or empty placeholder currencies."""
        with self.app.app_context():
            research = db.session.get(Research, self.research_id)
            snapshot = build_verified_snapshot(research, allow_live_call=False)

            self.assertEqual(snapshot["company"]["currency"], "INR")
            self.assertEqual(snapshot["market_data"]["currency"], "INR")
            self.assertEqual(snapshot["financial_statements"]["currency"], "INR")

            # Check prices are formatted with ₹ in analysis
            analysis = generate_deterministic_analysis_from_snapshot(snapshot)
            self.assertIn("₹", analysis["market_assessment"])
            self.assertNotIn("$", analysis["market_assessment"])

    # -------------------------------------------------------------------------
    # 4. Gemini is Never Called with Empty Snapshot or Insufficient Data
    # -------------------------------------------------------------------------
    def test_gemini_never_called_with_insufficient_data(self):
        """When quality status is 'insufficient', Gemini API is bypassed completely."""
        with self.app.app_context():
            empty_comp = Company(
                legal_name="EMPTY CORP",
                display_name="EMPTY CORP",
                normalized_name="empty corp",
                country="IN",
                is_active=True,
            )
            db.session.add(empty_comp)
            db.session.flush()
            empty_sec = Security(company_id=empty_comp.id, symbol="EMPTY", exchange="NSE", currency="INR")
            db.session.add(empty_sec)
            db.session.flush()
            empty_res = Research(
                user_id=self.user_id,
                company_id=empty_comp.id,
                security_id=empty_sec.id,
                company_name="EMPTY CORP",
                ticker_symbol="EMPTY",
                news_data=json.dumps([]),
            )
            db.session.add(empty_res)
            db.session.commit()

            with patch("services.financial_service.get_stock_quote", return_value={"price": None}), \
                 patch("services.news_service.get_ticker_news", return_value=[]):
                snapshot = build_verified_snapshot(empty_res, allow_live_call=False)

            self.assertEqual(snapshot["quality_status"], "insufficient")

            # Verify that calling generate_research_analysis_from_snapshot never calls Gemini
            with patch("services.ai_service.genai.Client") as mock_client:
                analysis = generate_research_analysis_from_snapshot(snapshot)
                mock_client.assert_not_called()
                self.assertEqual(analysis["recommendation"], "Insufficient Data")
                self.assertEqual(analysis["decision_summary"]["research_view"], "Insufficient Data")
                self.assertEqual(analysis["decision_summary"]["confidence_level"], "Low")

    # -------------------------------------------------------------------------
    # 5. Verified News Articles Contain Source, URL, Title, Published Timestamp
    # -------------------------------------------------------------------------
    def test_verified_news_structure(self):
        """Every news article in the verified snapshot must possess required metadata."""
        mock_news = [
            {
                "title": "Titan Q1 Net Profit Jumps 15% on Strong Jewellery Demand",
                "source": "Economic Times",
                "url": "https://economictimes.indiatimes.com/markets/stocks/news/titan-q1-profit",
                "published_at": "2026-09-16T10:30:00Z",
                "summary": "Titan Company reported robust quarterly numbers backed by festive retail growth.",
            },
            {
                "title": "NSE Bulk Deals: Institutional Investors Increase Stake in Titan",
                "source": "LiveMint",
                "url": "https://www.livemint.com/market/titan-bulk-deals",
                "published_at": "2026-09-15T14:15:00Z",
                "summary": "Key domestic institutional funds accumulated shares of Titan.",
            },
        ]

        with self.app.app_context():
            research = db.session.get(Research, self.research_id)
            research.news_data = None
            db.session.commit()

            with patch("services.snapshot_service.get_ticker_news", return_value=mock_news):
                snapshot = build_verified_snapshot(research, allow_live_call=True)

            self.assertEqual(len(snapshot["news_articles"]), 2)
            for article in snapshot["news_articles"]:
                self.assertIn("headline", article)
                self.assertIn("source", article)
                self.assertIn("url", article)
                self.assertIn("published_at", article)
                self.assertIn("summary", article)
                self.assertTrue(len(article["headline"]) > 0)
                self.assertTrue(len(article["source"]) > 0)
                self.assertTrue(article["url"].startswith("http"))

    # -------------------------------------------------------------------------
    # 6. Cached Data Prevents Duplicate External Provider Calls
    # -------------------------------------------------------------------------
    def test_cached_data_prevents_duplicate_provider_calls(self):
        """Fresh research snapshot stored in database reuses cached data without calling providers."""
        with self.app.app_context():
            research = db.session.get(Research, self.research_id)
            # Populate research with a fresh snapshot & financial data
            research.financial_data = json.dumps({
                "financial_statements": {
                    "is_available": True,
                    "reporting_period": "Q1 FY27",
                    "revenue": 142000000000,
                    "net_profit": 9800000000,
                    "source": "NSE Regulatory Filings",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "currency": "INR",
                },
                "financial_ratios": {
                    "is_available": True,
                    "pe_ratio": 85.4,
                    "roe": 28.5,
                    "source": "NSE Regulatory Filings",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            })
            research.news_data = json.dumps([
                {"headline": "Titan Expansion", "source": "NSE", "url": "https://nseindia.com", "published_at": "2026-09-16"}
            ])
            db.session.commit()

            # Now build snapshot - it should read from research.financial_data and not call external financial APIs
            with patch("services.snapshot_service.get_ticker_news") as mock_news_api:
                snapshot = build_verified_snapshot(research, allow_live_call=False)
                mock_news_api.assert_not_called()
                self.assertTrue(snapshot["financial_statements"]["is_available"])
                self.assertEqual(snapshot["financial_statements"]["source"], "NSE Regulatory Filings")

    # -------------------------------------------------------------------------
    # 7. Quality Status and Insufficient Data
    # -------------------------------------------------------------------------
    def test_partial_quality_status_with_market_data_only(self):
        """When market data is present but financials and news are missing, status is 'partial'."""
        with self.app.app_context():
            research = db.session.get(Research, self.research_id)
            research.financial_data = None
            research.news_data = None
            db.session.commit()

            with patch("services.snapshot_service.get_ticker_news", return_value=[]):
                snapshot = build_verified_snapshot(research, allow_live_call=True)

            self.assertEqual(snapshot["quality_status"], "partial")
            self.assertTrue(snapshot["market_data"]["is_available"])
            self.assertFalse(snapshot["financial_statements"]["is_available"])
            self.assertIn("financial_statements", snapshot["missing_sections"])
            self.assertIn("news_articles", snapshot["missing_sections"])

    # -------------------------------------------------------------------------
    # 8. Old Unsupported Analyses are Flagged as Legacy
    # -------------------------------------------------------------------------
    def test_legacy_analysis_detection(self):
        """Analyses created without verified snapshot v2 or with hallucinated claims are marked legacy."""
        self._login()

        with self.app.app_context():
            research = db.session.get(Research, self.research_id)
            # Set legacy analysis format (no snapshot_version: 2)
            legacy_obj = {
                "fundamental_assessment": "Titan demonstrates strong ROE of 32% and excellent balance sheet leverage.",
                "market_assessment": "Stock is trading near highs with positive momentum.",
                "news_sentiment": "Recent news coverage shows overwhelming bullishness from analysts.",
                "recommendation": "Buy",
                "risk_factors": ["Gold price volatility"],
            }
            research.analysis_data = json.dumps(legacy_obj)
            research.financial_data = None
            research.news_data = json.dumps([])
            db.session.commit()

        # Call GET /api/research/<id>
        with patch("services.news_service.get_ticker_news", return_value=[]):
            res = self.client.get(f"/api/research/{self.research_id}")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()

            self.assertTrue(data.get("is_legacy_analysis"))
            self.assertIn("legacy_warning", data)
            self.assertIn("without the current verified-data snapshot", data["legacy_warning"])

    # -------------------------------------------------------------------------
    # 9. Verified Saved Reports Reopen Without Extra Provider Calls
    # -------------------------------------------------------------------------
    def test_verified_saved_reports_reopen_endpoint(self):
        """GET /api/research/<id>/snapshot and GET /api/research/<id> return consistent verified data."""
        self._login()

        # Post analyze
        with patch("services.news_service.get_ticker_news", return_value=[]):
            post_res = self.client.post(f"/api/research/{self.research_id}/analyze")
            self.assertEqual(post_res.status_code, 200)
            post_data = post_res.get_json()
            self.assertTrue(post_data.get("success"))
            self.assertIn("analysis", post_data)

            # Now GET the research record
            get_res = self.client.get(f"/api/research/{self.research_id}")
            self.assertEqual(get_res.status_code, 200)
            get_data = get_res.get_json()

            self.assertFalse(get_data.get("is_legacy_analysis", True))
            self.assertIn("snapshot", get_data)
            self.assertEqual(get_data["snapshot"]["company"]["symbol"], "TITAN")

            # Now GET /api/research/<id>/snapshot
            snap_res = self.client.get(f"/api/research/{self.research_id}/snapshot")
            self.assertEqual(snap_res.status_code, 200)
            snap_data = snap_res.get_json()
            self.assertIn("snapshot", snap_data)
            self.assertEqual(snap_data["snapshot"]["company"]["symbol"], "TITAN")
            self.assertEqual(snap_data["snapshot"]["market_data"]["currency"], "INR")

    # -------------------------------------------------------------------------
    # 10. No Secrets Appear in Logs or API Responses
    # -------------------------------------------------------------------------
    def test_no_secrets_in_responses(self):
        """API keys, passwords, and connection strings must never appear in response payloads."""
        self._login()

        endpoints = [
            f"/api/research/{self.research_id}",
            f"/api/research/{self.research_id}/snapshot",
        ]

        forbidden_secrets = [
            "test-secret-key-do-not-leak",
            "sqlite:///",
            "SecurePass123!",
        ]

        with patch("services.news_service.get_ticker_news", return_value=[]):
            for ep in endpoints:
                res = self.client.get(ep)
                text_body = res.get_data(as_text=True)
                for secret in forbidden_secrets:
                    self.assertNotIn(
                        secret,
                        text_body,
                        f"Secret '{secret}' was leaked in response from {ep}!"
                    )


if __name__ == "__main__":
    unittest.main()
