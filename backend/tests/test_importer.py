"""
backend/tests/test_importer.py
--------------------------------------------------------------------------
Comprehensive Automated Test Suite for NSE Company & Security Master Importer (Phase 1A).

Guarantees:
  1. Complete Database Isolation (temporary directory outside repository).
  2. Model relationships (Company 1-to-N Security).
  3. Strict unique constraints on (exchange, symbol, series).
  4. Space-preserving normalization and ISIN Luhn checksums.
  5. Transactional rollback and independent failed audit logging.
  6. Dry-run zero-write guarantee.
  7. Multi-tier snapshot deactivation safety.
--------------------------------------------------------------------------
"""

import os
import shutil
import tempfile
import unittest

from app import create_app
from config import Config
from database.db import db
from models.company import Company
from models.security import Security
from models.data_import_run import DataImportRun
from services.importer.isin_validator import validate_isin, calculate_isin_check_digit
from services.importer.normalizer import (
    normalize_company_name,
    parse_listing_date,
    parse_decimal,
    parse_integer,
    normalize_nse_row,
)
from services.importer.nse_importer import NSECompanyImporter


class NSEImporterTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="investiq_importer_test_")
        cls.test_db_path = os.path.join(cls.temp_dir, "investiq_importer_test.db")

        # Validate test DB is not investiq.db
        dev_db = os.path.abspath(os.path.join(Config.BASE_DIR, "database", "investiq.db"))
        resolved_test = os.path.abspath(cls.test_db_path)
        assert os.path.normcase(resolved_test) != os.path.normcase(dev_db)

        cls.test_config = {
            "TESTING": True,
            "DEBUG": False,
            "SECRET_KEY": "test-importer-secret-key-safe",
            "SESSION_COOKIE_SECURE": False,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{cls.test_db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RUN_MIGRATIONS": False,
            "WTF_CSRF_ENABLED": False,
        }

        cls.app = create_app(cls.test_config)
        cls.fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "synthetic_nse_equities.csv"
        )

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

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.session.remove()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

    # ----------------------------------------------------------------
    # 1. Models & Normalization Unit Tests
    # ----------------------------------------------------------------
    def test_company_and_security_model_relationship(self):
        with self.app.app_context():
            company = Company(
                legal_name="Reliance Industries Limited",
                display_name="Reliance Industries Limited",
                normalized_name="reliance industries limited",
                country="IN",
            )
            db.session.add(company)
            db.session.flush()

            # Add two securities under the same company (EQ and BE series)
            sec1 = Security(
                company_id=company.id,
                symbol="RELIANCE",
                exchange="NSE",
                series="EQ",
                isin="INE002A01018",
            )
            sec2 = Security(
                company_id=company.id,
                symbol="RELIANCE",
                exchange="NSE",
                series="BE",
                isin="INE002A01018",
            )
            db.session.add_all([sec1, sec2])
            db.session.commit()

            # Verify relationship
            saved_company = Company.query.first()
            self.assertEqual(len(saved_company.securities), 2)
            self.assertEqual(saved_company.securities[0].symbol, "RELIANCE")

    def test_security_composite_unique_constraint(self):
        with self.app.app_context():
            company = Company(
                legal_name="Test Co",
                display_name="Test Co",
                normalized_name="test co",
                country="IN",
            )
            db.session.add(company)
            db.session.flush()

            sec1 = Security(company_id=company.id, symbol="TEST", exchange="NSE", series="EQ")
            sec2 = Security(company_id=company.id, symbol="TEST", exchange="NSE", series="EQ")
            db.session.add(sec1)
            db.session.commit()

            db.session.add(sec2)
            with self.assertRaises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_space_preserving_company_name_normalization(self):
        # Must preserve word boundaries and lowercase
        self.assertEqual(
            normalize_company_name("Tata Motors Limited"),
            "tata motors limited",
        )
        self.assertEqual(
            normalize_company_name("  Reliance   Industries  Ltd.  "),
            "reliance industries ltd",
        )
        self.assertEqual(
            normalize_company_name("3M India Limited (EQ)"),
            "3m india limited eq",
        )

    def test_isin_validation_and_luhn_checksum(self):
        # Valid Indian ISIN
        is_valid, err = validate_isin("INE144J01027", expected_country="IN")
        self.assertTrue(is_valid)
        self.assertEqual(err, "")

        # Invalid Luhn check digit
        is_valid_bad, err_bad = validate_isin("INE144J01029", expected_country="IN")
        self.assertFalse(is_valid_bad)
        self.assertIn("invalid Luhn check digit", err_bad)

        # Invalid length
        is_valid_len, err_len = validate_isin("INE144J01", expected_country="IN")
        self.assertFalse(is_valid_len)

        # Wrong country
        is_valid_ctry, err_ctry = validate_isin("US0378331005", expected_country="IN")
        self.assertFalse(is_valid_ctry)

    def test_date_and_numeric_parsing(self):
        dt, err = parse_listing_date("06-OCT-2008")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2008)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 6)

        dec, _ = parse_decimal("10.50")
        self.assertEqual(float(dec), 10.50)

        lot, _ = parse_integer("100")
        self.assertEqual(lot, 100)

    # ----------------------------------------------------------------
    # 2. Importer Live & Dry-Run Tests
    # ----------------------------------------------------------------
    def test_dry_run_makes_zero_database_modifications(self):
        with self.app.app_context():
            importer = NSECompanyImporter()
            report = importer.run(self.fixture_path, dry_run=True)

            self.assertTrue(report.dry_run)
            self.assertEqual(report.inserted_securities, 5)
            self.assertEqual(report.inserted_companies, 4)
            self.assertEqual(report.skipped_rows, 1)

            # Database must remain completely empty
            self.assertEqual(Company.query.count(), 0)
            self.assertEqual(Security.query.count(), 0)
            self.assertEqual(DataImportRun.query.count(), 0)

    def test_live_import_creates_companies_securities_and_audit_run(self):
        with self.app.app_context():
            importer = NSECompanyImporter()
            report = importer.run(self.fixture_path, dry_run=False)

            self.assertFalse(report.dry_run)
            self.assertEqual(report.inserted_securities, 5)
            # 4 distinct companies (TESTACME has 2 securities EQ and BE)
            self.assertEqual(report.inserted_companies, 4)
            self.assertEqual(report.skipped_rows, 1)

            # Check DB records
            self.assertEqual(Company.query.count(), 4)
            self.assertEqual(Security.query.count(), 5)

            # Audit record created
            audit = DataImportRun.query.first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.status, "completed")
            self.assertEqual(audit.inserted_companies, 4)
            self.assertEqual(audit.inserted_securities, 5)
            self.assertIsNotNone(audit.file_sha256)
            self.assertNotIn("Users", audit.source_file)

    def test_idempotent_reimport_counts_unchanged_securities(self):
        with self.app.app_context():
            importer = NSECompanyImporter()
            # 1st import
            importer.run(self.fixture_path, dry_run=False)

            # 2nd import of exact same file
            report2 = importer.run(self.fixture_path, dry_run=False)
            self.assertEqual(report2.inserted_companies, 0)
            self.assertEqual(report2.inserted_securities, 0)
            self.assertEqual(report2.unchanged_securities, 5)
            self.assertEqual(Company.query.count(), 4)
            self.assertEqual(Security.query.count(), 5)

    def test_fatal_import_rolls_back_and_records_failed_audit(self):
        with self.app.app_context():
            # Create a corrupted temporary CSV with missing required headers
            corrupt_file = os.path.join(self.temp_dir, "corrupt.csv")
            with open(corrupt_file, "w") as f:
                f.write("FOO,BAR\n1,2\n")

            importer = NSECompanyImporter()
            with self.assertRaises(ValueError):
                importer.run(corrupt_file, dry_run=False)

            # No company/security rows created
            self.assertEqual(Company.query.count(), 0)
            self.assertEqual(Security.query.count(), 0)

            # Failed audit run was logged
            failed_audit = DataImportRun.query.filter_by(status="failed").first()
            self.assertIsNotNone(failed_audit)
            self.assertIn("missing required columns", failed_audit.error_summary)

    def test_full_snapshot_requires_confirmation(self):
        with self.app.app_context():
            importer = NSECompanyImporter()
            with self.assertRaises(RuntimeError) as ctx:
                importer.run(
                    self.fixture_path,
                    full_snapshot=True,
                    confirm_deactivation=False,
                )
            self.assertIn("--confirm-deactivation was not provided", str(ctx.exception))

    def test_full_snapshot_safety_thresholds(self):
        with self.app.app_context():
            importer = NSECompanyImporter()
            # File with 5 rows should fail when min_rows=10
            with self.assertRaises(RuntimeError) as ctx:
                importer.run(
                    self.fixture_path,
                    full_snapshot=True,
                    confirm_deactivation=True,
                    min_rows=10,
                )
            self.assertIn("less than required min_rows", str(ctx.exception))

    def test_snapshot_deactivates_security_without_deactivating_company(self):
        with self.app.app_context():
            importer = NSECompanyImporter()
            # Initial import with 5 securities (min_rows=1 to allow small fixture)
            importer.run(self.fixture_path, min_rows=1)

            # Create a 2nd fixture omitting TESTSOLAR
            subset_file = os.path.join(self.temp_dir, "subset.csv")
            with open(subset_file, "w") as f:
                f.write(
                    "SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n"
                    "TESTACME,Acme Synthetic Corporation Limited,EQ,06-OCT-2008,5,1,INE144J01027,5\n"
                    "TESTACME,Acme Synthetic Corporation Limited,BE,15-MAY-2024,5,1,INE144J01027,5\n"
                    "TESTNEXUS,Nexus Digital Systems Limited,EQ,19-SEP-2019,10,1,INE466L01038,10\n"
                    "TESTQUANT,Quantum Biotech India Limited,EQ,20-APR-2026,2,1,INE105C01023,2\n"
                )

            report = importer.run(
                subset_file,
                full_snapshot=True,
                confirm_deactivation=True,
                min_rows=1,
                min_pct=50.0,
            )
            self.assertEqual(report.deactivated_securities, 1)

            # TESTSOLAR security must be deactivated
            solar_sec = Security.query.filter_by(symbol="TESTSOLAR").first()
            self.assertFalse(solar_sec.is_active)

            # Company must remain active
            solar_comp = Company.query.filter_by(normalized_name="solaris green power limited").first()
            self.assertTrue(solar_comp.is_active)


if __name__ == "__main__":
    unittest.main()
