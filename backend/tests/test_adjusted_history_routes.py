"""
Integration tests for adjusted history market data API routes.
"""
import os
import unittest
from datetime import date
from decimal import Decimal

from app import create_app
from database.db import db
from models.user import User
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.corporate_action import CorporateAction
from services.adjustment_service import AdjustmentService


class TestAdjustedHistoryRoutes(unittest.TestCase):
    def setUp(self):
        self.test_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_adj_routes.db"))
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

        test_config = {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.test_db_path}",
            "SECRET_KEY": "test-key",
            "WTF_CSRF_ENABLED": False,
        }
        self.app = create_app(test_config)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed User
        self.user = User(email="test@example.com", name="Test User")
        self.user.set_password("Password123!")
        db.session.add(self.user)

        # Seed Company & Security
        self.company = Company(legal_name="Reliance Industries Limited", display_name="Reliance", normalized_name="reliance industries limited", country="IN")
        db.session.add(self.company)
        db.session.commit()

        self.security = Security(company_id=self.company.id, symbol="RELIANCE", exchange="NSE", series="EQ", currency="INR")
        db.session.add(self.security)
        db.session.commit()

        # Seed Daily Prices
        dp1 = DailyPrice(security_id=self.security.id, trading_date=date(2026, 8, 30), open_price=Decimal("1000"), high_price=Decimal("1010"), low_price=Decimal("990"), close_price=Decimal("1000"), volume=100, source="NSE_UDIFF", source_file_sha256="T")
        dp2 = DailyPrice(security_id=self.security.id, trading_date=date(2026, 9, 2), open_price=Decimal("200"), high_price=Decimal("205"), low_price=Decimal("195"), close_price=Decimal("200"), volume=500, source="NSE_UDIFF", source_file_sha256="T")
        db.session.add_all([dp1, dp2])
        db.session.commit()

        # Seed Split on Sep 1
        ca = CorporateAction(security_id=self.security.id, action_type="stock_split", ex_date=date(2026, 9, 1), ratio_from=Decimal("10"), ratio_to=Decimal("2"), action_description="Split 10 to 2", source="NSE_CA", source_event_key="s1", source_file_sha256="T", processing_status="verified")
        db.session.add(ca)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(self.user.id)
            sess["user_id"] = self.user.id

    def test_raw_history_response(self):
        self._login()
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history?price_mode=raw")
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data["success"])
        self.assertFalse(json_data["metadata"]["is_adjusted"])
        self.assertEqual(json_data["metadata"]["returned_price_mode"], "raw")
        # First price should be raw 1000.00
        self.assertEqual(json_data["prices"][0]["close"], "1000.00")

    def test_split_adjusted_fallback_before_rebuild(self):
        self._login()
        # Adjusted prices haven't been calculated yet -> should return honest fallback with reason
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history?price_mode=split_adjusted")
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertFalse(json_data["metadata"]["is_adjusted"])
        self.assertEqual(json_data["metadata"]["returned_price_mode"], "raw")
        self.assertIn("unavailable_reason", json_data["metadata"])

    def test_split_adjusted_after_rebuild(self):
        # Calculate adjustments
        AdjustmentService.adjust_security(self.security.id)

        self._login()
        res = self.client.get(f"/api/securities/{self.security.id}/market-data/history?price_mode=split_adjusted")
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data["metadata"]["is_adjusted"])
        self.assertEqual(json_data["metadata"]["returned_price_mode"], "split_adjusted")
        self.assertEqual(json_data["metadata"]["applied_action_count"], 1)

        # Pre-split close (was 1000) should now be adjusted to 200.00
        self.assertEqual(json_data["prices"][0]["close"], "200.00")
        self.assertEqual(json_data["prices"][0]["volume"], 500)
        # Post-split close should be 200.00
        self.assertEqual(json_data["prices"][1]["close"], "200.00")


if __name__ == "__main__":
    unittest.main()
