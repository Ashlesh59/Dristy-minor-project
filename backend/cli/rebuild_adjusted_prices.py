"""
CLI Tool: Rebuild Historical Split and Bonus Adjusted Prices.

Usage:
    python -m backend.cli.rebuild_adjusted_prices --security-id 1 --version split_bonus_v1 --dry-run
    python -m backend.cli.rebuild_adjusted_prices --all --version split_bonus_v1
"""
import sys
import argparse
from app import create_app
from services.adjustment_service import AdjustmentService


def main():
    parser = argparse.ArgumentParser(description="Rebuild split and bonus adjusted historical prices.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--security-id",
        type=int,
        help="Specific Security ID to calculate adjustments for",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Rebuild adjustments for all active securities in database",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="split_bonus_v1",
        help="Adjustment calculation version identifier (default: split_bonus_v1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate adjustments without saving to adjusted_daily_prices table",
    )

    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("  InvestIQ Phase 2C: Adjusted Price Rebuild Engine")
        print("=" * 60)
        print(f"Target:     {'Security ID ' + str(args.security_id) if args.security_id else 'ALL Active Securities'}")
        print(f"Version:    {args.version}")
        print(f"Mode:       {'DRY-RUN (No DB writes)' if args.dry_run else 'LIVE REBUILD'}")
        print("-" * 60)

        try:
            if args.security_id:
                res = AdjustmentService.adjust_security(
                    security_id=args.security_id,
                    version=args.version,
                    dry_run=args.dry_run,
                )
                print("\nSingle Security Adjustment Results:")
                print(f"  Security ID:      {res['security_id']} ({res['symbol']})")
                print(f"  Actions Applied:  {res['actions_applied']}")
                print(f"  Prices Adjusted:  {res['prices_processed']}")
                print(f"  Status:           {res['status'].upper()}")
            else:
                res = AdjustmentService.rebuild_all_securities(
                    version=args.version,
                    dry_run=args.dry_run,
                )
                print("\nBatch Adjustment Results:")
                print(f"  Status:               {res['status'].upper()}")
                print(f"  Securities Processed: {res['securities_processed']}")
                print(f"  Prices Adjusted:      {res['prices_processed']}")
                print(f"  Actions Applied:      {res['actions_applied']}")
                print(f"  Manual Review Items:  {res['manual_review_actions']}")
                print(f"  Failed Securities:    {res['failed_securities']}")
                if res.get("error_summary"):
                    print(f"  Errors / Notes:\n{res['error_summary']}")
            print("=" * 60)

        except Exception as e:
            print(f"\nFATAL REBUILD ERROR: {str(e)}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
