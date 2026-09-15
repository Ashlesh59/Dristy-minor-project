"""
Corporate Action Importer Service — Ingests exchange corporate actions and associates them with Securities.
"""
import os
import csv
import io
import hashlib
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple

from database.db import db
from models.security import Security
from models.corporate_action import CorporateAction
from models.corporate_action_import_run import CorporateActionImportRun
from services.importer.ca_parser import CorporateActionParser


class CorporateActionImporter:
    """
    Ingests and audits NSE Corporate Action CSV files.
    """

    @staticmethod
    def _compute_sha256(filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest().upper()

    @classmethod
    def import_csv(
        cls,
        filepath: str,
        source: str = "NSE_CA",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Imports corporate actions from a local CSV file.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Corporate actions file not found: {filepath}")

        file_sha256 = cls._compute_sha256(filepath)
        safe_filename = os.path.basename(filepath)
        started_at = datetime.utcnow()

        stats = {
            "status": "dry_run" if dry_run else "pending",
            "total_rows": 0,
            "inserted_rows": 0,
            "updated_rows": 0,
            "unchanged_rows": 0,
            "skipped_rows": 0,
            "unresolved_rows": 0,
            "manual_review_rows": 0,
            "rejected_rows": 0,
            "failed_rows": 0,
            "error_summary": None,
        }

        # Preload active securities for resolution
        active_securities = Security.query.filter_by(is_active=True).all()
        isin_map = {s.isin: s for s in active_securities if s.isin}
        sym_series_map = {(s.exchange.upper(), s.symbol.upper(), s.series.upper()): s for s in active_securities}
        
        # Build symbol to list of securities map
        symbol_map: Dict[Tuple[str, str], List[Security]] = {}
        for s in active_securities:
            key = (s.exchange.upper(), s.symbol.upper())
            symbol_map.setdefault(key, []).append(s)

        parsed_actions: List[Dict[str, Any]] = []
        errors: List[str] = []

        try:
            with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    raise ValueError("Corporate action CSV is empty or missing header row.")

                # Normalize headers
                header_map = {}
                for col in reader.fieldnames:
                    clean_col = col.strip().upper().replace(" ", "_")
                    header_map[col] = clean_col

                for row_idx, raw_row in enumerate(reader, start=2):
                    stats["total_rows"] += 1
                    row = {header_map[k]: (v.strip() if v else "") for k, v in raw_row.items() if k in header_map}

                    raw_symbol = row.get("SYMBOL", "").upper()
                    raw_series = row.get("SERIES", "EQ").upper() or "EQ"
                    raw_isin = row.get("ISIN", "").upper()
                    raw_purpose = row.get("PURPOSE") or row.get("SUBJECT") or ""
                    raw_ex_date = row.get("EX_DATE") or row.get("EX-DATE")
                    raw_rec_date = row.get("RECORD_DATE") or row.get("RECORD-DATE")
                    raw_ann_date = row.get("ANNOUNCEMENT_DATE") or row.get("BC_START_DATE")

                    # Validate ex_date
                    ex_date = CorporateActionParser.parse_date(raw_ex_date)
                    if not ex_date:
                        stats["failed_rows"] += 1
                        errors.append(f"Row {row_idx}: Missing or invalid EX_DATE '{raw_ex_date}' for {raw_symbol}")
                        continue

                    record_date = CorporateActionParser.parse_date(raw_rec_date)
                    announcement_date = CorporateActionParser.parse_date(raw_ann_date)

                    # Resolve Security
                    security: Optional[Security] = None
                    if raw_isin and raw_isin in isin_map:
                        security = isin_map[raw_isin]
                    elif ("NSE", raw_symbol, raw_series) in sym_series_map:
                        security = sym_series_map[("NSE", raw_symbol, raw_series)]
                    elif ("NSE", raw_symbol) in symbol_map and len(symbol_map[("NSE", raw_symbol)]) == 1:
                        security = symbol_map[("NSE", raw_symbol)][0]

                    if not security:
                        stats["unresolved_rows"] += 1
                        errors.append(f"Row {row_idx}: Unresolved security for SYMBOL='{raw_symbol}', ISIN='{raw_isin}'")
                        continue

                    # Parse Purpose
                    parsed_purpose = CorporateActionParser.parse_purpose(raw_purpose)
                    if parsed_purpose["processing_status"] == "manual_review":
                        stats["manual_review_rows"] += 1

                    # Generate deterministic source_event_key
                    event_hash_input = f"{security.id}_{ex_date.isoformat()}_{raw_purpose}"
                    event_key = hashlib.sha256(event_hash_input.encode("utf-8")).hexdigest()[:64]

                    parsed_actions.append({
                        "security_id": security.id,
                        "action_type": parsed_purpose["action_type"],
                        "announcement_date": announcement_date,
                        "ex_date": ex_date,
                        "record_date": record_date,
                        "action_description": raw_purpose,
                        "ratio_from": parsed_purpose["ratio_from"],
                        "ratio_to": parsed_purpose["ratio_to"],
                        "cash_amount": parsed_purpose["cash_amount"],
                        "currency": "INR",
                        "source": source,
                        "source_event_key": event_key,
                        "source_file_sha256": file_sha256,
                        "processing_status": parsed_purpose["processing_status"],
                        "review_reason": parsed_purpose["review_reason"],
                    })

            # Process database upserts if not dry-run
            if not dry_run:
                for item in parsed_actions:
                    existing = CorporateAction.query.filter_by(
                        source=item["source"],
                        source_event_key=item["source_event_key"]
                    ).first()

                    if existing is None:
                        action = CorporateAction(**item)
                        db.session.add(action)
                        stats["inserted_rows"] += 1
                    else:
                        # Check if any field changed
                        changed = False
                        for field, val in item.items():
                            curr_val = getattr(existing, field)
                            if isinstance(curr_val, Decimal) and isinstance(val, Decimal):
                                if curr_val != val:
                                    setattr(existing, field, val)
                                    changed = True
                            elif curr_val != val:
                                setattr(existing, field, val)
                                changed = True
                        if changed:
                            existing.updated_at = datetime.utcnow()
                            stats["updated_rows"] += 1
                        else:
                            stats["unchanged_rows"] += 1

                db.session.commit()
                stats["status"] = "completed"
            else:
                stats["status"] = "dry_run"
                stats["inserted_rows"] = len(parsed_actions)

        except Exception as exc:
            db.session.rollback()
            stats["status"] = "failed"
            stats["failed_rows"] += 1
            errors.append(f"Fatal error: {str(exc)}")
            stats["error_summary"] = "\n".join(errors[:20])

            # Audit failure in a clean transaction
            if not dry_run:
                try:
                    failed_run = CorporateActionImportRun(
                        source=source,
                        source_file=safe_filename,
                        file_sha256=file_sha256,
                        started_at=started_at,
                        completed_at=datetime.utcnow(),
                        status="failed",
                        total_rows=stats["total_rows"],
                        inserted_rows=0,
                        updated_rows=0,
                        unchanged_rows=0,
                        skipped_rows=stats["skipped_rows"],
                        unresolved_rows=stats["unresolved_rows"],
                        manual_review_rows=stats["manual_review_rows"],
                        rejected_rows=stats["rejected_rows"],
                        failed_rows=stats["failed_rows"],
                        error_summary=stats["error_summary"],
                    )
                    db.session.add(failed_run)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            raise

        if errors:
            stats["error_summary"] = "\n".join(errors[:20])

        # Record completed audit run
        if not dry_run:
            completed_run = CorporateActionImportRun(
                source=source,
                source_file=safe_filename,
                file_sha256=file_sha256,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                status=stats["status"],
                total_rows=stats["total_rows"],
                inserted_rows=stats["inserted_rows"],
                updated_rows=stats["updated_rows"],
                unchanged_rows=stats["unchanged_rows"],
                skipped_rows=stats["skipped_rows"],
                unresolved_rows=stats["unresolved_rows"],
                manual_review_rows=stats["manual_review_rows"],
                rejected_rows=stats["rejected_rows"],
                failed_rows=stats["failed_rows"],
                error_summary=stats["error_summary"],
            )
            db.session.add(completed_run)
            db.session.commit()

        stats["completed_at"] = datetime.utcnow().isoformat()
        stats["file_sha256"] = file_sha256
        return stats
