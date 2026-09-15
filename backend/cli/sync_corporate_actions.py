"""
CLI Tool: Ingest Exchange Corporate Actions CSV into InvestIQ Database.

Usage:
    python -m backend.cli.sync_corporate_actions --source nse --file data/raw/nse/CA.csv
    python -m backend.cli.sync_corporate_actions --source nse --file data/raw/nse/CA.csv --dry-run
"""
import sys
import argparse
from app import create_app
from services.importer.corporate_action_importer import CorporateActionImporter


def main():
    parser = argparse.ArgumentParser(description="Synchronize exchange corporate actions into InvestIQ.")
    parser.add_argument(
        "--source",
        type=str,
        default="nse",
        choices=["nse", "nse_ca"],
        help="Corporate action dataset source (default: nse)",
    )
    parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Path to corporate actions CSV file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate actions without writing to the database",
    )

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("  InvestIQ Phase 2C: Corporate Actions Synchronizer")
        print("=" * 60)
        print(f"Source:     {args.source}")
        print(f"File:       {args.file}")
        print(f"Mode:       {'DRY-RUN (No DB writes)' if args.dry_run else 'LIVE IMPORT'}")
        print("-" * 60)

        try:
            results = CorporateActionImporter.import_csv(
                filepath=args.file,
                source="NSE_CA" if args.source.lower() == "nse" else args.source,
                dry_run=args.dry_run,
            )

            print("\nCorporate Actions Ingestion Results:")
            print(f"  Status:          {results['status'].upper()}")
            print(f"  Total Rows:      {results['total_rows']}")
            print(f"  Inserted:        {results['inserted_rows']}")
            print(f"  Updated:         {results['updated_rows']}")
            print(f"  Unchanged:       {results['unchanged_rows']}")
            print(f"  Unresolved:      {results['unresolved_rows']}")
            print(f"  Manual Review:   {results['manual_review_rows']}")
            print(f"  Failed:          {results['failed_rows']}")
            if results.get("error_summary"):
                print(f"  Errors / Notes:\n{results['error_summary']}")
            print("=" * 60)

        except Exception as e:
            print(f"\nFATAL IMPORT ERROR: {str(e)}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
