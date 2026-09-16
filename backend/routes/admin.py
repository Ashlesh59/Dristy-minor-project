"""
routes/admin.py
--------------------------------------------------------------------------
Administrative and diagnostic endpoints for Neon DB status and market data sync.
--------------------------------------------------------------------------
"""

import os
import tempfile
import urllib.request
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app

from database.db import db
from models.company import Company
from models.security import Security
from models.daily_price import DailyPrice
from models.market_data_import_run import MarketDataImportRun
from models.research import Research
from routes.auth import get_current_user
from services.importer.nse_market_importer import NseMarketImporter

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

NSE_ARCHIVE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}

TARGET_BENCHMARK_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "M&M"]


def _check_admin_auth():
    """Verify session user or administrative header."""
    user = get_current_user()
    if user is not None:
        return True, user
    # Fallback for automation/CLI with SECRET_KEY verification
    admin_secret = request.headers.get("X-Admin-Key")
    configured_secret = current_app.config.get("SECRET_KEY")
    if admin_secret and configured_secret and admin_secret == configured_secret:
        return True, None
    return False, None


@admin_bp.route("/diagnose", methods=["GET"])
def diagnose():
    """
    Returns database engine status, entity counts, and verification of key symbols.
    Never exposes DATABASE_URL or sensitive credentials.
    """
    is_auth, _ = _check_admin_auth()
    if not is_auth:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    try:
        engine_name = db.engine.name
        is_postgres = "postgres" in engine_name.lower()

        # Counts
        companies_count = db.session.query(Company).count()
        securities_count = db.session.query(Security).count()
        daily_prices_count = db.session.query(DailyPrice).count()
        import_runs_count = db.session.query(MarketDataImportRun).count()
        research_count = db.session.query(Research).count()

        # Research sample
        recent_research = []
        for r in (
            db.session.query(Research)
            .order_by(Research.created_at.desc())
            .limit(10)
            .all()
        ):
            recent_research.append({
                "id": r.id,
                "company_name": r.company_name,
                "ticker_symbol": r.ticker_symbol,
                "security_id": r.security_id or (r.security.id if r.security else None),
                "has_valid_security_id": bool(r.security_id or r.security),
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        # Key securities inspection
        key_securities = []
        for sym in TARGET_BENCHMARK_SYMBOLS:
            sec = (
                db.session.query(Security)
                .filter(Security.symbol == sym, Security.is_active == True)
                .first()
            )
            if sec:
                price_count = (
                    db.session.query(DailyPrice)
                    .filter(DailyPrice.security_id == sec.id)
                    .count()
                )
                latest_price = (
                    db.session.query(DailyPrice)
                    .filter(DailyPrice.security_id == sec.id)
                    .order_by(DailyPrice.trading_date.desc())
                    .first()
                )
                key_securities.append({
                    "symbol": sym,
                    "isin": sec.isin,
                    "security_id": sec.id,
                    "price_count": price_count,
                    "latest_trading_date": str(latest_price.trading_date) if latest_price else None,
                    "latest_close": float(latest_price.close_price) if latest_price and latest_price.close_price is not None else None,
                })
            else:
                key_securities.append({
                    "symbol": sym,
                    "isin": None,
                    "security_id": None,
                    "price_count": 0,
                    "latest_trading_date": None,
                    "latest_close": None,
                })

        return jsonify({
            "success": True,
            "database": {
                "engine": engine_name,
                "is_postgresql": is_postgres,
            },
            "counts": {
                "companies": companies_count,
                "securities": securities_count,
                "daily_prices": daily_prices_count,
                "market_data_import_runs": import_runs_count,
                "research_records": research_count,
            },
            "key_securities": key_securities,
            "recent_research": recent_research,
        }), 200

    except Exception as e:
        current_app.logger.error("Admin diagnose error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 500


@admin_bp.route("/market-data/sync", methods=["POST"])
def sync_market_data():
    """
    Downloads and imports official NSE UDiFF Bhavcopy archives into Postgres.
    Enforces Postgres-only, supports dry-run, requires confirm_production_write for writes.
    """
    is_auth, _ = _check_admin_auth()
    if not is_auth:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    dry_run = data.get("dry_run", True)
    confirm_write = data.get("confirm_production_write", False)
    dates = data.get("dates", [])
    strict = data.get("strict", False)

    # Safety checks
    if not dry_run and not confirm_write:
        return jsonify({
            "success": False,
            "message": "Live database write requires confirm_production_write: true."
        }), 400

    engine_name = db.engine.name
    if "postgres" not in engine_name.lower():
        return jsonify({
            "success": False,
            "message": f"Production market data sync refused on non-Postgres engine: {engine_name}."
        }), 400

    # Auto-generate latest 35 candidate dates if none supplied
    if not dates:
        start_dt = datetime.utcnow().date()
        for i in range(70):
            cur = start_dt - timedelta(days=i)
            if cur.weekday() < 5:  # Mon-Fri
                dates.append(cur.strftime("%Y%m%d"))
            if len(dates) >= 40:
                break

    importer = NseMarketImporter(db.session)
    results = {
        "mode": "DRY-RUN (No DB modifications)" if dry_run else "LIVE WRITE",
        "dates_attempted": len(dates),
        "successful_files": 0,
        "failed_files": 0,
        "skipped_not_found": 0,
        "total_inserted_rows": 0,
        "total_updated_rows": 0,
        "total_unchanged_rows": 0,
        "file_details": [],
    }

    with tempfile.TemporaryDirectory(prefix="bhavcopy_sync_") as tmpdir:
        for date_str in dates:
            url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
            zip_dest = os.path.join(tmpdir, f"BhavCopy_{date_str}.zip")

            req = urllib.request.Request(url, headers=NSE_ARCHIVE_HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    zip_bytes = resp.read()
                    if len(zip_bytes) < 1000:
                        results["skipped_not_found"] += 1
                        continue
                    with open(zip_dest, "wb") as fz:
                        fz.write(zip_bytes)
            except Exception:
                # Market holiday or weekend or not published yet
                results["skipped_not_found"] += 1
                continue

            try:
                import_res = importer.import_bhavcopy(
                    file_path=zip_dest,
                    source="NSE_UDIFF",
                    dry_run=dry_run,
                    strict=strict,
                )
                results["successful_files"] += 1
                results["total_inserted_rows"] += import_res.get("inserted_rows", 0)
                results["total_updated_rows"] += import_res.get("updated_rows", 0)
                results["total_unchanged_rows"] += import_res.get("unchanged_rows", 0)
                results["file_details"].append({
                    "date": date_str,
                    "trading_date": str(import_res.get("trading_date")),
                    "status": import_res.get("status"),
                    "inserted": import_res.get("inserted_rows", 0),
                    "updated": import_res.get("updated_rows", 0),
                    "unchanged": import_res.get("unchanged_rows", 0),
                    "unresolved": import_res.get("unresolved_rows", 0),
                    "duration_seconds": import_res.get("duration_seconds", 0),
                })
            except Exception as e:
                results["failed_files"] += 1
                results["file_details"].append({
                    "date": date_str,
                    "status": "failed",
                    "error": str(e),
                })
                if strict:
                    return jsonify({
                        "success": False,
                        "message": f"Strict import halted on {date_str}: {e}",
                        "partial_results": results
                    }), 500

    # Get final count
    final_price_count = db.session.query(DailyPrice).count()
    results["final_daily_prices_count"] = final_price_count
    results["success"] = True

    return jsonify(results), 200
