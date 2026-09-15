"""
Unit and integration tests for AdjustmentService (mathematical correctness, ex-date boundaries, cumulative factors).
"""
import os
import unittest
from datetime import date
from decimal import Decimal

from app import create_app
from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.corporate_action import CorporateAction
from models.adjusted_daily_price import AdjustedDailyPrice
from models.adjustment_run import AdjustmentRun
from services.adjustment_service import AdjustmentService


class TestAdjustmentService(unittest.TestCase):
    def setUp(self):
        self.test_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_adj_service.db"))
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
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed Company & Security
        self.company = Company(legal_name="Test Company", display_name="Test Co", normalized_name="test company", country="IN")
        db.session.add(self.company)
        db.session.commit()

        self.security = Security(company_id=self.company.id, symbol="TESTSEC", exchange="NSE", series="EQ", currency="INR")
        db.session.add(self.security)
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

    def test_single_stock_split_adjustment(self):
        # Seed daily prices: 1 before ex-date, 1 on ex-date
        dp1 = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 8, 31),
            open_price=Decimal("1000.00"),
            high_price=Decimal("1020.00"),
            low_price=Decimal("980.00"),
            close_price=Decimal("1010.00"),
            volume=1000,
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
        )
        dp2 = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 9, 1),
            open_price=Decimal("202.00"),
            high_price=Decimal("205.00"),
            low_price=Decimal("199.00"),
            close_price=Decimal("204.00"),
            volume=5200,
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
        )
        db.session.add_all([dp1, dp2])
        db.session.commit()

        # Stock split 5:1 (ratio_from=10, ratio_to=2) on 2026-09-01
        ca = CorporateAction(
            security_id=self.security.id,
            action_type="stock_split",
            ex_date=date(2026, 9, 1),
            action_description="Split from Rs 10 to Rs 2",
            ratio_from=Decimal("10"),
            ratio_to=Decimal("2"),
            source="NSE_CA",
            source_event_key="split_1",
            source_file_sha256="TEST_SHA256",
            processing_status="verified",
        )
        db.session.add(ca)
        db.session.commit()

        res = AdjustmentService.adjust_security(self.security.id, version="split_bonus_v1")
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["actions_applied"], 1)
        self.assertEqual(res["prices_processed"], 2)

        # Verify pre-exdate adjustment: factor = 2/10 = 0.2
        adj1 = AdjustedDailyPrice.query.filter_by(daily_price_id=dp1.id).first()
        self.assertIsNotNone(adj1)
        self.assertEqual(adj1.adjusted_open, Decimal("200.0000"))
        self.assertEqual(adj1.adjusted_high, Decimal("204.0000"))
        self.assertEqual(adj1.adjusted_low, Decimal("196.0000"))
        self.assertEqual(adj1.adjusted_close, Decimal("202.0000"))
        self.assertEqual(adj1.adjusted_volume, 5000)  # volume * 5
        self.assertEqual(adj1.cumulative_price_factor, Decimal("0.2"))

        # Verify post-exdate adjustment: factor = 1.0 (no adjustment)
        adj2 = AdjustedDailyPrice.query.filter_by(daily_price_id=dp2.id).first()
        self.assertIsNotNone(adj2)
        self.assertEqual(adj2.adjusted_open, Decimal("202.0000"))
        self.assertEqual(adj2.adjusted_close, Decimal("204.0000"))
        self.assertEqual(adj2.adjusted_volume, 5200)
        self.assertEqual(adj2.cumulative_price_factor, Decimal("1.0"))

        # Raw prices remain 100% unchanged
        raw1 = DailyPrice.query.get(dp1.id)
        self.assertEqual(raw1.close_price, Decimal("1010.0000"))

    def test_bonus_adjustment(self):
        dp = DailyPrice(
            security_id=self.security.id,
            trading_date=date(2026, 8, 14),
            open_price=Decimal("4000.00"),
            high_price=Decimal("4050.00"),
            low_price=Decimal("3950.00"),
            close_price=Decimal("4000.00"),
            volume=500,
            source="NSE_UDIFF",
            source_file_sha256="TEST_SHA256",
        )
        db.session.add(dp)

        # Bonus 1:1 on 2026-08-15 (ratio_from=1, ratio_to=2) -> factor = 1/2 = 0.5
        ca = CorporateAction(
            security_id=self.security.id,
            action_type="bonus",
            ex_date=date(2026, 8, 15),
            action_description="Bonus 1:1",
            ratio_from=Decimal("1"),
            ratio_to=Decimal("2"),
            source="NSE_CA",
            source_event_key="bonus_1",
            source_file_sha256="TEST_SHA256",
            processing_status="verified",
        )
        db.session.add(ca)
        db.session.commit()

        AdjustmentService.adjust_security(self.security.id)
        adj = AdjustedDailyPrice.query.filter_by(daily_price_id=dp.id).first()
        self.assertEqual(adj.adjusted_close, Decimal("2000.0000"))
        self.assertEqual(adj.adjusted_volume, 1000)

    def test_multiple_cumulative_adjustments(self):
        # Dates: D1 (July 1), D2 (Aug 20), D3 (Sep 15)
        dp1 = DailyPrice(security_id=self.security.id, trading_date=date(2026, 7, 1), close_price=Decimal("2000.00"), source="NSE_UDIFF", source_file_sha256="T", open_price=Decimal("2000"), high_price=Decimal("2000"), low_price=Decimal("2000"))
        dp2 = DailyPrice(security_id=self.security.id, trading_date=date(2026, 8, 20), close_price=Decimal("1000.00"), source="NSE_UDIFF", source_file_sha256="T", open_price=Decimal("1000"), high_price=Decimal("1000"), low_price=Decimal("1000"))
        dp3 = DailyPrice(security_id=self.security.id, trading_date=date(2026, 9, 15), close_price=Decimal("200.00"), source="NSE_UDIFF", source_file_sha256="T", open_price=Decimal("200"), high_price=Decimal("200"), low_price=Decimal("200"))
        db.session.add_all([dp1, dp2, dp3])

        # Action 1: Bonus 1:1 on 2026-08-01 (factor 0.5)
        ca1 = CorporateAction(security_id=self.security.id, action_type="bonus", ex_date=date(2026, 8, 1), ratio_from=Decimal("1"), ratio_to=Decimal("2"), action_description="Bonus 1:1", source="NSE_CA", source_event_key="b1", source_file_sha256="T", processing_status="verified")
        # Action 2: Split 5:1 on 2026-09-01 (factor 0.2)
        ca2 = CorporateAction(security_id=self.security.id, action_type="stock_split", ex_date=date(2026, 9, 1), ratio_from=Decimal("10"), ratio_to=Decimal("2"), action_description="Split 10 to 2", source="NSE_CA", source_event_key="s1", source_file_sha256="T", processing_status="verified")
        db.session.add_all([ca1, ca2])
        db.session.commit()

        AdjustmentService.adjust_security(self.security.id)

        # D1: before both actions -> factor = 0.5 * 0.2 = 0.1 -> 2000 * 0.1 = 200.00
        adj1 = AdjustedDailyPrice.query.filter_by(daily_price_id=dp1.id).first()
        self.assertEqual(adj1.adjusted_close, Decimal("200.0000"))
        self.assertEqual(adj1.cumulative_price_factor, Decimal("0.1"))

        # D2: after Action 1, before Action 2 -> factor = 0.2 -> 1000 * 0.2 = 200.00
        adj2 = AdjustedDailyPrice.query.filter_by(daily_price_id=dp2.id).first()
        self.assertEqual(adj2.adjusted_close, Decimal("200.0000"))
        self.assertEqual(adj2.cumulative_price_factor, Decimal("0.2"))

        # D3: after both actions -> factor = 1.0 -> 200.00
        adj3 = AdjustedDailyPrice.query.filter_by(daily_price_id=dp3.id).first()
        self.assertEqual(adj3.adjusted_close, Decimal("200.0000"))
        self.assertEqual(adj3.cumulative_price_factor, Decimal("1.0"))


if __name__ == "__main__":
    unittest.main()
