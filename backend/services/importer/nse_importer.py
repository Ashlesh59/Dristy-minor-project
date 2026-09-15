"""
services/importer/nse_importer.py
--------------------------------------------------------------------------
Transactional, idempotent NSE Equity CSV Importer.
Separates Company (issuer) and Security (listed instrument) entities.
Enforces audit logging, dry-run guarantees, and snapshot safety guards.
--------------------------------------------------------------------------
"""

from datetime import datetime, timezone
import json
import os
from typing import Dict, Any, Optional, Set, Tuple

from config import Config
from database.db import db
from models.company import Company
from models.security import Security
from models.data_import_run import DataImportRun
from services.importer.csv_reader import read_nse_csv
from services.importer.normalizer import normalize_nse_row, ParsedNSEEquity


def _utc_now():
    return datetime.now(timezone.utc)


def _get_privacy_safe_file_path(file_path: str) -> str:
    """Returns a repository-relative or basename path to avoid leaking absolute system paths."""
    try:
        repo_root = os.path.abspath(os.path.join(Config.BASE_DIR, ".."))
        rel = os.path.relpath(os.path.abspath(file_path), repo_root)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
    except Exception:
        pass
    return os.path.basename(file_path)


class ImportReport:
    def __init__(
        self,
        source: str,
        source_file: str,
        file_sha256: str,
        dry_run: bool,
        full_snapshot: bool,
        total_rows: int = 0,
        inserted_companies: int = 0,
        updated_companies: int = 0,
        inserted_securities: int = 0,
        updated_securities: int = 0,
        unchanged_securities: int = 0,
        skipped_rows: int = 0,
        failed_rows: int = 0,
        deactivated_securities: int = 0,
        errors: list = None,
        warnings: list = None,
    ):
        self.source = source
        self.source_file = source_file
        self.file_sha256 = file_sha256
        self.dry_run = dry_run
        self.full_snapshot = full_snapshot
        self.total_rows = total_rows
        self.inserted_companies = inserted_companies
        self.updated_companies = updated_companies
        self.inserted_securities = inserted_securities
        self.updated_securities = updated_securities
        self.unchanged_securities = unchanged_securities
        self.skipped_rows = skipped_rows
        self.failed_rows = failed_rows
        self.deactivated_securities = deactivated_securities
        self.errors = errors or []
        self.warnings = warnings or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "source_file": self.source_file,
            "file_sha256": self.file_sha256,
            "dry_run": self.dry_run,
            "full_snapshot": self.full_snapshot,
            "total_rows": self.total_rows,
            "inserted_companies": self.inserted_companies,
            "updated_companies": self.updated_companies,
            "inserted_securities": self.inserted_securities,
            "updated_securities": self.updated_securities,
            "unchanged_securities": self.unchanged_securities,
            "skipped_rows": self.skipped_rows,
            "failed_rows": self.failed_rows,
            "deactivated_securities": self.deactivated_securities,
            "errors_count": len(self.errors),
            "warnings_count": len(self.warnings),
            "errors": self.errors[:50],  # cap for display
            "warnings": self.warnings[:50],
        }


class NSECompanyImporter:
    def __init__(self, exchange: str = "NSE", country: str = "IN", currency: str = "INR"):
        self.exchange = exchange
        self.country = country
        self.currency = currency

    def run(
        self,
        file_path: str,
        dry_run: bool = False,
        full_snapshot: bool = False,
        confirm_deactivation: bool = False,
        min_rows: int = 100,
        min_pct: float = 80.0,
    ) -> ImportReport:
        """
        Executes an idempotent import of NSE equities from a CSV file.
        """
        started_at = _utc_now()
        safe_path = _get_privacy_safe_file_path(file_path)

        report = ImportReport(
            source=self.exchange,
            source_file=safe_path,
            file_sha256="",
            dry_run=dry_run,
            full_snapshot=full_snapshot,
            total_rows=0,
        )

        try:
            # 1. Read & validate CSV
            csv_res = read_nse_csv(file_path)
            report.file_sha256 = csv_res.file_sha256
            report.total_rows = csv_res.total_raw_rows

            if csv_res.total_raw_rows == 0:
                raise ValueError(f"Import file is empty or missing content: {safe_path}")

            # Check for required headers
            required_headers = {"SYMBOL"}
            name_headers = {"NAME OF COMPANY", "NAME_OF_COMPANY", "COMPANY NAME"}
            has_symbol = any(h in required_headers for h in csv_res.headers)
            has_name = any(h in name_headers for h in csv_res.headers)

            if not has_symbol or not has_name:
                raise ValueError(
                    f"File headers missing required columns ('SYMBOL', 'NAME OF COMPANY'). Found: {csv_res.headers}"
                )

            if dry_run:
                # Execute in-memory calculation with zero DB modifications
                return self._execute_dry_run(
                    csv_res=csv_res,
                    report=report,
                    full_snapshot=full_snapshot,
                    confirm_deactivation=confirm_deactivation,
                    min_rows=min_rows,
                    min_pct=min_pct,
                )

            # 2. Live Transactional Execution
            self._execute_live_import(
                csv_res=csv_res,
                report=report,
                started_at=started_at,
                full_snapshot=full_snapshot,
                confirm_deactivation=confirm_deactivation,
                min_rows=min_rows,
                min_pct=min_pct,
            )
            return report
        except Exception as e:
            if not dry_run:
                # Fatal error: Roll back all company/security modifications
                db.session.rollback()
                # Record failed import run in a separate independent transaction
                self._record_failed_run(
                    report=report,
                    started_at=started_at,
                    error_msg=str(e),
                )
            raise

    def _execute_dry_run(
        self,
        csv_res,
        report: ImportReport,
        full_snapshot: bool,
        confirm_deactivation: bool,
        min_rows: int,
        min_pct: float,
    ) -> ImportReport:
        """In-memory calculation without modifying the database."""
        existing_securities = {
            (s.exchange, s.symbol, s.series): s
            for s in Security.query.filter_by(exchange=self.exchange).all()
        }
        existing_companies_by_norm = {
            c.normalized_name: c
            for c in Company.query.filter_by(country=self.country).all()
        }
        active_security_keys_in_db = {
            (s.symbol, s.series)
            for s in existing_securities.values()
            if s.is_active
        }

        simulated_new_companies = set()
        seen_keys: Set[Tuple[str, str]] = set()

        for row_dict in csv_res.rows:
            parsed, fatal_err = normalize_nse_row(row_dict)
            if fatal_err:
                report.skipped_rows += 1
                report.errors.append(fatal_err)
                continue

            if parsed.warnings:
                report.warnings.extend(parsed.warnings)

            sec_key = (self.exchange, parsed.symbol, parsed.series)
            seen_keys.add((parsed.symbol, parsed.series))

            if sec_key in existing_securities:
                sec = existing_securities[sec_key]
                # Check for updates
                if (
                    sec.isin != parsed.isin
                    or sec.listing_date != parsed.listing_date
                    or (parsed.paid_up_value is not None and sec.paid_up_value != parsed.paid_up_value)
                    or (parsed.market_lot is not None and sec.market_lot != parsed.market_lot)
                    or (parsed.face_value is not None and sec.face_value != parsed.face_value)
                    or not sec.is_active
                ):
                    report.updated_securities += 1
                else:
                    report.unchanged_securities += 1
            else:
                report.inserted_securities += 1
                if (
                    parsed.normalized_name not in existing_companies_by_norm
                    and parsed.normalized_name not in simulated_new_companies
                ):
                    report.inserted_companies += 1
                    simulated_new_companies.add(parsed.normalized_name)

        if full_snapshot:
            previous_active_count = len(active_security_keys_in_db)
            # Check safety thresholds
            if len(seen_keys) < min_rows:
                report.warnings.append(
                    f"Snapshot safety: Feed valid rows ({len(seen_keys)}) below min_rows ({min_rows})"
                )
            elif previous_active_count > 0 and (len(seen_keys) / previous_active_count) * 100 < min_pct:
                report.warnings.append(
                    f"Snapshot safety: Feed row count ({len(seen_keys)}) is less than {min_pct}% of previous active count ({previous_active_count})"
                )
            else:
                to_deactivate = len(active_security_keys_in_db - seen_keys)
                report.deactivated_securities = to_deactivate

        return report

    def _execute_live_import(
        self,
        csv_res,
        report: ImportReport,
        started_at: datetime,
        full_snapshot: bool,
        confirm_deactivation: bool,
        min_rows: int,
        min_pct: float,
    ):
        """Live transactional execution."""
        # Query existing securities for this exchange
        existing_securities = {
            (s.exchange, s.symbol, s.series): s
            for s in Security.query.filter_by(exchange=self.exchange).all()
        }
        existing_companies_by_norm = {
            c.normalized_name: c
            for c in Company.query.filter_by(country=self.country).all()
        }
        active_security_keys_in_db = {
            (s.symbol, s.series)
            for s in existing_securities.values()
            if s.is_active
        }

        seen_keys: Set[Tuple[str, str]] = set()

        for row_dict in csv_res.rows:
            parsed, fatal_err = normalize_nse_row(row_dict)
            if fatal_err:
                report.skipped_rows += 1
                report.errors.append(fatal_err)
                continue

            if parsed.warnings:
                report.warnings.extend(parsed.warnings)

            sec_key = (self.exchange, parsed.symbol, parsed.series)
            seen_keys.add((parsed.symbol, parsed.series))

            if sec_key in existing_securities:
                sec = existing_securities[sec_key]
                changed = False

                if sec.isin != parsed.isin and parsed.isin is not None:
                    sec.isin = parsed.isin
                    changed = True
                if sec.listing_date != parsed.listing_date and parsed.listing_date is not None:
                    sec.listing_date = parsed.listing_date
                    changed = True
                if parsed.paid_up_value is not None and sec.paid_up_value != parsed.paid_up_value:
                    sec.paid_up_value = parsed.paid_up_value
                    changed = True
                if parsed.market_lot is not None and sec.market_lot != parsed.market_lot:
                    sec.market_lot = parsed.market_lot
                    changed = True
                if parsed.face_value is not None and sec.face_value != parsed.face_value:
                    sec.face_value = parsed.face_value
                    changed = True
                if not sec.is_active:
                    sec.is_active = True
                    changed = True

                if changed:
                    sec.updated_at = _utc_now()
                    sec.source_updated_at = _utc_now()
                    report.updated_securities += 1
                else:
                    report.unchanged_securities += 1

            else:
                # Security does not exist -> find or create Company
                company = existing_companies_by_norm.get(parsed.normalized_name)
                if not company:
                    company = Company(
                        legal_name=parsed.legal_name,
                        display_name=parsed.display_name,
                        normalized_name=parsed.normalized_name,
                        country=self.country,
                        is_active=True,
                    )
                    db.session.add(company)
                    db.session.flush()  # assign company.id
                    existing_companies_by_norm[parsed.normalized_name] = company
                    report.inserted_companies += 1

                new_sec = Security(
                    company_id=company.id,
                    symbol=parsed.symbol,
                    exchange=self.exchange,
                    series=parsed.series,
                    isin=parsed.isin,
                    currency=self.currency,
                    asset_type="Equity",
                    listing_date=parsed.listing_date,
                    paid_up_value=parsed.paid_up_value,
                    market_lot=parsed.market_lot,
                    face_value=parsed.face_value,
                    is_active=True,
                    source=self.exchange,
                    source_updated_at=_utc_now(),
                )
                db.session.add(new_sec)
                existing_securities[sec_key] = new_sec
                report.inserted_securities += 1

        # Snapshot deactivation
        if full_snapshot:
            if not confirm_deactivation:
                raise RuntimeError(
                    "Snapshot deactivation requested but --confirm-deactivation was not provided. "
                    "Refusing to deactivate missing securities."
                )

            previous_active_count = len(active_security_keys_in_db)
            if len(seen_keys) < min_rows:
                raise RuntimeError(
                    f"Snapshot safety check failed: Valid rows in feed ({len(seen_keys)}) is less "
                    f"than required min_rows ({min_rows}). Deactivation aborted."
                )

            if previous_active_count > 0:
                pct = (len(seen_keys) / previous_active_count) * 100.0
                if pct < min_pct:
                    raise RuntimeError(
                        f"Snapshot safety check failed: Active feed percentage ({pct:.1f}%) is less "
                        f"than minimum safety threshold ({min_pct}%). Possible truncated feed. Deactivation aborted."
                    )

            # Deactivate missing securities (never deactivates Company)
            keys_to_deactivate = active_security_keys_in_db - seen_keys
            if keys_to_deactivate:
                for sym, ser in keys_to_deactivate:
                    sec = existing_securities.get((self.exchange, sym, ser))
                    if sec and sec.is_active:
                        sec.is_active = False
                        sec.updated_at = _utc_now()
                        report.deactivated_securities += 1

        # Record completed audit run
        error_summary_text = None
        if report.errors or report.warnings:
            error_summary_text = json.dumps({
                "errors": report.errors[:100],
                "warnings": report.warnings[:100],
            })

        audit_run = DataImportRun(
            source=self.exchange,
            source_file=report.source_file,
            file_sha256=report.file_sha256,
            started_at=started_at,
            completed_at=_utc_now(),
            status="completed",
            total_rows=report.total_rows,
            inserted_companies=report.inserted_companies,
            updated_companies=report.updated_companies,
            inserted_securities=report.inserted_securities,
            updated_securities=report.updated_securities,
            unchanged_securities=report.unchanged_securities,
            skipped_rows=report.skipped_rows,
            failed_rows=report.failed_rows,
            deactivated_securities=report.deactivated_securities,
            error_summary=error_summary_text,
        )
        db.session.add(audit_run)
        db.session.commit()

    def _record_failed_run(self, report: ImportReport, started_at: datetime, error_msg: str):
        """Records failed audit run in an independent transaction."""
        try:
            error_summary_json = json.dumps({
                "fatal_error": error_msg,
                "errors": report.errors[:50],
                "warnings": report.warnings[:50],
            })
            audit_run = DataImportRun(
                source=self.exchange,
                source_file=report.source_file,
                file_sha256=report.file_sha256,
                started_at=started_at,
                completed_at=_utc_now(),
                status="failed",
                total_rows=report.total_rows,
                skipped_rows=report.skipped_rows,
                failed_rows=report.failed_rows,
                error_summary=error_summary_json,
            )
            db.session.add(audit_run)
            db.session.commit()
        except Exception:
            db.session.rollback()
