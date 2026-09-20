"""
services/market_data_service.py
--------------------------------------------------------------------------
Business logic service for resolving and querying stored End-of-Day (EOD)
DailyPrice records, calculating metrics, and assembling time-series history.
--------------------------------------------------------------------------
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import desc, asc

from database.db import db
from models.security import Security
from models.daily_price import DailyPrice
from models.adjusted_daily_price import AdjustedDailyPrice
from models.corporate_action import CorporateAction


class MarketDataServiceError(Exception):
    """Base error for market data service operations."""
    pass


class SecurityNotFoundError(MarketDataServiceError):
    """Raised when a security is missing or inactive."""
    pass


class InvalidRangeError(MarketDataServiceError):
    """Raised when range or date parameters are invalid."""
    pass


# Range mappings: key -> timedelta approximation
RANGE_DAYS_MAP = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "3y": 365 * 3,
    "5y": 365 * 5,
    "max": None,
}


def _dec_str(val, decimals: int = 2) -> Optional[str]:
    """
    Safely serializes a Decimal / Numeric database value to standard base-10 string
    without converting through binary float.
    """
    if val is None:
        return None
    d = Decimal(str(val))
    quant = Decimal("0." + "0" * decimals) if decimals > 0 else Decimal("1")
    return str(d.quantize(quant))


class MarketDataService:
    """
    Dedicated service for retrieving and computing stored market data.
    """

    def __init__(self, db_session=None):
        self.session = db_session or db.session

    @classmethod
    def get_security_or_fail(cls, security_id: int) -> Security:
        """
        Resolves an active Security record or raises SecurityNotFoundError.
        """
        security = Security.query.filter_by(id=security_id, is_active=True).first()
        if not security:
            raise SecurityNotFoundError(f"Security ID {security_id} not found or is inactive.")
        if security.company and not security.company.is_active:
            raise SecurityNotFoundError(f"Security ID {security_id} belongs to an inactive company.")
        return security

    @classmethod
    def get_latest_market_data(cls, security_id: int) -> Dict[str, Any]:
        """
        Retrieves the most recent stored DailyPrice record for a security,
        calculates absolute and percentage change safely, and formats metadata.
        """
        security = cls.get_security_or_fail(security_id)

        # 1. Fetch latest daily price record
        latest_price = (
            DailyPrice.query.filter_by(security_id=security.id)
            .order_by(desc(DailyPrice.trading_date))
            .first()
        )

        security_payload = {
            "security_id": security.id,
            "company_id": security.company_id,
            "company_name": security.company.display_name if security.company else security.symbol,
            "symbol": security.symbol,
            "exchange": security.exchange,
            "series": security.series,
            "isin": security.isin,
            "currency": security.currency or "INR",
        }

        if not latest_price:
            from flask import current_app
            is_testing = False
            try:
                is_testing = bool(
                    current_app
                    and current_app.config.get("TESTING", False)
                    and not current_app.config.get("ENABLE_LIVE_FALLBACK", False)
                )
            except Exception:
                pass

            if not is_testing:
                try:
                    from services.financial_service import get_stock_quote
                    live_q = get_stock_quote(security.symbol)
                    if live_q and live_q.get("price"):
                        price_val = str(live_q.get("price"))
                        chg_val = str(live_q.get("change") or "0.00")
                        raw_pct = str(live_q.get("change_percent") or "0.00%").replace("%", "").replace("+", "").strip()
                        curr = live_q.get("currency") or security.currency or "INR"
                        security_payload["currency"] = curr
                        
                        trading_dt = live_q.get("latest_trading_day") or datetime.utcnow().strftime("%Y-%m-%d")
                        market_data_payload = {
                            "date": trading_dt,
                            "trading_date": trading_dt,
                            "currency": curr,
                            "open": str(live_q.get("open") or price_val),
                            "high": str(live_q.get("high") or price_val),
                            "low": str(live_q.get("low") or price_val),
                            "close": price_val,
                            "last_price": price_val,
                            "previous_close": str(live_q.get("previous_close") or price_val),
                            "change": chg_val,
                            "change_percent": raw_pct,
                            "vwap": price_val,
                            "volume": int(live_q.get("volume") or 0),
                            "turnover": None,
                            "trade_count": None,
                            "deliverable_quantity": None,
                            "deliverable_percentage": None,
                            "week_52_high": str(live_q.get("high") or price_val),
                            "week_52_low": str(live_q.get("low") or price_val),
                            "sma_20": None,
                            "sma_50": None,
                            "average_volume_30": None,
                            "volatility": None,
                            "coverage": None,
                            "returns": {
                                "return_1m": None,
                                "return_3m": None,
                                "return_6m": None,
                                "return_1y": None,
                            },
                            "source": live_q.get("source") or "Live Market Feed",
                            "is_adjusted": False,
                        }
                        return {
                            "success": True,
                            "security": security_payload,
                            "market_data": market_data_payload,
                            "summary": market_data_payload,
                            "freshness": {
                                "data_type": "real_time",
                                "last_trading_date": live_q.get("latest_trading_day"),
                                "is_real_time": True,
                            },
                        }
                except Exception as e:
                    pass

            return {
                "success": True,
                "security": security_payload,
                "market_data": None,
                "freshness": {
                    "data_type": "end_of_day",
                    "last_trading_date": None,
                    "is_real_time": False,
                    "message": "No price data has been imported for this security yet.",
                },
            }

        # 2. Resolve previous close
        previous_close = latest_price.previous_close

        if previous_close is None:
            # Query immediately preceding daily price
            prev_record = (
                DailyPrice.query.filter(
                    DailyPrice.security_id == security.id,
                    DailyPrice.trading_date < latest_price.trading_date,
                )
                .order_by(desc(DailyPrice.trading_date))
                .first()
            )
            if prev_record:
                previous_close = prev_record.close_price

        # 3. Calculate daily price change and change percentage
        change = None
        change_percent = None

        if latest_price.close_price is not None and previous_close is not None:
            change = latest_price.close_price - previous_close
            # Division by zero protection
            if previous_close > Decimal("0"):
                change_percent = ((change / previous_close) * Decimal("100")).quantize(
                    Decimal("0.0001")
                )

        # 4. Calculate 52-week range and period returns safely
        metrics = cls._compute_market_metrics(security.id, latest_price)

        market_data_payload = {
            "date": latest_price.trading_date.isoformat(),
            "trading_date": latest_price.trading_date.isoformat(),
            "currency": security_payload["currency"],
            "open": _dec_str(latest_price.open_price, 2),
            "high": _dec_str(latest_price.high_price, 2),
            "low": _dec_str(latest_price.low_price, 2),
            "close": _dec_str(latest_price.close_price, 2),
            "last_price": _dec_str(latest_price.last_price, 2),
            "previous_close": _dec_str(previous_close, 2),
            "change": _dec_str(change, 2),
            "change_percent": _dec_str(change_percent, 4),
            "vwap": _dec_str(latest_price.vwap, 2),
            "volume": latest_price.volume,
            "turnover": _dec_str(latest_price.turnover, 2),
            "trade_count": latest_price.trade_count,
            "deliverable_quantity": latest_price.deliverable_quantity,
            "deliverable_percentage": _dec_str(latest_price.deliverable_percentage, 2),
            "week_52_high": metrics["week_52_high"],
            "week_52_low": metrics["week_52_low"],
            "sma_20": metrics.get("sma_20"),
            "sma_50": metrics.get("sma_50"),
            "average_volume_30": metrics.get("average_volume_30"),
            "volatility": metrics.get("volatility"),
            "coverage": metrics.get("coverage"),
            "returns": metrics["returns"],
            "source": latest_price.source,
            "is_adjusted": latest_price.is_adjusted,
        }

        return {
            "success": True,
            "security": security_payload,
            "market_data": market_data_payload,
            "summary": market_data_payload,
            "freshness": {
                "data_type": "end_of_day",
                "last_trading_date": latest_price.trading_date.isoformat(),
                "is_real_time": False,
            },
        }

    @classmethod
    def _compute_market_metrics(cls, security_id: int, latest_price: DailyPrice) -> Dict[str, Any]:
        """
        Calculates 52-week high/low and 1M/3M/6M/1Y returns Decimal-safely
        using stored chronological DailyPrice records.
        """
        if not latest_price or latest_price.close_price is None:
            return {
                "week_52_high": None,
                "week_52_low": None,
                "returns": {
                    "return_1m": None,
                    "return_3m": None,
                    "return_6m": None,
                    "return_1y": None,
                }
            }

        t_date = latest_price.trading_date
        year_ago = t_date - timedelta(days=365)

        # 1. 52-Week High and Low
        year_records = (
            DailyPrice.query.filter(
                DailyPrice.security_id == security_id,
                DailyPrice.trading_date >= year_ago,
                DailyPrice.trading_date <= t_date,
            )
            .all()
        )

        valid_highs = [
            r.high_price if r.high_price is not None else r.close_price
            for r in year_records
            if (r.high_price is not None or r.close_price is not None)
        ]
        valid_lows = [
            r.low_price if r.low_price is not None else r.close_price
            for r in year_records
            if (r.low_price is not None or r.close_price is not None)
        ]

        w52_high = max(valid_highs) if valid_highs else (latest_price.high_price or latest_price.close_price)
        w52_low = min(valid_lows) if valid_lows else (latest_price.low_price or latest_price.close_price)

        # 2. Returns (1M = 30d, 3M = 90d, 6M = 180d, 1Y = 365d)
        def _calc_return(days: int) -> Optional[str]:
            target_date = t_date - timedelta(days=days)
            base_rec = (
                DailyPrice.query.filter(
                    DailyPrice.security_id == security_id,
                    DailyPrice.trading_date <= target_date,
                )
                .order_by(desc(DailyPrice.trading_date))
                .first()
            )
            if not base_rec or base_rec.close_price is None or base_rec.close_price <= Decimal("0"):
                return None

            latest_c = latest_price.close_price
            base_c = base_rec.close_price
            ret = ((latest_c - base_c) / base_c * Decimal("100")).quantize(Decimal("0.01"))
            return str(ret)

        # 3. Query chronological price slice for technical indicators
        recent_prices = (
            DailyPrice.query.filter_by(security_id=security_id)
            .order_by(desc(DailyPrice.trading_date))
            .limit(260)
            .all()
        )
        total_sessions = DailyPrice.query.filter_by(security_id=security_id).count()
        earliest_rec = (
            DailyPrice.query.filter_by(security_id=security_id)
            .order_by(asc(DailyPrice.trading_date))
            .first()
        )
        coverage_start = earliest_rec.trading_date.isoformat() if earliest_rec else None
        coverage_end = latest_price.trading_date.isoformat() if latest_price else None

        # 4. Moving averages: 20-session and 50-session
        sma_20 = None
        sma_50 = None
        if len(recent_prices) >= 20:
            p20 = [r.close_price for r in recent_prices[:20] if r.close_price is not None]
            if len(p20) == 20:
                sma_20 = _dec_str(sum(p20) / Decimal("20"), 2)

        if len(recent_prices) >= 50:
            p50 = [r.close_price for r in recent_prices[:50] if r.close_price is not None]
            if len(p50) == 50:
                sma_50 = _dec_str(sum(p50) / Decimal("50"), 2)

        # 5. Average Volume (30 sessions)
        avg_volume_30 = None
        v30 = [r.volume for r in recent_prices[:30] if r.volume is not None]
        if v30:
            avg_volume_30 = int(round(sum(v30) / len(v30)))

        # 6. Annualized Historical Volatility (sample std dev of daily log returns * sqrt(252))
        volatility = None
        if len(recent_prices) >= 20:
            try:
                import math
                closes = [float(r.close_price) for r in reversed(recent_prices) if r.close_price is not None]
                if len(closes) >= 20:
                    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0]
                    if len(returns) >= 19:
                        mean_ret = sum(returns) / len(returns)
                        var = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
                        std_dev = math.sqrt(var)
                        annualized_vol = std_dev * math.sqrt(252) * 100.0
                        volatility = f"{annualized_vol:.2f}%"
            except Exception:
                volatility = None

        return {
            "week_52_high": _dec_str(w52_high, 2),
            "week_52_low": _dec_str(w52_low, 2),
            "sma_20": sma_20,
            "sma_50": sma_50,
            "average_volume_30": avg_volume_30,
            "volatility": volatility,
            "coverage": {
                "start_date": coverage_start,
                "end_date": coverage_end,
                "total_sessions": total_sessions,
            },
            "returns": {
                "return_1m": _calc_return(30),
                "return_3m": _calc_return(90),
                "return_6m": _calc_return(180),
                "return_1y": _calc_return(365),
            }
        }

    @classmethod
    def get_market_summary(cls, security_id: int) -> Dict[str, Any]:
        """
        Retrieves a complete market performance summary for a security including
        latest pricing, 52-week range, and period returns.
        """
        return cls.get_latest_market_data(security_id)

    @classmethod
    def get_price_history(
        cls,
        security_id: int,
        range_key: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 2000,
        price_mode: str = "raw",
        adjustment_version: str = "split_bonus_v1",
    ) -> Dict[str, Any]:
        """
        Retrieves historical EOD DailyPrice or AdjustedDailyPrice records in chronological order.
        """
        security = cls.get_security_or_fail(security_id)

        # 1. Parameter ambiguity validation
        if range_key and (start_date or end_date):
            raise InvalidRangeError("Cannot specify predefined 'range' together with 'start' or 'end' dates.")

        clean_range = (range_key or "1y").strip().lower() if not (start_date or end_date) else None

        if clean_range and clean_range not in RANGE_DAYS_MAP:
            valid_keys = ", ".join(sorted(RANGE_DAYS_MAP.keys()))
            raise InvalidRangeError(f"Invalid range '{range_key}'. Allowed ranges are: {valid_keys}.")

        # 2. Date boundary resolution
        resolved_start = start_date
        resolved_end = end_date

        if clean_range:
            days_offset = RANGE_DAYS_MAP[clean_range]
            if days_offset is not None:
                latest_record = (
                    DailyPrice.query.filter_by(security_id=security.id)
                    .order_by(desc(DailyPrice.trading_date))
                    .first()
                )
                ref_date = latest_record.trading_date if latest_record else date.today()
                resolved_end = ref_date
                resolved_start = ref_date - timedelta(days=days_offset)

        if resolved_start and resolved_end and resolved_start > resolved_end:
            raise InvalidRangeError(
                f"Start date '{resolved_start}' cannot be later than end date '{resolved_end}'."
            )

        safe_limit = min(max(1, limit), 5000)
        clean_mode = (price_mode or "raw").strip().lower()

        # 3. Check if split_adjusted is requested and available
        if clean_mode == "split_adjusted":
            # Check if adjusted prices exist for this security and version
            adj_count = AdjustedDailyPrice.query.filter_by(
                security_id=security.id,
                adjustment_version=adjustment_version,
            ).count()

            if adj_count > 0:
                # Query AdjustedDailyPrice
                query = AdjustedDailyPrice.query.filter(
                    AdjustedDailyPrice.security_id == security.id,
                    AdjustedDailyPrice.adjustment_version == adjustment_version,
                )
                if resolved_start:
                    query = query.filter(AdjustedDailyPrice.trading_date >= resolved_start)
                if resolved_end:
                    query = query.filter(AdjustedDailyPrice.trading_date <= resolved_end)

                query = query.order_by(asc(AdjustedDailyPrice.trading_date))
                records = query.limit(safe_limit + 1).all()

                truncated = len(records) > safe_limit
                display_records = records[:safe_limit]

                prices_list = []
                for r in display_records:
                    prices_list.append({
                        "date": r.trading_date.isoformat(),
                        "open": _dec_str(r.adjusted_open, 2),
                        "high": _dec_str(r.adjusted_high, 2),
                        "low": _dec_str(r.adjusted_low, 2),
                        "close": _dec_str(r.adjusted_close, 2),
                        "volume": r.adjusted_volume,
                        "cumulative_price_factor": _dec_str(r.cumulative_price_factor, 6),
                    })

                applied_action_count = (
                    CorporateAction.query.filter_by(security_id=security.id)
                    .filter(CorporateAction.action_type.in_(["stock_split", "bonus"]))
                    .filter(CorporateAction.processing_status.in_(["applied", "verified"]))
                    .count()
                )

                start_iso = resolved_start.isoformat() if resolved_start else (display_records[0].trading_date.isoformat() if display_records else None)
                end_iso = resolved_end.isoformat() if resolved_end else (display_records[-1].trading_date.isoformat() if display_records else None)

                return {
                    "success": True,
                    "security": {
                        "security_id": security.id,
                        "company_id": security.company_id,
                        "company_name": security.company.display_name if security.company else security.symbol,
                        "symbol": security.symbol,
                        "exchange": security.exchange,
                        "series": security.series,
                        "isin": security.isin,
                        "currency": security.currency or "INR",
                    },
                    "range": {
                        "requested": clean_range or "custom",
                        "start": start_iso,
                        "end": end_iso,
                        "count": len(prices_list),
                        "truncated": truncated,
                    },
                    "prices": prices_list,
                    "metadata": {
                        "data_type": "end_of_day",
                        "source": "NSE_UDIFF",
                        "is_adjusted": True,
                        "requested_price_mode": "split_adjusted",
                        "returned_price_mode": "split_adjusted",
                        "adjustment_version": adjustment_version,
                        "applied_action_count": applied_action_count,
                        "adjustment_scope": "split_bonus_only",
                        "disclaimer": "Adjusted for stock splits and bonus issues. Cash dividends and rights issues are excluded.",
                    },
                }

        # 4. Raw DailyPrice query (Default or Fallback when adjusted records are not built)
        query = DailyPrice.query.filter(DailyPrice.security_id == security.id)
        if resolved_start:
            query = query.filter(DailyPrice.trading_date >= resolved_start)
        if resolved_end:
            query = query.filter(DailyPrice.trading_date <= resolved_end)

        query = query.order_by(asc(DailyPrice.trading_date))
        records = query.limit(safe_limit + 1).all()

        truncated = len(records) > safe_limit
        display_records = records[:safe_limit]

        prices_list = []
        for r in display_records:
            prices_list.append({
                "date": r.trading_date.isoformat(),
                "open": _dec_str(r.open_price, 2),
                "high": _dec_str(r.high_price, 2),
                "low": _dec_str(r.low_price, 2),
                "close": _dec_str(r.close_price, 2),
                "volume": r.volume,
                "turnover": _dec_str(r.turnover, 2),
                "vwap": _dec_str(r.vwap, 2),
            })

        start_iso = resolved_start.isoformat() if resolved_start else (display_records[0].trading_date.isoformat() if display_records else None)
        end_iso = resolved_end.isoformat() if resolved_end else (display_records[-1].trading_date.isoformat() if display_records else None)

        metadata_dict = {
            "data_type": "end_of_day",
            "source": "NSE_UDIFF",
            "is_adjusted": False,
            "requested_price_mode": clean_mode,
            "returned_price_mode": "raw",
            "adjustment_version": None,
            "applied_action_count": 0,
            "adjustment_scope": "none",
            "disclaimer": "Unadjusted nominal exchange prices. Excludes corporate action adjustments.",
        }
        if clean_mode == "split_adjusted":
            metadata_dict["unavailable_reason"] = "Split-adjusted price history has not been calculated for this security."

        # If no local prices exist and not in unit testing mode, fetch live historical candles from financial service
        if not prices_list:
            from flask import current_app
            is_testing = False
            try:
                is_testing = bool(
                    current_app
                    and current_app.config.get("TESTING", False)
                    and not current_app.config.get("ENABLE_LIVE_FALLBACK", False)
                )
            except Exception:
                pass

            if not is_testing:
                try:
                    from services.financial_service import get_stock_history
                    fetched_history = get_stock_history(security.symbol, clean_range or "1y")
                    if fetched_history:
                        prices_list = fetched_history[:safe_limit]
                        truncated = len(fetched_history) > safe_limit
                        start_iso = prices_list[0]["date"] if prices_list else None
                        end_iso = prices_list[-1]["date"] if prices_list else None
                        metadata_dict["source"] = "Live Market Feed"
                        metadata_dict["disclaimer"] = "Historical daily market prices."
                except Exception as e:
                    pass

        return {
            "success": True,
            "security": {
                "security_id": security.id,
                "company_id": security.company_id,
                "company_name": security.company.display_name if security.company else security.symbol,
                "symbol": security.symbol,
                "exchange": security.exchange,
                "series": security.series,
                "isin": security.isin,
                "currency": security.currency or "INR",
            },
            "range": {
                "requested": clean_range or "custom",
                "start": start_iso,
                "end": end_iso,
                "count": len(prices_list),
                "truncated": truncated,
            },
            "prices": prices_list,
            "metadata": metadata_dict,
        }

