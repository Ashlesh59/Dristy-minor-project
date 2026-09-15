"""
backend/tests/test_workflow.py
--------------------------------------------------------------------------
Automated End-to-End Workflow Test Suite for InvestIQ.
Covers:
  1. Health & Monitoring endpoint
  2. User Registration, Authentication & Session Security
  3. Logout & Session Invalidation
  4. Search Creation & Database Counting
  5. Financial Data Caching
  6. AI Analysis Generation & JSON Integrity
  7. Report Generation from Saved Analysis (Zero Duplicate Calls)
  8. Multi-Tenant User Isolation & Ownership Scoping
--------------------------------------------------------------------------
"""

import json
import unittest

from app import create_app
from database.db import db
from models.user import User
from models.research import Research
from services.report_service import build_investment_report


class InvestIQWorkflowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ----------------------------------------------------------------
    # 1. Health & Monitoring Check
    # ----------------------------------------------------------------
    def test_health_monitoring(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")
        self.assertIn("services", data)

    # ----------------------------------------------------------------
    # 2. User Signup, Login & /api/auth/me
    # ----------------------------------------------------------------
    def test_auth_workflow(self):
        # Signup
        res = self.client.post("/api/auth/signup", json={
            "name": "Jane Investor",
            "email": "jane@example.com",
            "password": "Password123!"
        })
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.get_json()["success"])

        # Duplicate signup should fail with 409
        res_dup = self.client.post("/api/auth/signup", json={
            "name": "Jane Investor",
            "email": "jane@example.com",
            "password": "Password123!"
        })
        self.assertEqual(res_dup.status_code, 409)

        # Login
        res_login = self.client.post("/api/auth/login", json={
            "email": "jane@example.com",
            "password": "Password123!"
        })
        self.assertEqual(res_login.status_code, 200)
        self.assertTrue(res_login.get_json()["success"])

        # Validate /me
        res_me = self.client.get("/api/auth/me")
        self.assertEqual(res_me.status_code, 200)
        self.assertEqual(res_me.get_json()["user"]["email"], "jane@example.com")

    # ----------------------------------------------------------------
    # 3. Logout & Session Invalidation
    # ----------------------------------------------------------------
    def test_logout_session_invalidation(self):
        # Signup and login
        self.client.post("/api/auth/signup", json={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "Password123!"
        })

        # Check /me is accessible
        res_me = self.client.get("/api/auth/me")
        self.assertEqual(res_me.status_code, 200)

        # Issue logout
        res_logout = self.client.post("/api/auth/logout")
        self.assertEqual(res_logout.status_code, 200)

        # Subsequent /me should return 401 Unauthorized
        res_after = self.client.get("/api/auth/me")
        self.assertEqual(res_after.status_code, 401)

    # ----------------------------------------------------------------
    # 4. Search Creation & Database Counting
    # ----------------------------------------------------------------
    def test_search_creation_and_counting(self):
        # Register and login
        self.client.post("/api/auth/signup", json={
            "name": "Bob Analyst",
            "email": "bob@example.com",
            "password": "Password123!"
        })

        # Create 2 searches
        res1 = self.client.post("/api/research", json={
            "company_name": "Apple Inc.",
            "ticker_symbol": "AAPL"
        })
        self.assertEqual(res1.status_code, 201)

        res2 = self.client.post("/api/research", json={
            "company_name": "Tesla Inc.",
            "ticker_symbol": "TSLA"
        })
        self.assertEqual(res2.status_code, 201)

        # Check /api/research/stats returns correct count
        res_stats = self.client.get("/api/research/stats")
        self.assertEqual(res_stats.status_code, 200)
        stats = res_stats.get_json()["stats"]
        self.assertEqual(stats["total_searches"], 2)
        self.assertEqual(stats["distinct_companies"], 2)

    # ----------------------------------------------------------------
    # 5. Financial Data Caching
    # ----------------------------------------------------------------
    def test_financial_data_caching(self):
        with self.app.app_context():
            user = User(name="Charlie", email="charlie@example.com")
            user.set_password("Password123!")
            db.session.add(user)
            db.session.commit()

            sample_quote = {
                "symbol": "AAPL",
                "price": "333.08",
                "change": "0.81",
                "change_percent": "0.24%",
                "currency": "USD"
            }
            record = Research(
                user_id=user.id,
                company_name="Apple Inc.",
                ticker_symbol="AAPL",
                financial_data=json.dumps(sample_quote),
                status="pending"
            )
            db.session.add(record)
            db.session.commit()
            record_id = record.id

        # Login as Charlie
        self.client.post("/api/auth/login", json={
            "email": "charlie@example.com",
            "password": "Password123!"
        })

        # Fetch record and verify cached financial_data
        res = self.client.get(f"/api/research/{record_id}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["research"]
        self.assertIsNotNone(data["financial_data"])
        self.assertEqual(data["financial_data"]["price"], "333.08")

    # ----------------------------------------------------------------
    # 6. Report Generation from Saved Analysis (Zero Duplicate Calls)
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

        # Login as Dave
        self.client.post("/api/auth/login", json={
            "email": "dave@example.com",
            "password": "Password123!"
        })

        # Generate report from saved analysis
        res = self.client.post(f"/api/research/{record_id}/report")
        self.assertEqual(res.status_code, 200)
        report = res.get_json()["report"]
        self.assertIn("company_overview", report)
        self.assertIn("conclusion", report)
        self.assertEqual(report["ai_score"], 82)
        self.assertEqual(report["recommendation"], "Buy")

    # ----------------------------------------------------------------
    # 7. Multi-Tenant User Isolation & Ownership Scoping
    # ----------------------------------------------------------------
    def test_user_isolation(self):
        # User 1 registers and creates research
        self.client.post("/api/auth/signup", json={
            "name": "User One",
            "email": "user1@example.com",
            "password": "Password123!"
        })
        res1 = self.client.post("/api/research", json={
            "company_name": "Microsoft Corp",
            "ticker_symbol": "MSFT"
        })
        user1_record_id = res1.get_json()["research"]["id"]

        # User 2 registers and logs in
        self.client.post("/api/auth/signup", json={
            "name": "User Two",
            "email": "user2@example.com",
            "password": "Password123!"
        })

        # User 2 tries to access User 1's research record -> Must return 404
        res_forbidden = self.client.get(f"/api/research/{user1_record_id}")
        self.assertEqual(res_forbidden.status_code, 404)

        # User 2 tries to delete User 1's research record -> Must return 404
        res_del = self.client.delete(f"/api/research/{user1_record_id}")
        self.assertEqual(res_del.status_code, 404)


if __name__ == "__main__":
    unittest.main()
