"""
backend/cli/seed_production.py
--------------------------------------------------------------------------
CLI Command for seeding production database with exchange equity master data.
Usage:
    python -m backend.cli.seed_production --file data/raw/nse/EQUITY_L.csv --dry-run
    python -m backend.cli.seed_production --file data/raw/nse/EQUITY_L.csv --confirm-production-write
--------------------------------------------------------------------------
"""

import argparse
import os
import sys

# Ensure backend directory is in sys.path when running from root or backend
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app
from services.importer.nse_importer import NSECompanyImporter

def parse_args():
    parser = argparse.ArgumentParser(
        description="InvestIQ Production Database Seeder"
    )
    parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to CSV listing file (e.g. data/raw/nse/EQUITY_L.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate import and report statistics without modifying the database",
    )
    parser.add_argument(
        "--full-snapshot",
        action="store_true",
        help="Treat the file as a complete snapshot of all active securities. Missing ones will be deactivated.",
    )
    parser.add_argument(
        "--confirm-production-write",
        action="store_true",
        help="Explicit confirmation required to write to the production database",
    )
    parser.add_argument(
        "--confirm-deactivation",
        action="store_true",
        help="Explicitly confirm deactivation of securities missing from a full snapshot",
    )
    return parser.parse_args()

def main():
    args = parse_args()
    file_path = os.path.abspath(args.file)

    if not os.path.exists(file_path):
        print(f"\n[ERROR] File not found: {args.file}")
        sys.exit(1)
        
    if not args.dry_run and not args.confirm_production_write:
        print("\n[ERROR] Production writes require explicit confirmation.")
        print("Use --confirm-production-write to execute a live import, or --dry-run to simulate.")
        sys.exit(1)

    # 1. Immediately fail if DATABASE_URL is missing or not Postgres
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("\n[ERROR] DATABASE_URL environment variable is missing. Seeding requires a production Postgres URL.")
        sys.exit(1)
    
    if not (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        print("\n[ERROR] Only Postgres URLs are allowed for production seeding. Refusing to seed.")
        sys.exit(1)
        
    # Prevent the app factory from failing due to missing secrets during CLI run
    # (these are safe dummy values because this script never serves HTTP traffic)
    os.environ.setdefault("SECRET_KEY", "cli-dummy-secret-key")
    os.environ.setdefault("GEMINI_API_KEY", "cli-dummy-gemini-key")
    os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost")

    print("==========================================================")
    print("  InvestIQ: Production Database Seeder")
    print("==========================================================")
    print(f"File:                 {args.file}")
    print(f"Mode:                 {'DRY-RUN (No database writes)' if args.dry_run else 'LIVE PRODUCTION SEED'}")
    print("----------------------------------------------------------")

    # DO NOT log the DATABASE_URL here
    app = create_app()
    with app.app_context():
        # Ensure we are really on Postgres and not SQLite fallback
        actual_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "sqlite" in actual_uri.lower():
            print("\n[ERROR] App context resolved to SQLite. Refusing to touch local database.")
            sys.exit(1)
            
        importer = NSECompanyImporter(exchange="NSE")
        try:
            report = importer.run(
                file_path=file_path,
                dry_run=args.dry_run,
                full_snapshot=args.full_snapshot,
                confirm_deactivation=args.confirm_deactivation,
                min_rows=100,
                min_pct=80.0,
            )
        except Exception as e:
            print(f"\n[FATAL IMPORT ERROR] {e}")
            sys.exit(1)

    print("\n==========================================================")
    print("  Import Execution Summary")
    print("==========================================================")
    print(f"File SHA-256:             {report.file_sha256}")
    print(f"Total Rows in File:       {report.total_rows}")
    print(f"Inserted Companies:       {report.inserted_companies}")
    print(f"Updated Companies:        {report.updated_companies}")
    print(f"Inserted Securities:      {report.inserted_securities}")
    print(f"Updated Securities:       {report.updated_securities}")
    print(f"Unchanged Securities:     {report.unchanged_securities}")
    print(f"Deactivated Securities:   {report.deactivated_securities}")
    print("==========================================================")

    if args.dry_run:
        print("\n[SUCCESS] Dry-run complete. Zero production database modifications made.")
    else:
        print("\n[SUCCESS] Production database seeding completed successfully.")

if __name__ == "__main__":
    main()
