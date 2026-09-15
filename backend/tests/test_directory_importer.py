"""
tests/test_directory_importer.py
--------------------------------------------------------------------------
Tests for multi-file Bhavcopy directory ingestion, per-file transactions,
deterministic sorting, hash-based skipping, and force overrides.
--------------------------------------------------------------------------
"""

import os
import shutil
import tempfile
import unittest
import zipfile
from decimal import Decimal

from app import create_app
from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.market_data_import_run import MarketDataImportRun
from services.importer.nse_market_importer import NseMarketImporter, MarketImportError


def _create_mock_bhavcopy_zip(zip_path, csv_filename, rows):
    """
    Helper that creates a valid NSE CM-UDiFF ZIP archive for tests.
    """
    csv_header = (
        "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd\n"
    )
    lines = [csv_header]
    for r in rows:
        lines.append(
            f"{r.get('TradDt', '2026-09-15')},{r.get('BizDt', '2026-09-15')},CM,NSE,EQ,12345,{r.get('ISIN', 'INE002A01018')},{r.get('TckrSymb', 'RELIANCE')},{r.get('SctySrs', 'EQ')},{r.get('OpnPric', '1450.00')},{r.get('HghPric', '1470.00')},{r.get('LwPric', '1440.00')},{r.get('ClsPric', '1465.00')},{r.get('LastPric', '1464.00')},{r.get('PrvsClsgPric', '1440.00')},,,0,0,{r.get('TtlTradgVol', '1000000')},{r.get('TtlTrfVal', '1465000000.00')},50000,1,1,,\n"
        )
    content = "".join(lines).encode("utf-8")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, content)


class TestDirectoryImporter(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(prefix="test_dir_imp_", suffix=".db")
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{self.db_path}",
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        })
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Seed Company & Security
        self.company = Company(
            legal_name="Reliance Industries Limited",
            display_name="Reliance Industries",
            normalized_name="reliance industries",
            country="IN",
            is_active=True,
        )
        db.session.add(self.company)
        db.session.commit()

        self.security = Security(
            company_id=self.company.id,
            symbol="RELIANCE",
            exchange="NSE",
            series="EQ",
            currency="INR",
            is_active=True,
        )
        db.session.add(self.security)
        db.session.commit()

        self.temp_dir = tempfile.mkdtemp(prefix="bhavcopy_dir_")
        self.importer = NseMarketImporter(db.session)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_directory_import_ordering_and_multi_file_ingestion(self):
        # Create two daily zip files: 2026-09-14 and 2026-09-15
        f1 = os.path.join(self.temp_dir, "BhavCopy_NSE_CM_0_0_0_20260914_F_0000.csv.zip")
        f2 = os.path.join(self.temp_dir, "BhavCopy_NSE_CM_0_0_0_20260915_F_0000.csv.zip")

        _create_mock_bhavcopy_zip(f1, "BhavCopy_NSE_CM_0_0_0_20260914_F_0000.csv", [
            {"TradDt": "2026-09-14", "TckrSymb": "RELIANCE", "ClsPric": "1440.00"}
        ])
        _create_mock_bhavcopy_zip(f2, "BhavCopy_NSE_CM_0_0_0_20260915_F_0000.csv", [
            {"TradDt": "2026-09-15", "TckrSymb": "RELIANCE", "ClsPric": "1465.00"}
        ])

        summary = self.importer.import_bhavcopy_directory(self.temp_dir)

        self.assertEqual(summary["total_files"], 2)
        self.assertEqual(summary["processed_files"], 2)
        self.assertEqual(summary["skipped_files"], 0)
        self.assertEqual(summary["inserted_rows"], 2)
        self.assertEqual(summary["status"], "completed")

        # Confirm 2 rows in DB
        prices = DailyPrice.query.filter_by(security_id=self.security.id).order_by(DailyPrice.trading_date).all()
        self.assertEqual(len(prices), 2)
        self.assertEqual(prices[0].close_price, Decimal("1440.00"))
        self.assertEqual(prices[1].close_price, Decimal("1465.00"))

    def test_skip_matching_completed_sha256_hash(self):
        f1 = os.path.join(self.temp_dir, "BhavCopy_NSE_CM_0_0_0_20260915_F_0000.csv.zip")
        _create_mock_bhavcopy_zip(f1, "BhavCopy_NSE_CM_0_0_0_20260915_F_0000.csv", [
            {"TradDt": "2026-09-15", "TckrSymb": "RELIANCE", "ClsPric": "1465.00"}
        ])

        # Run 1: initial import
        summary1 = self.importer.import_bhavcopy_directory(self.temp_dir)
        self.assertEqual(summary1["processed_files"], 1)
        self.assertEqual(summary1["inserted_rows"], 1)

        # Run 2: re-run without --force -> should skip based on completed audit hash
        summary2 = self.importer.import_bhavcopy_directory(self.temp_dir, force=False)
        self.assertEqual(summary2["processed_files"], 0)
        self.assertEqual(summary2["skipped_files"], 1)
        self.assertEqual(summary2["inserted_rows"], 0)

        # Run 3: re-run WITH --force -> should reprocess without skipping
        summary3 = self.importer.import_bhavcopy_directory(self.temp_dir, force=True)
        self.assertEqual(summary3["processed_files"], 1)
        self.assertEqual(summary3["skipped_files"], 0)
        self.assertEqual(summary3["unchanged_rows"], 1)

    def test_per_file_independent_transactions(self):
        # File 1: valid
        f1 = os.path.join(self.temp_dir, "file1.zip")
        _create_mock_bhavcopy_zip(f1, "file1.csv", [
            {"TradDt": "2026-09-14", "TckrSymb": "RELIANCE", "ClsPric": "1440.00"}
        ])

        # File 2: corrupt zip
        f2 = os.path.join(self.temp_dir, "file2.zip")
        with open(f2, "wb") as f:
            f.write(b"NOT A VALID ZIP ARCHIVE")

        # In non-strict mode, file 1 commits and file 2 fails
        summary = self.importer.import_bhavcopy_directory(self.temp_dir, strict=False)

        self.assertEqual(summary["total_files"], 2)
        self.assertEqual(summary["processed_files"], 1)
        self.assertEqual(summary["failed_files"], 1)
        self.assertEqual(summary["status"], "completed_with_errors")

        # Verify File 1 remained committed in the DB!
        count = DailyPrice.query.filter_by(security_id=self.security.id).count()
        self.assertEqual(count, 1)

    def test_dry_run_directory_writes_nothing(self):
        f1 = os.path.join(self.temp_dir, "file1.zip")
        _create_mock_bhavcopy_zip(f1, "file1.csv", [
            {"TradDt": "2026-09-14", "TckrSymb": "RELIANCE", "ClsPric": "1440.00"}
        ])

        summary = self.importer.import_bhavcopy_directory(self.temp_dir, dry_run=True)
        self.assertEqual(summary["total_files"], 1)

        # Database must have 0 prices
        count = DailyPrice.query.count()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
