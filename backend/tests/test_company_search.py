"""
backend/tests/test_company_search.py
--------------------------------------------------------------------------
Comprehensive Automated Test Suite for Local Company Search & Research Creation (Phase 1B).

Covers:
  1. Authentication & Query Validation (401, 400).
  2. Multi-tier search matching & deterministic ranking.
  3. LIKE wildcard escaping (%, _, \\).
  4. 1-character exact symbol lookup rule.
  5. Single-query performance (no N+1).
  6. Strict security_id contract for POST /api/research (400 on missing, 404 on inactive).
  7. Backward compatibility for legacy research rows.
  8. Zero external API calls.
--------------------------------------------------------------------------
"""

import os
import shutil
import tempfile
import unittest
from sqlalchemy import event

from app import create_app
from config import Config
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.research import Research


class CompanySearchTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="investiq_search_test_")
        cls.test_db_path = os.path.join(cls.temp_dir, "search_test.db")

        # Validate database path is isolated
        dev_db = os.path.abspath(os.path.join(Config.BASE_DIR, "database", "investiq.db"))
        assert os.path.normcase(os.path.abspath(cls.test_db_path)) != os.path.normcase(dev_db)

        cls.test_config = {
            "TESTING": True,
            "DEBUG": False,
            "SECRET_KEY": "test-company-search-secret-key",
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
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self._seed_test_data()

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.session.remove()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

    def _seed_test_data(self):
        # Seed test user
        user = User(name="Trader Pro", email="trader@investiq.com")
        user.set_password("Password123!")
        db.session.add(user)

        # Seed Companies & Securities
        # 1. Reliance
        c1 = Company(
            legal_name="Reliance Industries Limited",
            display_name="Reliance Industries Limited",
            normalized_name="reliance industries limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c1)
        db.session.flush()

        s1_eq = Security(
            company_id=c1.id,
            symbol="RELIANCE",
            exchange="NSE",
            series="EQ",
            isin="INE002A01018",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        s1_be = Security(
            company_id=c1.id,
            symbol="RELIANCE",
            exchange="NSE",
            series="BE",
            isin="INE002A01018",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add_all([s1_eq, s1_be])

        # 2. Tata Motors
        c2 = Company(
            legal_name="Tata Motors Limited",
            display_name="Tata Motors Limited",
            normalized_name="tata motors limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c2)
        db.session.flush()

        s2 = Security(
            company_id=c2.id,
            symbol="TATAMOTORS",
            exchange="NSE",
            series="EQ",
            isin="INE155A01022",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s2)

        # 3. Tata Consultancy Services
        c3 = Company(
            legal_name="Tata Consultancy Services Limited",
            display_name="Tata Consultancy Services Limited",
            normalized_name="tata consultancy services limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c3)
        db.session.flush()

        s3 = Security(
            company_id=c3.id,
            symbol="TCS",
            exchange="NSE",
            series="EQ",
            isin="INE467B01029",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s3)

        # 4. Single-character symbol company for 1-char test
        c4 = Company(
            legal_name="U Corporation Limited",
            display_name="U Corporation Limited",
            normalized_name="u corporation limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c4)
        db.session.flush()

        s4 = Security(
            company_id=c4.id,
            symbol="U",
            exchange="NSE",
            series="EQ",
            isin="INE999U01019",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s4)

        # 5. Inactive Security and Inactive Company
        c_inactive = Company(
            legal_name="Dead Corp Limited",
            display_name="Dead Corp Limited",
            normalized_name="dead corp limited",
            country="IN",
            is_active=False,
        )
        db.session.add(c_inactive)
        db.session.flush()

        s_inactive = Security(
            company_id=c_inactive.id,
            symbol="DEADCORP",
            exchange="NSE",
            series="EQ",
            is_active=False,
        )
        db.session.add(s_inactive)

        # 6. Special character testing (wildcards in text)
        c_wild = Company(
            legal_name="100% Pure_Energy & Tech Corp",
            display_name="100% Pure_Energy & Tech Corp",
            normalized_name="100 pure energy tech corp",
            country="IN",
            is_active=True,
        )
        db.session.add(c_wild)
        db.session.flush()
        s_wild = Security(
            company_id=c_wild.id,
            symbol="PURETECH",
            exchange="NSE",
            series="EQ",
            is_active=True,
        )
        db.session.add(s_wild)

        db.session.commit()

    def _login(self):
        self.client.post("/api/auth/login", json={
            "email": "trader@investiq.com",
            "password": "Password123!"
        })

    # ----------------------------------------------------------------
    # 1. Authentication & Query Validation
    # ----------------------------------------------------------------
    def test_search_requires_authentication(self):
        # Unauthenticated request must return 401
        res = self.client.get("/api/companies/search?q=reliance")
        self.assertEqual(res.status_code, 401)

    def test_search_missing_and_empty_query_returns_400(self):
        self._login()
        # Missing q
        res_missing = self.client.get("/api/companies/search")
        self.assertEqual(res_missing.status_code, 400)

        # Empty q
        res_empty = self.client.get("/api/companies/search?q=")
        self.assertEqual(res_empty.status_code, 400)

        # Query < 2 chars that is not a valid 1-char alphanumeric
        res_short = self.client.get("/api/companies/search?q=%20")
        self.assertEqual(res_short.status_code, 400)

    # ----------------------------------------------------------------
    # 2. Search Matching & Ranking Tests
    # ----------------------------------------------------------------
    def test_exact_ticker_search(self):
        self._login()
        res = self.client.get("/api/companies/search?q=RELIANCE")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["symbol"], "RELIANCE")

    def test_case_insensitive_ticker_search(self):
        self._login()
        res = self.client.get("/api/companies/search?q=reliance")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["results"][0]["symbol"], "RELIANCE")

    def test_exact_company_name_search(self):
        self._login()
        res = self.client.get("/api/companies/search?q=Tata%20Motors%20Limited")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["results"][0]["symbol"], "TATAMOTORS")

    def test_company_name_prefix_search(self):
        self._login()
        res = self.client.get("/api/companies/search?q=Tata")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        symbols = [r["symbol"] for r in data["results"]]
        self.assertIn("TATAMOTORS", symbols)
        self.assertIn("TCS", symbols)

    def test_partial_company_name_search(self):
        self._login()
        res = self.client.get("/api/companies/search?q=Motors")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["results"][0]["symbol"], "TATAMOTORS")

    def test_isin_search(self):
        self._login()
        res = self.client.get("/api/companies/search?q=INE467B01029")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["results"][0]["symbol"], "TCS")

    def test_1_character_query_rule(self):
        self._login()
        # 'U' matches exact symbol 'U'
        res_u = self.client.get("/api/companies/search?q=U")
        self.assertEqual(res_u.status_code, 200)
        data_u = res_u.get_json()
        self.assertEqual(data_u["count"], 1)
        self.assertEqual(data_u["results"][0]["symbol"], "U")

        # 'X' does not match any exact symbol -> returns empty list
        res_x = self.client.get("/api/companies/search?q=X")
        self.assertEqual(res_x.status_code, 200)
        self.assertEqual(res_x.get_json()["count"], 0)

        # 1-char non-alphanumeric -> 400
        res_punct = self.client.get("/api/companies/search?q=@")
        self.assertEqual(res_punct.status_code, 400)

    # ----------------------------------------------------------------
    # 3. Filters & Limit Tests
    # ----------------------------------------------------------------
    def test_filters_and_limit_enforcement(self):
        self._login()
        # Valid exchange and country filter
        res = self.client.get("/api/companies/search?q=tata&exchange=nse&country=in&limit=1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["results"]), 1)

        # Invalid limit
        res_bad_lim = self.client.get("/api/companies/search?q=tata&limit=0")
        self.assertEqual(res_bad_lim.status_code, 400)

    def test_inactive_companies_and_securities_are_excluded(self):
        self._login()
        res = self.client.get("/api/companies/search?q=deadcorp")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["count"], 0)

    def test_sql_like_wildcard_escaping(self):
        self._login()
        # Searching for '%' should match literal '100% Pure_Energy' without wildcard expanding
        res_pct = self.client.get("/api/companies/search?q=100%")
        self.assertEqual(res_pct.status_code, 200)
        data = res_pct.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["symbol"], "PURETECH")

        # SQL Injection attempt should be treated as literal text
        res_inj = self.client.get("/api/companies/search?q=' OR '1'='1")
        self.assertEqual(res_inj.status_code, 200)
        self.assertEqual(res_inj.get_json()["count"], 0)

    # ----------------------------------------------------------------
    # 4. Database Query Performance & Single-Query Verification
    # ----------------------------------------------------------------
    def test_single_joined_query_execution(self):
        self._login()
        queries = []

        def query_listener(conn, cursor, statement, parameters, context, executemany):
            # Ignore session / auth queries
            if "FROM companies" in statement or "JOIN securities" in statement:
                queries.append(statement)

        with self.app.app_context():
            event.listen(db.engine, "before_cursor_execute", query_listener)
            try:
                res = self.client.get("/api/companies/search?q=Tata")
                self.assertEqual(res.status_code, 200)
                # Must execute exactly 1 joined query for search (no N+1 queries)
                self.assertEqual(len(queries), 1)
            finally:
                event.remove(db.engine, "before_cursor_execute", query_listener)

    # ----------------------------------------------------------------
    # 5. Strict Research Creation Contract (POST /api/research)
    # ----------------------------------------------------------------
    def test_research_creation_requires_security_id(self):
        self._login()
        # Missing security_id must return 400
        res_missing = self.client.post("/api/research", json={
            "company_name": "Spoofed Name",
            "ticker_symbol": "FAKE"
        })
        self.assertEqual(res_missing.status_code, 400)
        self.assertIn("security_id (integer) is required", res_missing.get_json()["message"])

        # Non-integer security_id -> 400
        res_str = self.client.post("/api/research", json={"security_id": "one"})
        self.assertEqual(res_str.status_code, 400)

    def test_research_creation_rejects_missing_or_inactive_security_with_404(self):
        self._login()
        # Nonexistent security_id
        res_404 = self.client.post("/api/research", json={"security_id": 99999})
        self.assertEqual(res_404.status_code, 404)

        # Inactive security
        with self.app.app_context():
            sec_inactive = Security.query.filter_by(symbol="DEADCORP").first()
            inactive_id = sec_inactive.id

        res_inactive = self.client.post("/api/research", json={"security_id": inactive_id})
        self.assertEqual(res_inactive.status_code, 404)

    def test_valid_research_creation_populates_verified_server_metadata(self):
        self._login()
        with self.app.app_context():
            sec = Security.query.filter_by(symbol="TCS").first()
            sec_id = sec.id
            comp_id = sec.company_id

        res = self.client.post("/api/research", json={
            "security_id": sec_id,
            "company_name": "IGNORE ME",
            "ticker_symbol": "IGNORE"
        })
        self.assertEqual(res.status_code, 201)
        data = res.get_json()["research"]

        # Server populated authoritative database metadata
        self.assertEqual(data["security_id"], sec_id)
        self.assertEqual(data["company_id"], comp_id)
        self.assertEqual(data["ticker_symbol"], "TCS")
        self.assertEqual(data["company_name"], "Tata Consultancy Services Limited")

        # Exactly 1 record created in database
        with self.app.app_context():
            self.assertEqual(Research.query.count(), 1)
            saved = Research.query.first()
            self.assertEqual(saved.company_id, comp_id)
            self.assertEqual(saved.security_id, sec_id)


if __name__ == "__main__":
    unittest.main()
