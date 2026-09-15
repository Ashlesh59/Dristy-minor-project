"""
backend/tests/test_market_importer.py
--------------------------------------------------------------------------
Comprehensive Automated Test Suite for Market Data Importer (Phase 2A).
--------------------------------------------------------------------------
"""

import os
import shutil
import tempfile
import unittest
import zipfile
from datetime import date
from decimal import Decimal

from app import create_app
from config import Config
from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.market_data_import_run import MarketDataImportRun
from services.importer.zip_reader import read_bhavcopy_zip, ZipArchiveError
from services.importer.price_parser import (
    build_header_map,
    parse_and_validate_row,
    parse_trading_date,
    PriceValidationError,
)
from services.importer.nse_market_importer import NseMarketImporter, MarketImportError


class MarketImporterTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="investiq_mkt_imp_test_")
        cls.test_db_path = os.path.join(cls.temp_dir, "mkt_imp_test.db")

        # Verify database path isolation
        dev_db = os.path.abspath(os.path.join(Config.BASE_DIR, "database", "investiq.db"))
        assert os.path.normcase(os.path.abspath(cls.test_db_path)) != os.path.normcase(dev_db)

        cls.app = create_app({
            "TESTING": True,
            "DEBUG": False,
            "SECRET_KEY": "test-mkt-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{cls.test_db_path}",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "RUN_MIGRATIONS": False,
        })

        # Locate synthetic fixture
        cls.fixture_path = os.path.join(
            Config.BASE_DIR, "tests", "fixtures", "synthetic_nse_udiff_bhavcopy.zip"
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
            self._seed_test_securities()

    def tearDown(self):
        with self.app.app_context():
            db.session.rollback()
            db.session.remove()
            for table in reversed(db.metadata.sorted_tables):
                db.session.execute(table.delete())
            db.session.commit()

    def _seed_test_securities(self):
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

        s1 = Security(
            company_id=c1.id,
            symbol="RELIANCE",
            exchange="NSE",
            series="EQ",
            isin="INE002A01018",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s1)

        # 2. TCS
        c2 = Company(
            legal_name="Tata Consultancy Services Limited",
            display_name="Tata Consultancy Services Limited",
            normalized_name="tata consultancy services limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c2)
        db.session.flush()

        s2 = Security(
            company_id=c2.id,
            symbol="TCS",
            exchange="NSE",
            series="EQ",
            isin="INE467B01029",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s2)

        # 3. Tata Motors
        c3 = Company(
            legal_name="Tata Motors Limited",
            display_name="Tata Motors Limited",
            normalized_name="tata motors limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c3)
        db.session.flush()

        s3 = Security(
            company_id=c3.id,
            symbol="TATAMOTORS",
            exchange="NSE",
            series="EQ",
            isin="INE155A01022",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s3)

        # 4. Infosys
        c4 = Company(
            legal_name="Infosys Limited",
            display_name="Infosys Limited",
            normalized_name="infosys limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c4)
        db.session.flush()

        s4 = Security(
            company_id=c4.id,
            symbol="INFY",
            exchange="NSE",
            series="EQ",
            isin="INE009A01021",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s4)

        # 5. HDFC Bank
        c5 = Company(
            legal_name="HDFC Bank Limited",
            display_name="HDFC Bank Limited",
            normalized_name="hdfc bank limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c5)
        db.session.flush()

        s5 = Security(
            company_id=c5.id,
            symbol="HDFCBANK",
            exchange="NSE",
            series="EQ",
            isin="INE040A01034",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s5)

        # 6. Illiquid stock for zero-volume testing
        c6 = Company(
            legal_name="Illiquid Co Limited",
            display_name="Illiquid Co Limited",
            normalized_name="illiquid co limited",
            country="IN",
            is_active=True,
        )
        db.session.add(c6)
        db.session.flush()

        s6 = Security(
            company_id=c6.id,
            symbol="ILLIQUID",
            exchange="NSE",
            series="EQ",
            isin="INE888Z01012",
            currency="INR",
            asset_type="Equity",
            is_active=True,
        )
        db.session.add(s6)

        db.session.commit()

    # ----------------------------------------------------------------
    # 1. ZIP Reader & Security Tests
    # ----------------------------------------------------------------
    def test_valid_zip_reading(self):
        sha256, reader, zf = read_bhavcopy_zip(self.fixture_path)
        self.assertIsNotNone(sha256)
        self.assertEqual(len(sha256), 64)
        self.assertIn("TckrSymb", reader.fieldnames)
        zf.close()

    def test_invalid_zip_rejection(self):
        bad_zip = os.path.join(self.temp_dir, "corrupt.zip")
        with open(bad_zip, "w") as f:
            f.write("not a zip file")

        with self.assertRaises(ZipArchiveError):
            read_bhavcopy_zip(bad_zip)

    def test_zip_path_traversal_rejection(self):
        malicious_zip = os.path.join(self.temp_dir, "malicious.zip")
        with zipfile.ZipFile(malicious_zip, "w") as zf:
            zf.writestr("../../etc/passwd.csv", "TradDt,TckrSymb\n2026-09-15,TEST")

        with self.assertRaises(ZipArchiveError) as ctx:
            read_bhavcopy_zip(malicious_zip)
        self.assertIn("path-traversal", str(ctx.exception).lower())

    def test_missing_csv_in_zip_rejection(self):
        empty_zip = os.path.join(self.temp_dir, "no_csv.zip")
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("notes.txt", "No csv data here")

        with self.assertRaises(ZipArchiveError) as ctx:
            read_bhavcopy_zip(empty_zip)
        self.assertIn("no csv data file found", str(ctx.exception).lower())

    # ----------------------------------------------------------------
    # 2. Parsing & Validation Rules
    # ----------------------------------------------------------------
    def test_price_validation_negative_price_rejection(self):
        header_map = build_header_map(["TradDt", "TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric"])
        bad_row = {
            "TradDt": "2026-09-15",
            "TckrSymb": "RELIANCE",
            "SctySrs": "EQ",
            "OpnPric": "-10.00",
            "HghPric": "20.00",
            "LwPric": "5.00",
            "ClsPric": "15.00",
        }
        with self.assertRaises(PriceValidationError) as ctx:
            parse_and_validate_row(bad_row, header_map, 1)
        self.assertIn("cannot be negative", str(ctx.exception))

    def test_price_validation_invalid_ohlc_relationship(self):
        header_map = build_header_map(["TradDt", "TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric"])
        # High < Close
        bad_row = {
            "TradDt": "2026-09-15",
            "TckrSymb": "RELIANCE",
            "SctySrs": "EQ",
            "OpnPric": "100.00",
            "HghPric": "90.00",
            "LwPric": "80.00",
            "ClsPric": "95.00",
        }
        with self.assertRaises(PriceValidationError) as ctx:
            parse_and_validate_row(bad_row, header_map, 1)
        self.assertIn("High price", str(ctx.exception))

    def test_trading_date_formats(self):
        self.assertEqual(parse_trading_date("2026-09-15"), date(2026, 9, 15))
        self.assertEqual(parse_trading_date("20260915"), date(2026, 9, 15))
        self.assertEqual(parse_trading_date("15-SEP-2026"), date(2026, 9, 15))

    # ----------------------------------------------------------------
    # 3. Full Transactional Importer Tests
    # ----------------------------------------------------------------
    def test_dry_run_produces_zero_database_writes(self):
        with self.app.app_context():
            importer = NseMarketImporter(db.session)
            results = importer.import_bhavcopy(self.fixture_path, dry_run=True)

            self.assertEqual(results["status"], "dry_run")
            self.assertEqual(results["total_rows"], 7)
            # Database should have 0 daily prices
            self.assertEqual(DailyPrice.query.count(), 0)

            # Audit log should record dry_run
            audit = MarketDataImportRun.query.first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.status, "dry_run")

    def test_normal_mode_imports_valid_rows_and_tracks_errors(self):
        with self.app.app_context():
            importer = NseMarketImporter(db.session)
            results = importer.import_bhavcopy(self.fixture_path, dry_run=False, strict=False)

            self.assertEqual(results["status"], "completed")
            self.assertEqual(results["total_rows"], 7)
            self.assertEqual(results["inserted_rows"], 4)  # RELIANCE, TCS, HDFCBANK, ILLIQUID
            self.assertEqual(results["unresolved_rows"], 1) # UNKNOWN_SYM
            self.assertEqual(results["failed_rows"], 2)     # TATAMOTORS (-price), INFY (invalid OHLC)

            # Confirm stored rows in database
            self.assertEqual(DailyPrice.query.count(), 4)

            # Verify no unknown security or company was created
            self.assertIsNone(Security.query.filter_by(symbol="UNKNOWN_SYM").first())
            self.assertIsNone(Company.query.filter_by(normalized_name="unknown sym").first())

            # Verify zero-volume stock was stored correctly
            illiquid = DailyPrice.query.join(Security).filter(Security.symbol == "ILLIQUID").first()
            self.assertIsNotNone(illiquid)
            self.assertEqual(illiquid.volume, 0)
            self.assertEqual(illiquid.open_price, Decimal("50.0000"))

    def test_reimport_is_idempotent_no_duplicates(self):
        with self.app.app_context():
            importer = NseMarketImporter(db.session)
            # Run 1
            importer.import_bhavcopy(self.fixture_path, dry_run=False)
            self.assertEqual(DailyPrice.query.count(), 4)

            # Run 2 on identical file
            results2 = importer.import_bhavcopy(self.fixture_path, dry_run=False)
            self.assertEqual(results2["inserted_rows"], 0)
            self.assertEqual(results2["unchanged_rows"], 4)
            self.assertEqual(results2["updated_rows"], 0)
            # Count must remain exactly 4 (no duplicates)
            self.assertEqual(DailyPrice.query.count(), 4)

    def test_changed_reimport_updates_prices(self):
        with self.app.app_context():
            importer = NseMarketImporter(db.session)
            # Run 1
            importer.import_bhavcopy(self.fixture_path, dry_run=False)
            initial_reliance = DailyPrice.query.join(Security).filter(Security.symbol == "RELIANCE").first()
            self.assertEqual(initial_reliance.close_price, Decimal("2475.5000"))

            # Create modified zip with updated close price for RELIANCE
            mod_csv = '''TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol,TtlTrdVal
2026-09-15,RELIANCE,EQ,2450.00,2490.00,2440.00,2485.00,1600000,3900000000.00
'''
            mod_zip = os.path.join(self.temp_dir, "modified_bhavcopy.zip")
            with zipfile.ZipFile(mod_zip, "w") as zf:
                zf.writestr("BhavCopy.csv", mod_csv.strip())

            # Run 2 with modified file
            results_mod = importer.import_bhavcopy(mod_zip, dry_run=False)
            self.assertEqual(results_mod["inserted_rows"], 0)
            self.assertEqual(results_mod["updated_rows"], 1)
            self.assertEqual(results_mod["unchanged_rows"], 0)

            # Check database value updated
            updated_reliance = DailyPrice.query.join(Security).filter(Security.symbol == "RELIANCE").first()
            self.assertEqual(updated_reliance.close_price, Decimal("2485.0000"))
            self.assertEqual(updated_reliance.high_price, Decimal("2490.0000"))

    def test_strict_mode_rejects_and_rolls_back(self):
        with self.app.app_context():
            importer = NseMarketImporter(db.session)
            with self.assertRaises(MarketImportError):
                importer.import_bhavcopy(self.fixture_path, dry_run=False, strict=True)

            # In strict mode with errors in file, 0 prices should be saved
            self.assertEqual(DailyPrice.query.count(), 0)

            # Failed audit run recorded
            audit = MarketDataImportRun.query.first()
            self.assertIsNotNone(audit)
            self.assertEqual(audit.status, "failed")

    def test_time_series_date_preservation(self):
        with self.app.app_context():
            importer = NseMarketImporter(db.session)
            # Create Day 1 ZIP (2026-09-14)
            d1_csv = "TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric\n2026-09-14,RELIANCE,EQ,2400.00,2420.00,2390.00,2410.00"
            d1_zip = os.path.join(self.temp_dir, "d1.zip")
            with zipfile.ZipFile(d1_zip, "w") as zf:
                zf.writestr("d1.csv", d1_csv)

            # Create Day 2 ZIP (2026-09-15)
            d2_csv = "TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric\n2026-09-15,RELIANCE,EQ,2450.00,2480.00,2440.00,2475.50"
            d2_zip = os.path.join(self.temp_dir, "d2.zip")
            with zipfile.ZipFile(d2_zip, "w") as zf:
                zf.writestr("d2.csv", d2_csv)

            # Import Day 2 first
            importer.import_bhavcopy(d2_zip)
            self.assertEqual(DailyPrice.query.count(), 1)

            # Import Day 1 (older date backfill)
            importer.import_bhavcopy(d1_zip)
            self.assertEqual(DailyPrice.query.count(), 2)

            # Both dates preserved
            dates = [dp.trading_date for dp in DailyPrice.query.order_by(DailyPrice.trading_date.asc()).all()]
            self.assertEqual(dates, [date(2026, 9, 14), date(2026, 9, 15)])


if __name__ == "__main__":
    unittest.main()
