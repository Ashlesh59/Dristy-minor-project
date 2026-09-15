"""
services/importer/nse_market_importer.py
--------------------------------------------------------------------------
Transactional, idempotent market data importer for NSE CM-UDiFF Bhavcopy.
--------------------------------------------------------------------------
"""

import logging
import time
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, Optional

from database.db import db
from models.security import Security
from models.daily_price import DailyPrice
from models.market_data_import_run import MarketDataImportRun
from services.importer.zip_reader import read_bhavcopy_zip, ZipArchiveError
from services.importer.price_parser import (
    build_header_map,
    parse_and_validate_row,
    PriceValidationError,
)

logger = logging.getLogger(__name__)


class MarketImportError(Exception):
    """Raised when market data import fails fatally."""
    pass


class NseMarketImporter:
    """
    Importer for NSE CM-UDiFF Bhavcopy ZIP archives.
    """

    def __init__(self, db_session=None):
        self.session = db_session or db.session

    def import_bhavcopy_directory(
        self,
        directory_path: str,
        source: str = "NSE_UDIFF",
        dry_run: bool = False,
        strict: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes a deterministic, multi-file import across a directory of Bhavcopy ZIP archives.
        Each file is processed in its own independent database transaction.
        
        Args:
            directory_path: Directory containing .zip Bhavcopy archives.
            source: Market data source identifier.
            dry_run: If True, executes dry run validation for each file.
            strict: If True, fails on invalid rows within a file.
            force: If True, re-processes files even if a completed audit run matches the SHA-256.
            
        Returns:
            dict: Summary metrics across all files, including per-file results.
        """
        import os
        from services.importer.zip_reader import compute_file_sha256

        if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
            raise MarketImportError(f"Directory not found or is not a directory: {directory_path}")

        # 1. Deterministic ordering: alphabetical / lexicographical sort on filenames
        zip_files = sorted([
            f for f in os.listdir(directory_path)
            if f.lower().endswith(".zip") and not f.startswith(".")
        ])

        summary = {
            "source": source,
            "directory": directory_path,
            "total_files": len(zip_files),
            "processed_files": 0,
            "skipped_files": 0,
            "failed_files": 0,
            "total_rows": 0,
            "inserted_rows": 0,
            "updated_rows": 0,
            "unchanged_rows": 0,
            "skipped_rows": 0,
            "unresolved_rows": 0,
            "failed_rows": 0,
            "file_results": [],
            "status": "completed",
        }

        for filename in zip_files:
            file_path = os.path.join(directory_path, filename)
            
            # Check SHA-256 against completed audit runs if not forced
            file_sha256 = None
            if not force:
                try:
                    file_sha256 = compute_file_sha256(file_path)
                    completed_run = (
                        self.session.query(MarketDataImportRun)
                        .filter(
                            MarketDataImportRun.file_sha256 == file_sha256,
                            MarketDataImportRun.status == "completed",
                        )
                        .first()
                    )
                    if completed_run:
                        # Skip processing
                        file_result = {
                            "filename": filename,
                            "file_sha256": file_sha256,
                            "status": "skipped",
                            "reason": "Already imported (matching completed SHA-256 run)",
                            "total_rows": 0,
                            "inserted_rows": 0,
                            "updated_rows": 0,
                            "unchanged_rows": 0,
                            "skipped_rows": 0,
                            "unresolved_rows": 0,
                            "failed_rows": 0,
                        }
                        summary["skipped_files"] += 1
                        summary["file_results"].append(file_result)
                        continue
                except Exception as ex:
                    logger.warning("Could not compute hash for %s: %s", filename, ex)

            # Process file in its own transaction
            try:
                res = self.import_bhavcopy(
                    file_path=file_path,
                    source=source,
                    dry_run=dry_run,
                    strict=strict,
                )
                summary["processed_files"] += 1
                summary["total_rows"] += res.get("total_rows", 0)
                summary["inserted_rows"] += res.get("inserted_rows", 0)
                summary["updated_rows"] += res.get("updated_rows", 0)
                summary["unchanged_rows"] += res.get("unchanged_rows", 0)
                summary["skipped_rows"] += res.get("skipped_rows", 0)
                summary["unresolved_rows"] += res.get("unresolved_rows", 0)
                summary["failed_rows"] += res.get("failed_rows", 0)
                
                summary["file_results"].append({
                    "filename": filename,
                    "file_sha256": res.get("file_sha256"),
                    "trading_date": res.get("trading_date"),
                    "status": res.get("status"),
                    "total_rows": res.get("total_rows", 0),
                    "inserted_rows": res.get("inserted_rows", 0),
                    "updated_rows": res.get("updated_rows", 0),
                    "unchanged_rows": res.get("unchanged_rows", 0),
                    "skipped_rows": res.get("skipped_rows", 0),
                    "unresolved_rows": res.get("unresolved_rows", 0),
                    "failed_rows": res.get("failed_rows", 0),
                    "duration_seconds": res.get("duration_seconds", 0),
                })
            except Exception as e:
                summary["failed_files"] += 1
                summary["file_results"].append({
                    "filename": filename,
                    "file_sha256": file_sha256,
                    "status": "failed",
                    "error": str(e),
                    "total_rows": 0,
                    "inserted_rows": 0,
                    "updated_rows": 0,
                    "unchanged_rows": 0,
                    "skipped_rows": 0,
                    "unresolved_rows": 0,
                    "failed_rows": 0,
                })
                if strict:
                    summary["status"] = "failed"
                    raise MarketImportError(f"Directory import stopped on strict error in {filename}: {e}") from e

        if summary["failed_files"] > 0:
            summary["status"] = "completed_with_errors"

        return summary

    def import_bhavcopy(
        self,
        file_path: str,
        source: str = "NSE_UDIFF",
        dry_run: bool = False,
        strict: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes a transactional import of a Bhavcopy ZIP archive.
        
        Args:
            file_path: Local path to the ZIP archive.
            source: Identifier for market data source.
            dry_run: If True, validates all rows but rolls back database changes.
            strict: If True, fails the complete import if any row is invalid or unresolved.
            
        Returns:
            dict: Summary metrics of the import run.
        """
        start_time = time.time()
        started_at = datetime.utcnow()
        sanitized_filename = MarketDataImportRun.sanitize_path(file_path)

        stats = {
            "source": source,
            "source_file": sanitized_filename,
            "file_sha256": "UNKNOWN",
            "trading_date": None,
            "total_rows": 0,
            "inserted_rows": 0,
            "updated_rows": 0,
            "unchanged_rows": 0,
            "skipped_rows": 0,
            "unresolved_rows": 0,
            "failed_rows": 0,
            "error_summary": None,
            "status": "pending",
            "duration_seconds": 0.0,
            "unresolved_samples": [],
            "error_samples": [],
        }

        # 1. Read and validate ZIP archive
        try:
            file_sha256, csv_reader, zf = read_bhavcopy_zip(file_path)
            stats["file_sha256"] = file_sha256
        except Exception as e:
            error_msg = f"Archive validation failure: {e}"
            stats["status"] = "failed"
            stats["error_summary"] = error_msg
            stats["duration_seconds"] = round(time.time() - start_time, 3)
            self._record_audit_log(stats, started_at, error_msg)
            raise MarketImportError(error_msg) from e

        # 2. Map and validate required headers
        header_map = build_header_map(csv_reader.fieldnames or [])
        required_headers = ["symbol", "series", "trading_date", "open", "high", "low", "close"]
        missing_headers = [h for h in required_headers if h not in header_map]
        if missing_headers:
            zf.close()
            error_msg = f"Missing required canonical headers in CSV: {', '.join(missing_headers)}"
            stats["status"] = "failed"
            stats["error_summary"] = error_msg
            stats["duration_seconds"] = round(time.time() - start_time, 3)
            self._record_audit_log(stats, started_at, error_msg)
            raise MarketImportError(error_msg)

        # 3. Preload all active NSE securities for fast O(1) in-memory resolution
        try:
            active_securities = (
                self.session.query(Security.id, Security.symbol, Security.series)
                .filter(Security.exchange == "NSE", Security.is_active == True)
                .all()
            )
            securities_map = {
                (s.symbol.upper(), (s.series or "EQ").upper()): s.id
                for s in active_securities
            }
        except Exception as e:
            zf.close()
            error_msg = f"Failed to load active securities: {e}"
            stats["status"] = "failed"
            stats["error_summary"] = error_msg
            stats["duration_seconds"] = round(time.time() - start_time, 3)
            self._record_audit_log(stats, started_at, error_msg)
            raise MarketImportError(error_msg) from e

        # Preload existing daily prices for this source to optimize upsert comparisons
        existing_prices_map = {}
        detected_trading_date = None

        try:
            # Step 4: Stream and process CSV rows
            row_idx = 0
            for raw_row in csv_reader:
                row_idx += 1
                stats["total_rows"] += 1

                # A. Parse and validate row fields
                try:
                    parsed = parse_and_validate_row(raw_row, header_map, row_idx)
                except PriceValidationError as pve:
                    stats["failed_rows"] += 1
                    if len(stats["error_samples"]) < 5:
                        stats["error_samples"].append(f"Row {row_idx}: {pve}")
                    if strict:
                        raise MarketImportError(f"Strict mode rejected invalid row {row_idx}: {pve}")
                    continue
                except Exception as ex:
                    stats["failed_rows"] += 1
                    if len(stats["error_samples"]) < 5:
                        stats["error_samples"].append(f"Row {row_idx} unexpected: {ex}")
                    if strict:
                        raise MarketImportError(f"Strict mode rejected unexpected error on row {row_idx}: {ex}")
                    continue

                # Set or check trading date
                t_date = parsed["trading_date"]
                if detected_trading_date is None:
                    detected_trading_date = t_date
                    stats["trading_date"] = detected_trading_date
                    # Fetch existing prices for this date & source into memory
                    db_existing = (
                        self.session.query(DailyPrice)
                        .filter(DailyPrice.trading_date == detected_trading_date, DailyPrice.source == source)
                        .all()
                    )
                    for dp in db_existing:
                        existing_prices_map[dp.security_id] = dp

                # B. Resolve Security ID using exchange="NSE" + symbol + series
                lookup_key = (parsed["symbol"], parsed["series"])
                security_id = securities_map.get(lookup_key)

                if not security_id:
                    stats["unresolved_rows"] += 1
                    if len(stats["unresolved_samples"]) < 5:
                        stats["unresolved_samples"].append(
                            f"Row {row_idx}: Unknown Security (Symbol: {parsed['symbol']}, Series: {parsed['series']})"
                        )
                    if strict:
                        raise MarketImportError(
                            f"Strict mode rejected unresolved security on row {row_idx}: {lookup_key}"
                        )
                    continue

                # C. Idempotent Upsert Comparison
                existing_dp = existing_prices_map.get(security_id)

                if existing_dp is None:
                    # New Price Record
                    new_dp = DailyPrice(
                        security_id=security_id,
                        trading_date=parsed["trading_date"],
                        open_price=parsed["open_price"],
                        high_price=parsed["high_price"],
                        low_price=parsed["low_price"],
                        close_price=parsed["close_price"],
                        last_price=parsed["last_price"],
                        previous_close=parsed["previous_close"],
                        vwap=parsed["vwap"],
                        volume=parsed["volume"],
                        turnover=parsed["turnover"],
                        trade_count=parsed["trade_count"],
                        deliverable_quantity=parsed["deliverable_quantity"],
                        deliverable_percentage=parsed["deliverable_percentage"],
                        source=source,
                        source_file_sha256=file_sha256,
                        source_row_number=row_idx,
                        is_adjusted=False,
                    )
                    self.session.add(new_dp)
                    existing_prices_map[security_id] = new_dp
                    stats["inserted_rows"] += 1
                else:
                    # Check if any field changed
                    changed = self._is_price_row_modified(existing_dp, parsed)
                    if changed:
                        existing_dp.open_price = parsed["open_price"]
                        existing_dp.high_price = parsed["high_price"]
                        existing_dp.low_price = parsed["low_price"]
                        existing_dp.close_price = parsed["close_price"]
                        existing_dp.last_price = parsed["last_price"]
                        existing_dp.previous_close = parsed["previous_close"]
                        existing_dp.vwap = parsed["vwap"]
                        existing_dp.volume = parsed["volume"]
                        existing_dp.turnover = parsed["turnover"]
                        existing_dp.trade_count = parsed["trade_count"]
                        existing_dp.deliverable_quantity = parsed["deliverable_quantity"]
                        existing_dp.deliverable_percentage = parsed["deliverable_percentage"]
                        existing_dp.source_file_sha256 = file_sha256
                        existing_dp.source_row_number = row_idx
                        existing_dp.updated_at = datetime.utcnow()
                        stats["updated_rows"] += 1
                    else:
                        stats["unchanged_rows"] += 1

            zf.close()

            # Compile error summaries if any non-fatal errors occurred
            summary_parts = []
            if stats["unresolved_rows"] > 0:
                summary_parts.append(f"{stats['unresolved_rows']} unresolved security rows.")
            if stats["failed_rows"] > 0:
                summary_parts.append(f"{stats['failed_rows']} invalid price rows.")
            if summary_parts:
                stats["error_summary"] = " ".join(summary_parts)

            stats["duration_seconds"] = round(time.time() - start_time, 3)

            # Step 5: Transaction Decision
            if dry_run:
                self.session.rollback()
                stats["status"] = "dry_run"
                self._record_audit_log(stats, started_at, stats["error_summary"])
                return stats

            # Commit all price changes in single transaction
            self.session.commit()
            stats["status"] = "completed"
            self._record_audit_log(stats, started_at, stats["error_summary"])
            return stats

        except Exception as e:
            zf.close()
            self.session.rollback()
            error_msg = str(e)
            stats["status"] = "failed"
            stats["error_summary"] = error_msg
            stats["duration_seconds"] = round(time.time() - start_time, 3)
            self._record_audit_log(stats, started_at, error_msg)
            raise MarketImportError(f"Market import failed: {error_msg}") from e

    def _is_price_row_modified(self, existing: DailyPrice, parsed: Dict[str, Any]) -> bool:
        """
        Compares existing database DailyPrice model values against newly parsed values.
        """
        def _dec_diff(d1, d2):
            if d1 is None and d2 is None:
                return False
            if d1 is None or d2 is None:
                return True
            return Decimal(str(d1)) != Decimal(str(d2))

        def _val_diff(v1, v2):
            return v1 != v2

        if _dec_diff(existing.open_price, parsed["open_price"]):
            return True
        if _dec_diff(existing.high_price, parsed["high_price"]):
            return True
        if _dec_diff(existing.low_price, parsed["low_price"]):
            return True
        if _dec_diff(existing.close_price, parsed["close_price"]):
            return True
        if _dec_diff(existing.last_price, parsed["last_price"]):
            return True
        if _dec_diff(existing.previous_close, parsed["previous_close"]):
            return True
        if _dec_diff(existing.vwap, parsed["vwap"]):
            return True
        if _val_diff(existing.volume, parsed["volume"]):
            return True
        if _dec_diff(existing.turnover, parsed["turnover"]):
            return True
        if _val_diff(existing.trade_count, parsed["trade_count"]):
            return True
        if _val_diff(existing.deliverable_quantity, parsed["deliverable_quantity"]):
            return True
        if _dec_diff(existing.deliverable_percentage, parsed["deliverable_percentage"]):
            return True

        return False

    def _record_audit_log(self, stats: Dict[str, Any], started_at: datetime, error_summary: Optional[str]):
        """
        Records an independent audit log entry in a dedicated transaction.
        """
        try:
            audit_run = MarketDataImportRun(
                source=stats["source"],
                source_file=stats["source_file"],
                file_sha256=stats["file_sha256"],
                trading_date=stats.get("trading_date"),
                started_at=started_at,
                completed_at=datetime.utcnow(),
                status=stats["status"],
                total_rows=stats["total_rows"],
                inserted_rows=stats["inserted_rows"],
                updated_rows=stats["updated_rows"],
                unchanged_rows=stats["unchanged_rows"],
                skipped_rows=stats["skipped_rows"],
                unresolved_rows=stats["unresolved_rows"],
                failed_rows=stats["failed_rows"],
                error_summary=error_summary,
            )
            self.session.add(audit_run)
            self.session.commit()
        except Exception as audit_exc:
            logger.error("Failed to commit market data audit log: %s", audit_exc)
            self.session.rollback()
