"""
backend/cli/sync_companies.py
--------------------------------------------------------------------------
CLI Command for importing and synchronizing exchange equity master data.
Usage:
    python -m backend.cli.sync_companies --source nse --file data/raw/nse/EQUITY_L.csv
    python -m backend.cli.sync_companies --source nse --file data/raw/nse/EQUITY_L.csv --dry-run
    python -m backend.cli.sync_companies --source nse --file data/raw/nse/EQUITY_L.csv --full-snapshot --confirm-deactivation
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
        description="InvestIQ Exchange Company & Security Master Synchronizer"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="nse",
        choices=["nse"],
        help="Market data source (default: nse)",
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
        help="Mark absent securities as inactive (requires --confirm-deactivation)",
    )
    parser.add_argument(
        "--confirm-deactivation",
        action="store_true",
        help="Explicit confirmation required to deactivate absent securities in snapshot mode",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=100,
        help="Minimum valid rows required for snapshot deactivation safety (default: 100)",
    )
    parser.add_argument(
        "--min-pct",
        type=float,
        default=80.0,
        help="Minimum active percentage required for snapshot deactivation safety (default: 80.0)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    file_path = os.path.abspath(args.file)

    if not os.path.exists(file_path):
        print(f"\n[ERROR] File not found: {args.file}")
        sys.exit(1)

    print("==========================================================")
    print("  InvestIQ: Exchange Master Importer")
    print("==========================================================")
    print(f"Source:               {args.source.upper()}")
    print(f"File:                 {args.file}")
    print(f"Mode:                 {'DRY-RUN (No database writes)' if args.dry_run else 'LIVE IMPORT'}")
    print(f"Full Snapshot:        {args.full_snapshot}")
    print(f"Confirm Deactivation: {args.confirm_deactivation}")
    print("----------------------------------------------------------")

    app = create_app()
    with app.app_context():
        importer = NSECompanyImporter(exchange=args.source.upper())
        try:
            report = importer.run(
                file_path=file_path,
                dry_run=args.dry_run,
                full_snapshot=args.full_snapshot,
                confirm_deactivation=args.confirm_deactivation,
                min_rows=args.min_rows,
                min_pct=args.min_pct,
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
    print(f"Skipped Rows (Invalid):   {report.skipped_rows}")
    print(f"Failed Rows:              {report.failed_rows}")
    print(f"Deactivated Securities:   {report.deactivated_securities}")
    print(f"Warnings Logged:          {len(report.warnings)}")
    print(f"Errors Logged:            {len(report.errors)}")
    print("==========================================================")

    if report.warnings:
        print("\nSample Warnings (first 5):")
        for w in report.warnings[:5]:
            print(f"  - {w}")

    if report.errors:
        print("\nSample Errors (first 5):")
        for err in report.errors[:5]:
            print(f"  - {err}")

    if args.dry_run:
        print("\n[SUCCESS] Dry-run complete. Zero database modifications made.")
    else:
        print("\n[SUCCESS] Master data synchronization completed successfully.")


if __name__ == "__main__":
    main()
