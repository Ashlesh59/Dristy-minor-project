"""
Adjustment Service — Computes reproducible cumulative split and bonus price adjustments.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional

from database.db import db
from models.security import Security
from models.daily_price import DailyPrice
from models.corporate_action import CorporateAction
from models.adjusted_daily_price import AdjustedDailyPrice
from models.adjustment_run import AdjustmentRun


class AdjustmentService:
    """
    Calculates derived historical adjusted prices based on verified corporate actions.
    """

    ADJUSTMENT_METHOD = "split_bonus_ratio"
    DEFAULT_VERSION = "split_bonus_v1"

    @classmethod
    def calculate_action_factor(cls, action: CorporateAction) -> Optional[Decimal]:
        """
        Calculates the single-event price multiplier for a verified stock split or bonus.
        Returns None if action is unsupported or has invalid ratios.
        """
        if action.action_type == "stock_split":
            # ratio_from = old face value, ratio_to = new face value (e.g. 10 -> 2)
            if action.ratio_from and action.ratio_to and action.ratio_from > Decimal("0") and action.ratio_to > Decimal("0"):
                return (action.ratio_to / action.ratio_from)
        elif action.action_type == "bonus":
            # ratio_from = existing shares, ratio_to = total new shares (e.g. 1 -> 2 for 1:1 bonus)
            if action.ratio_from and action.ratio_to and action.ratio_from > Decimal("0") and action.ratio_to > Decimal("0"):
                return (action.ratio_from / action.ratio_to)
        return None

    @classmethod
    def adjust_security(
        cls,
        security_id: int,
        version: str = DEFAULT_VERSION,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Rebuilds adjusted prices for a single security.
        """
        security = Security.query.get(security_id)
        if not security:
            raise ValueError(f"Security with id={security_id} not found.")

        # 1. Fetch eligible actions (stock_split and bonus with verified or applied status)
        actions = (
            CorporateAction.query.filter_by(security_id=security_id)
            .filter(CorporateAction.action_type.in_(["stock_split", "bonus"]))
            .filter(CorporateAction.processing_status.in_(["verified", "applied"]))
            .order_by(CorporateAction.ex_date.asc(), CorporateAction.id.asc())
            .all()
        )

        # Precompute factors for each action
        action_factors = []
        for a in actions:
            factor = cls.calculate_action_factor(a)
            if factor is not None and factor > Decimal("0"):
                action_factors.append((a, factor))

        # 2. Fetch all raw daily prices sorted chronologically
        daily_prices = (
            DailyPrice.query.filter_by(security_id=security_id)
            .order_by(DailyPrice.trading_date.asc())
            .all()
        )

        adjusted_records: List[Dict[str, Any]] = []

        for dp in daily_prices:
            # A corporate action applies to all dates strictly prior to its ex_date
            cum_price_factor = Decimal("1.0")
            for a, factor in action_factors:
                if dp.trading_date < a.ex_date:
                    cum_price_factor *= factor

            cum_volume_factor = Decimal("1.0") / cum_price_factor if cum_price_factor > Decimal("0") else Decimal("1.0")

            # Round prices to 4 decimal places via ROUND_HALF_UP
            adj_open = (dp.open_price * cum_price_factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            adj_high = (dp.high_price * cum_price_factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            adj_low = (dp.low_price * cum_price_factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            adj_close = (dp.close_price * cum_price_factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

            adj_volume = None
            if dp.volume is not None:
                adj_volume = int((Decimal(dp.volume) * cum_volume_factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

            adjusted_records.append({
                "daily_price_id": dp.id,
                "security_id": security.id,
                "trading_date": dp.trading_date,
                "adjusted_open": adj_open,
                "adjusted_high": adj_high,
                "adjusted_low": adj_low,
                "adjusted_close": adj_close,
                "adjusted_volume": adj_volume,
                "cumulative_price_factor": cum_price_factor,
                "cumulative_volume_factor": cum_volume_factor,
                "adjustment_method": cls.ADJUSTMENT_METHOD,
                "adjustment_version": version,
                "calculated_at": datetime.utcnow(),
            })

        if not dry_run:
            # Delete existing records for this security and version to maintain idempotency
            AdjustedDailyPrice.query.filter_by(
                security_id=security.id,
                adjustment_version=version
            ).delete()

            for item in adjusted_records:
                adj_row = AdjustedDailyPrice(**item)
                db.session.add(adj_row)

            # Mark applied actions
            for a, _ in action_factors:
                if a.processing_status != "applied":
                    a.processing_status = "applied"
                    a.updated_at = datetime.utcnow()

            db.session.commit()

        return {
            "security_id": security.id,
            "symbol": security.symbol,
            "actions_applied": len(action_factors),
            "prices_processed": len(adjusted_records),
            "status": "dry_run" if dry_run else "completed",
        }

    @classmethod
    def rebuild_all_securities(
        cls,
        version: str = DEFAULT_VERSION,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Rebuilds adjusted prices for all active securities with per-security transaction isolation.
        """
        started_at = datetime.utcnow()
        securities = Security.query.filter_by(is_active=True).all()

        stats = {
            "status": "dry_run" if dry_run else "pending",
            "adjustment_version": version,
            "securities_processed": 0,
            "prices_processed": 0,
            "actions_applied": 0,
            "manual_review_actions": 0,
            "failed_securities": 0,
            "error_summary": None,
        }

        # Count total manual review actions across system
        manual_rev_count = CorporateAction.query.filter_by(processing_status="manual_review").count()
        stats["manual_review_actions"] = manual_rev_count

        errors = []

        for sec in securities:
            try:
                res = cls.adjust_security(sec.id, version=version, dry_run=dry_run)
                stats["securities_processed"] += 1
                stats["prices_processed"] += res["prices_processed"]
                stats["actions_applied"] += res["actions_applied"]
            except Exception as exc:
                if not dry_run:
                    db.session.rollback()
                stats["failed_securities"] += 1
                err_msg = f"Failed security {sec.symbol} (ID: {sec.id}): {str(exc)}"
                errors.append(err_msg)

        if errors:
            stats["error_summary"] = "\n".join(errors[:20])

        stats["status"] = "dry_run" if dry_run else ("completed" if stats["failed_securities"] == 0 else "partial_failure")

        # Record audit run
        if not dry_run:
            completed_run = AdjustmentRun(
                security_id=None,
                adjustment_version=version,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                status=stats["status"],
                securities_processed=stats["securities_processed"],
                prices_processed=stats["prices_processed"],
                actions_applied=stats["actions_applied"],
                manual_review_actions=stats["manual_review_actions"],
                failed_securities=stats["failed_securities"],
                error_summary=stats["error_summary"],
            )
            db.session.add(completed_run)
            db.session.commit()

        stats["completed_at"] = datetime.utcnow().isoformat()
        return stats
