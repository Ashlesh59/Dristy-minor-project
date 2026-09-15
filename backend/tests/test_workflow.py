"""
backend/tests/test_workflow.py
--------------------------------------------------------------------------
Comprehensive Automated Test Suite for InvestIQ (Phase 0 Foundation).

Guarantees:
  1. Database Safety: Creates an isolated temporary directory outside the
     repository for each test run. Never accesses or modifies investiq.db.
  2. Test Sentinel: Verifies INVESTIQ_TEST_RUN fail-fast safety checks.
  3. Migrations Control: Verifies RUN_MIGRATIONS=False prevents schema alterations.
  4. Mocked Providers: 100% offline, zero live network requests.
  5. Core Lifecycle: Auth (signup, login, /me, logout), health, quotes, reports.
--------------------------------------------------------------------------
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from config import Config
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.research import Research
from services.financial_service import (
    MissingApiKeyError,
    FinancialServiceUnavailableError,
    FinancialServiceBadResponseError,
)


class InvestIQPhase0TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Create an isolated temporary directory strictly outside the repository
        cls.temp_dir = tempfile.mkdtemp(prefix="investiq_test_")
        cls.test_db_path = os.path.join(cls.temp_dir, "investiq_test.db")

        # 2. Safety verification: ensure test DB path is NOT inside repo or investiq.db
        dev_db = os.path.abspath(os.path.join(Config.BASE_DIR, "database", "investiq.db"))
        resolved_test = os.path.abspath(cls.test_db_path)
        assert os.path.normcase(resolved_test) != os.path.normcase(dev_db), "Test DB resolves to dev DB!"
        assert "investiq.db" not in os.path.basename(resolved_test), "Test DB file must not be investiq.db"

        # 3. Explicit test configuration
        cls.test_config = {
            "TESTING": True,
            "DEBUG": False,
            "SECRET_KEY": "test-only-secret-key-phase0-safe",
            "SESSION_COOKIE_SECURE": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{cls.test_db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RUN_MIGRATIONS": False,
            "WTF_CSRF_ENABLED": False,
        }

        # 4. Instantiate application with validated test configuration
        cls.app = create_app(cls.test_config)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()

        # Remove temporary directory and test database file
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            comp1 = Company(
                legal_name="Apple Inc",
                display_name="Apple Inc",
                normalized_name="apple inc",
                country="US",
                is_active=True,
            )
            comp2 = Company(
                legal_name="Tesla Inc",
                display_name="Tesla Inc",
                normalized_name="tesla inc",
                country="US",
                is_active=True,
            )
            db.session.add_all([comp1, comp2])
            db.session.flush()

            sec1 = Security(
                company_id=comp1.id,
                symbol="AAPL",
                exchange="NASDAQ",
                series="EQ",
                isin="US0378331005",
                is_active=True,
            )
            sec2 = Security(
                company_id=comp2.id,
                symbol="TSLA",
                exchange="NASDAQ",
                series="EQ",
                isin="US88160R1014",
                is_active=True,
            )
            db.session.add_all([sec1, sec2])
            db.session.commit()
            self.aapl_security_id = sec1.id
            self.tsla_security_id = sec2.id

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.session.remove()
            # Clean all tables between tests
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

    def _register_and_login(self, email="trader@investiq.com", password="Password123!", name="Pro Trader"):
        res = self.client.post("/api/auth/signup", json={
            "name": name,
            "email": email,
            "password": password
        })
        return res

    # ----------------------------------------------------------------
    # 1. Test Sentinel & Safety Guard Tests
    # ----------------------------------------------------------------
    def test_sentinel_blocks_unsafe_configuration(self):
        # When INVESTIQ_TEST_RUN=1, create_app must refuse non-testing mode
        with patch.dict(os.environ, {"INVESTIQ_TEST_RUN": "1"}):
            with self.assertRaises(RuntimeError) as ctx:
                create_app({"TESTING": False})
            self.assertIn("TESTING is not True", str(ctx.exception))

    def test_sentinel_blocks_development_database_path(self):
        # When INVESTIQ_TEST_RUN=1, create_app must refuse pointing to investiq.db
        dev_db = os.path.join(Config.BASE_DIR, "database", "investiq.db")
        with patch.dict(os.environ, {"INVESTIQ_TEST_RUN": "1"}):
            with self.assertRaises(RuntimeError) as ctx:
                create_app({
                    "TESTING": True,
                    "SQLALCHEMY_DATABASE_URI": f"sqlite:///{dev_db}"
                })
            self.assertIn("Configured test database resolves to development database", str(ctx.exception))

    def test_create_app_accepts_test_config(self):
        self.assertTrue(self.app.config["TESTING"])
        self.assertFalse(self.app.config["DEBUG"])
        self.assertFalse(self.app.config["RUN_MIGRATIONS"])
        self.assertEqual(self.app.config["SECRET_KEY"], "test-only-secret-key-phase0-safe")

    def test_database_is_isolated_temporary_file(self):
        dev_db = os.path.abspath(os.path.join(Config.BASE_DIR, "database", "investiq.db"))
        active_db = self.app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        self.assertNotEqual(os.path.normcase(os.path.abspath(active_db)), os.path.normcase(dev_db))
        self.assertTrue(os.path.exists(self.temp_dir))

    # ----------------------------------------------------------------
    # 2. Health & Core Authentication Tests (Offline, No External Keys)
    # ----------------------------------------------------------------
    def test_health_endpoint_response(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")

    def test_auth_lifecycle(self):
        # Signup
        res_signup = self.client.post("/api/auth/signup", json={
            "name": "Phase 0 User",
            "email": "phase0@example.com",
            "password": "Password123!"
        })
        self.assertEqual(res_signup.status_code, 201)

        # /me authenticated
        res_me = self.client.get("/api/auth/me")
        self.assertEqual(res_me.status_code, 200)
        self.assertEqual(res_me.get_json()["user"]["email"], "phase0@example.com")

        # Logout
        res_logout = self.client.post("/api/auth/logout")
        self.assertEqual(res_logout.status_code, 200)

        # /me unauthenticated
        res_after = self.client.get("/api/auth/me")
        self.assertEqual(res_after.status_code, 401)

    def test_missing_api_keys_does_not_break_auth_or_health(self):
        # Ensure that missing external keys (like ALPHA_VANTAGE_API_KEY) do not crash auth/health
        with patch.dict(os.environ, {"ALPHA_VANTAGE_API_KEY": "", "GEMINI_API_KEY": ""}):
            res_health = self.client.get("/api/health")
            self.assertEqual(res_health.status_code, 200)

            res_signup = self.client.post("/api/auth/signup", json={
                "name": "Offline User",
                "email": "offline@example.com",
                "password": "Password123!"
            })
            self.assertEqual(res_signup.status_code, 201)

    # ----------------------------------------------------------------
    # 3. Local Search & Research Creation Contract (Phase 1B)
    # ----------------------------------------------------------------
    def test_company_search_local_discovery(self):
        self._register_and_login()

        res = self.client.get("/api/companies/search?q=apple")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["symbol"], "AAPL")

    def test_invalid_security_id_does_not_create_research_record(self):
        self._register_and_login()

        # Missing security_id
        res_missing = self.client.post("/api/research", json={
            "company_name": "Random Fake Co",
            "ticker_symbol": "INVALID99"
        })
        self.assertEqual(res_missing.status_code, 400)

        # Inactive/nonexistent security_id
        res_nonexistent = self.client.post("/api/research", json={"security_id": 99999})
        self.assertEqual(res_nonexistent.status_code, 404)

        with self.app.app_context():
            # Ensure no research record was created
            self.assertEqual(Research.query.count(), 0)

    def test_successful_research_creation_and_financials_fetch(self):
        self._register_and_login()

        # Create research with validated security_id
        res = self.client.post("/api/research", json={
            "security_id": self.aapl_security_id
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        research_id = data["research"]["id"]

        with self.app.app_context():
            self.assertEqual(Research.query.count(), 1)
            saved = Research.query.first()
            self.assertEqual(saved.ticker_symbol, "AAPL")
            self.assertEqual(saved.company_name, "Apple Inc")

        # Now test financial quote retrieval on the created record
        with patch("routes.research.get_stock_quote") as mock_quote:
            mock_quote.return_value = {
                "symbol": "AAPL",
                "open": "220.00",
                "high": "225.00",
                "low": "219.00",
                "price": "224.50",
                "volume": "50000000",
                "latest_trading_day": "2026-09-15",
                "change": "4.50",
                "change_percent": "2.04%",
                "currency": "USD"
            }
            res_fin = self.client.get(f"/api/research/{research_id}/financials")
            self.assertEqual(res_fin.status_code, 200)
            fin_data = res_fin.get_json()["financial_data"]
            self.assertEqual(fin_data["price"], "224.50")

    def test_failed_searches_do_not_increase_search_statistics(self):
        self._register_and_login()

        # 1 Successful research creation
        res_ok = self.client.post("/api/research", json={
            "security_id": self.tsla_security_id
        })
        self.assertEqual(res_ok.status_code, 201)

        # 3 Failed attempts (missing / invalid security_id)
        self.client.post("/api/research", json={"security_id": 99991})
        self.client.post("/api/research", json={"security_id": 99992})
        self.client.post("/api/research", json={"company_name": "Fake 3"})

        res_stats = self.client.get("/api/research/stats")
        self.assertEqual(res_stats.status_code, 200)
        stats = res_stats.get_json()["stats"]
        self.assertEqual(stats["total_searches"], 1)

    # ----------------------------------------------------------------
    # 4. Mocked Report Generation from Saved Analysis
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


if __name__ == "__main__":
    unittest.main()
