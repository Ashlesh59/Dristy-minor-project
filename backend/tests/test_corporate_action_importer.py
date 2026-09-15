"""
Integration tests for CorporateActionImporter.
"""
import os
import unittest
from datetime import date
from decimal import Decimal

from app import create_app
from database.db import db
from models.company import Company
from models.security import Security
from models.corporate_action import CorporateAction
from models.corporate_action_import_run import CorporateActionImportRun
from services.importer.corporate_action_importer import CorporateActionImporter


class TestCorporateActionImporter(unittest.TestCase):
    def setUp(self):
        self.test_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_ca_importer.db"))
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

        # Seed securities
        c1 = Company(legal_name="Reliance Industries Limited", display_name="Reliance", normalized_name="reliance industries limited", country="IN")
        c2 = Company(legal_name="Tata Consultancy Services Limited", display_name="TCS", normalized_name="tata consultancy services limited", country="IN")
        c3 = Company(legal_name="Infosys Limited", display_name="Infosys", normalized_name="infosys limited", country="IN")
        c4 = Company(legal_name="HDFC Bank Limited", display_name="HDFC Bank", normalized_name="hdfc bank limited", country="IN")
        db.session.add_all([c1, c2, c3, c4])
        db.session.commit()

        s1 = Security(company_id=c1.id, symbol="RELIANCE", exchange="NSE", series="EQ", isin="INE002A01018")
        s2 = Security(company_id=c2.id, symbol="TCS", exchange="NSE", series="EQ", isin="INE467B01029")
        s3 = Security(company_id=c3.id, symbol="INFY", exchange="NSE", series="EQ", isin="INE009A01021")
        s4 = Security(company_id=c4.id, symbol="HDFCBANK", exchange="NSE", series="EQ", isin="INE040A01034")
        db.session.add_all([s1, s2, s3, s4])
        db.session.commit()

        self.fixture_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "fixtures", "synthetic_nse_corporate_actions.csv"
        ))

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_dry_run_writes_nothing(self):
        res = CorporateActionImporter.import_csv(self.fixture_path, dry_run=True)
        self.assertEqual(res["status"], "dry_run")
        self.assertEqual(CorporateAction.query.count(), 0)
        self.assertEqual(CorporateActionImportRun.query.count(), 0)

    def test_live_import_success(self):
        res = CorporateActionImporter.import_csv(self.fixture_path, dry_run=False)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["total_rows"], 6)
        self.assertEqual(res["unresolved_rows"], 1)  # UNKNOWNSEC
        self.assertEqual(res["manual_review_rows"], 2)  # Scheme of Arrangement & Invalid Split

        # Check stored actions
        actions = CorporateAction.query.all()
        self.assertEqual(len(actions), 5)

        # Check RELIANCE split
        rel_split = CorporateAction.query.filter_by(action_type="stock_split", processing_status="verified").first()
        self.assertIsNotNone(rel_split)
        self.assertEqual(rel_split.ratio_from, Decimal("10"))
        self.assertEqual(rel_split.ratio_to, Decimal("2"))

        # Check audit log
        audit = CorporateActionImportRun.query.first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.status, "completed")
        self.assertEqual(audit.inserted_rows, 5)

    def test_idempotent_reimport(self):
        CorporateActionImporter.import_csv(self.fixture_path, dry_run=False)
        self.assertEqual(CorporateAction.query.count(), 5)

        # Re-import identical file
        res2 = CorporateActionImporter.import_csv(self.fixture_path, dry_run=False)
        self.assertEqual(res2["inserted_rows"], 0)
        self.assertEqual(res2["updated_rows"], 0)
        self.assertEqual(res2["unchanged_rows"], 5)
        self.assertEqual(CorporateAction.query.count(), 5)


if __name__ == "__main__":
    unittest.main()
