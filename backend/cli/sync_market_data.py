"""
cli/sync_market_data.py
--------------------------------------------------------------------------
CLI command for synchronizing exchange End-of-Day Bhavcopy market data.
--------------------------------------------------------------------------
"""

import argparse
import os
import sys

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app
from database.db import db
from services.importer.nse_market_importer import NseMarketImporter, MarketImportError


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize End-of-Day market data from exchange Bhavcopy ZIP archives."
    )
    parser.add_argument(
        "--source",
        choices=["nse-udiff"],
        default="nse-udiff",
        help="Market data source format (default: nse-udiff).",
    )
    parser.add_argument(
        "--file",
        help="Path to a single Bhavcopy ZIP archive.",
    )
    parser.add_argument(
        "--directory",
        help="Path to a directory containing Bhavcopy ZIP archives.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing of archives even if previously imported successfully.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate archive and price rows without persisting database writes.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail and roll back if any invalid price or unresolved security is encountered.",
    )

    args = parser.parse_args()

    # Rule: Reject ambiguous use of --file and --directory together or neither
    if args.file and args.directory:
        print("[ERROR] Cannot specify both --file and --directory. Choose one.", file=sys.stderr)
        sys.exit(1)
    if not args.file and not args.directory:
        print("[ERROR] Must specify either --file <path> or --directory <path>.", file=sys.stderr)
        sys.exit(1)

    app = create_app()
    with app.app_context():
        importer = NseMarketImporter(db.session)
        source_key = args.source.upper().replace("-", "_")

        print("=" * 65)
        print("  InvestIQ Market Data Synchronizer")
        print("=" * 65)
        print(f"Source:     {args.source}")
        if args.file:
            print(f"File:       {args.file}")
        else:
            print(f"Directory:  {args.directory}")
        print(f"Mode:       {'DRY-RUN (No DB writes)' if args.dry_run else 'LIVE IMPORT'}")
        print(f"Strictness: {'STRICT (Fail-on-error)' if args.strict else 'NORMAL'}")
        print(f"Force:      {'YES (Reprocess completed files)' if args.force else 'NO (Skip matching hashes)'}")
        print("-" * 65)

        try:
            if args.file:
                results = importer.import_bhavcopy(
                    file_path=args.file,
                    source=source_key,
                    dry_run=args.dry_run,
                    strict=args.strict,
                )

                print("\nImport Results:")
                print(f"  Status:          {results['status'].upper()}")
                print(f"  Trading Date:    {results['trading_date']}")
                print(f"  File SHA-256:    {results['file_sha256']}")
                print(f"  Total Rows:      {results['total_rows']}")
                print(f"  Inserted:        {results['inserted_rows']}")
                print(f"  Updated:         {results['updated_rows']}")
                print(f"  Unchanged:       {results['unchanged_rows']}")
                print(f"  Skipped:         {results['skipped_rows']}")
                print(f"  Unresolved:      {results['unresolved_rows']}")
                print(f"  Failed:          {results['failed_rows']}")
                print(f"  Duration:        {results['duration_seconds']}s")

                if results.get("unresolved_samples"):
                    print("\nSample Unresolved Securities:")
                    for sample in results["unresolved_samples"]:
                        print(f"  - {sample}")

                if results.get("error_samples"):
                    print("\nSample Validation Errors:")
                    for err in results["error_samples"]:
                        print(f"  - {err}")

            else:
                summary = importer.import_bhavcopy_directory(
                    directory_path=args.directory,
                    source=source_key,
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

                print("\nPer-File Details:")
                for fr in summary.get("file_results", []):
                    status_badge = fr['status'].upper()
                    date_info = f"Date: {fr.get('trading_date')}" if fr.get('trading_date') else ""
                    ins_info = f"Ins: {fr.get('inserted_rows', 0)}, Unch: {fr.get('unchanged_rows', 0)}"
                    extra = f" ({fr.get('reason')})" if fr.get('reason') else (f" [Err: {fr.get('error')}]" if fr.get('error') else "")
                    print(f"  [{status_badge:10}] {fr['filename']:<40} {date_info} {ins_info}{extra}")

            print("=" * 65)
            sys.exit(0)

        except MarketImportError as mie:
            print(f"\n[ERROR] Market import failed: {mie}", file=sys.stderr)
            print("=" * 65)
            sys.exit(1)
        except Exception as e:
            print(f"\n[FATAL] Unexpected error: {e}", file=sys.stderr)
            print("=" * 65)
            sys.exit(1)


if __name__ == "__main__":
    main()
