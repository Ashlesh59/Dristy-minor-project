"""
backend/cli/seed_production_market.py
--------------------------------------------------------------------------
CLI command for seeding production database with official NSE CM-UDiFF Bhavcopy market data.
Requires explicit PostgreSQL/Neon connection. Refuses SQLite.
Supports dry-run and requires confirmation for live database writes.
--------------------------------------------------------------------------
"""

import argparse
import os
import sys

# Ensure backend root is on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app
from database.db import db
from services.importer.nse_market_importer import NseMarketImporter, MarketImportError


def parse_args():
    parser = argparse.ArgumentParser(
        description="InvestIQ Production Market Data Seeder (NSE CM-UDiFF)"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Path to a single Bhavcopy ZIP file",
    )
    parser.add_argument(
        "--directory",
        type=str,
        default="data/raw/nse/bhavcopy",
        help="Path to directory containing Bhavcopy ZIP files (default: data/raw/nse/bhavcopy)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate import without committing database changes",
    )
    parser.add_argument(
        "--confirm-production-write",
        action="store_true",
        help="Explicit confirmation required to write to production database",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail entire import if any invalid row or unresolved security is encountered",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing even if matching SHA-256 exists in audit runs",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not args.dry_run and not args.confirm_production_write:
        print("\n[ERROR] Production writes require explicit confirmation.")
        print("Use --confirm-production-write to execute live import, or --dry-run to simulate.")
        sys.exit(1)

    # 1. Enforce DATABASE_URL exists and is Postgres
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if not db_url:
        print("\n[ERROR] DATABASE_URL / POSTGRES_URL environment variable is missing.")
        print("Production market data seeding requires a valid PostgreSQL connection string.")
        sys.exit(1)

    if not (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        print("\n[ERROR] Only PostgreSQL connection strings are permitted for production seeding.")
        print("Refusing to seed non-PostgreSQL database.")
        sys.exit(1)

    # Prevent app factory failure on missing API secrets during CLI run
    os.environ.setdefault("SECRET_KEY", "cli-dummy-secret-key")
    os.environ.setdefault("GEMINI_API_KEY", "cli-dummy-gemini-key")
    os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost")

    print("=" * 65)
    print("  InvestIQ: Production Market Data Seeder (NSE UDiFF)")
    print("=" * 65)
    print(f"Target:       PostgreSQL (Neon / Production)")
    print(f"Mode:         {'DRY-RUN (No database modifications)' if args.dry_run else 'LIVE PRODUCTION SEED'}")
    if args.file:
        print(f"File:         {args.file}")
    else:
        print(f"Directory:    {args.directory}")
    print(f"Strictness:   {'STRICT' if args.strict else 'NORMAL'}")
    print(f"Force:        {'YES' if args.force else 'NO'}")
    print("-" * 65)

    app = create_app()
    with app.app_context():
        # Ensure we are really on Postgres and not SQLite fallback
        actual_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if "sqlite" in actual_uri.lower():
            print("\n[ERROR] App context resolved to SQLite. Refusing to touch local database.")
            sys.exit(1)

        importer = NseMarketImporter(db.session)

        try:
            if args.file:
                file_path = os.path.abspath(args.file)
                if not os.path.exists(file_path):
                    print(f"\n[ERROR] File not found: {file_path}")
                    sys.exit(1)

                res = importer.import_bhavcopy(
                    file_path=file_path,
                    source="NSE_UDIFF",
                    dry_run=args.dry_run,
                    strict=args.strict,
                )
                print("\nSingle File Import Summary:")
                print(f"  Status:          {res['status'].upper()}")
                print(f"  Trading Date:    {res['trading_date']}")
                print(f"  Total Rows:      {res['total_rows']}")
                print(f"  Inserted Rows:   {res['inserted_rows']}")
                print(f"  Updated Rows:    {res['updated_rows']}")
                print(f"  Unchanged Rows:  {res['unchanged_rows']}")
                print(f"  Duration:        {res['duration_seconds']}s")
            else:
                dir_path = os.path.abspath(args.directory)
                if not os.path.exists(dir_path):
                    print(f"\n[ERROR] Directory not found: {dir_path}")
                    sys.exit(1)

                summary = importer.import_bhavcopy_directory(
                    directory_path=dir_path,
                    source="NSE_UDIFF",
                    dry_run=args.dry_run,
                    strict=args.strict,
                    force=args.force,
                )
                print("\nDirectory Import Summary:")
                print(f"  Status:          {summary['status'].upper()}")
                print(f"  Total Files:     {summary['total_files']}")
                print(f"  Processed Files: {summary['processed_files']}")
                print(f"  Skipped Files:   {summary['skipped_files']}")
                print(f"  Failed Files:    {summary['failed_files']}")
                print(f"  Total Rows:      {summary['total_rows']}")
                print(f"  Inserted Rows:   {summary['inserted_rows']}")
                print(f"  Updated Rows:    {summary['updated_rows']}")
                print(f"  Unchanged Rows:  {summary['unchanged_rows']}")
                print(f"  Unresolved Rows: {summary['unresolved_rows']}")
                print(f"  Failed Rows:     {summary['failed_rows']}")

        except MarketImportError as mie:
            print(f"\n[FATAL IMPORT ERROR] {mie}")
            sys.exit(1)
        except Exception as e:
            print(f"\n[UNEXPECTED ERROR] {e}")
            sys.exit(1)

    print("=" * 65)
    if args.dry_run:
        print("[SUCCESS] Dry-run complete. Zero production database modifications made.")
    else:
        print("[SUCCESS] Production market data seeding completed successfully.")


if __name__ == "__main__":
    main()
