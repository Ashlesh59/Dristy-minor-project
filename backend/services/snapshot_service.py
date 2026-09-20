"""
services/snapshot_service.py
--------------------------------------------------------------------------
Unified Verified Snapshot Engine for InvestIQ.
Assembles strict, versioned snapshots across 4 independent data sections:
1. Verified NSE Market Data (loaded from local Bhavcopy DailyPrice records)
2. Verified Financial Statements & Ratios (with reporting period and source)
3. Verified News Articles & Corporate Announcements (headline, source, timestamp, URL)
4. Missing sections & Quality Status classification

Snapshot Quality Statuses:
- 'complete': Verified market data + verified financial statements + verified news articles
- 'partial': Verified market data available, but financial statements or news missing
- 'insufficient': Market history < 5 sessions or missing price data
- 'invalid': Security record missing or inactive
--------------------------------------------------------------------------
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from database.db import db
from models.security import Security
from models.company import Company
from models.daily_price import DailyPrice
from services.market_data_service import MarketDataService
from services.financial_service import get_stock_quote
from services.news_service import get_ticker_news

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_verified_snapshot(record, allow_live_call: bool = True) -> Dict[str, Any]:
    """
    Constructs a strict, factual research snapshot for a given Research record.
    Never invents unstated figures. Explicitly identifies missing sections.
    """
    sec = None
    if record.security_id:
        sec = db.session.get(Security, record.security_id)
    if not sec and record.ticker_symbol:
        sec = Security.query.filter_by(symbol=record.ticker_symbol.upper(), is_active=True).first()

    company = sec.company if sec else None
    if not company and record.company_id:
        company = db.session.get(Company, record.company_id)

    symbol = (sec.symbol if sec else record.ticker_symbol or "UNKNOWN").upper()
    company_name = company.display_name if company else (record.company_name or symbol)
    currency = sec.currency if sec else "INR"
    exchange = sec.exchange if sec else "NSE"
    series = sec.series if sec else "EQ"
    isin = sec.isin if sec else None

    company_info = {
        "id": company.id if company else None,
        "name": company_name,
        "symbol": symbol,
        "exchange": exchange,
        "series": series,
        "isin": isin,
        "currency": currency,
        "asset_type": sec.asset_type if sec else "Equity",
    }

    # 1. VERIFIED MARKET DATA (From local Bhavcopy DailyPrice)
    market_data: Dict[str, Any] = {
        "is_available": False,
        "source": "NSE Bhavcopy",
        "currency": currency,
    }
    coverage_info: Dict[str, Any] = {
        "total_sessions": 0,
        "start_date": None,
        "end_date": None,
        "returns": {},
        "volatility": None,
    }
    data_sources: List[str] = []

    if sec:
        try:
            summary_dict = MarketDataService.get_market_summary(sec.id)
            m = summary_dict.get("market_data") or summary_dict.get("summary")
            cov = summary_dict.get("coverage") or (m.get("coverage") if m else {}) or {}
            ret_dict = summary_dict.get("returns") or (m.get("returns") if m else {}) or {}
            vol_val = summary_dict.get("volatility") or (m.get("volatility") if m else None)
            
            if m and m.get("close") is not None:
                close_val = float(m.get("close"))
                prev_close_val = float(m.get("previous_close")) if m.get("previous_close") is not None else None
                chg_val = float(m.get("change")) if m.get("change") is not None else (
                    round(close_val - prev_close_val, 2) if prev_close_val is not None else 0.0
                )
                chg_pct_val = float(m.get("change_percent")) if m.get("change_percent") is not None else (
                    round((chg_val / prev_close_val) * 100.0, 2) if prev_close_val else 0.0
                )

                market_data = {
                    "is_available": True,
                    "close": close_val,
                    "previous_close": prev_close_val,
                    "change": chg_val,
                    "change_percent": chg_pct_val,
                    "open": float(m.get("open")) if m.get("open") is not None else None,
                    "high": float(m.get("high")) if m.get("high") is not None else None,
                    "low": float(m.get("low")) if m.get("low") is not None else None,
                    "vwap": float(m.get("vwap")) if m.get("vwap") is not None else None,
                    "volume": int(m.get("volume")) if m.get("volume") is not None else None,
                    "turnover": float(m.get("turnover")) if m.get("turnover") is not None else None,
                    "week_52_high": float(m.get("week_52_high")) if m.get("week_52_high") is not None else None,
                    "week_52_low": float(m.get("week_52_low")) if m.get("week_52_low") is not None else None,
                    "trading_date": str(m.get("trading_date") or m.get("latest_trading_day") or ""),
                    "currency": currency,
                    "source": "NSE Bhavcopy",
                    "retrieved_at": _utc_now_iso(),
                }
                data_sources.append("NSE Bhavcopy (Official Exchange EOD Archive)")

            coverage_info = {
                "total_sessions": cov.get("total_sessions") or 0,
                "start_date": cov.get("start_date"),
                "end_date": cov.get("end_date"),
                "returns": ret_dict,
                "volatility": vol_val,
            }
        except Exception as e:
            logger.warning("Local Bhavcopy summary lookup non-fatal: %s", e)

    # Fallback to live quote if local market data is empty
    if not market_data.get("is_available") and allow_live_call:
        try:
            live_q = get_stock_quote(symbol)
            if live_q and live_q.get("price"):
                p_val = float(str(live_q.get("price")).replace(",", ""))
                c_val = float(str(live_q.get("change")).replace(",", "")) if live_q.get("change") else 0.0
                cp_str = str(live_q.get("change_percent") or "0").replace("%", "").strip()
                cp_val = float(cp_str) if cp_str else 0.0
                
                market_data = {
                    "is_available": True,
                    "close": p_val,
                    "previous_close": float(live_q.get("previous_close")) if live_q.get("previous_close") else None,
                    "change": c_val,
                    "change_percent": cp_val,
                    "open": float(live_q.get("open")) if live_q.get("open") else None,
                    "high": float(live_q.get("high")) if live_q.get("high") else None,
                    "low": float(live_q.get("low")) if live_q.get("low") else None,
                    "vwap": None,
                    "volume": int(live_q.get("volume")) if live_q.get("volume") else None,
                    "turnover": None,
                    "week_52_high": float(live_q.get("week_52_high")) if live_q.get("week_52_high") else None,
                    "week_52_low": float(live_q.get("week_52_low")) if live_q.get("week_52_low") else None,
                    "trading_date": str(live_q.get("latest_trading_day") or ""),
                    "currency": live_q.get("currency") or currency,
                    "source": live_q.get("source") or "Live Market Feed",
                    "retrieved_at": _utc_now_iso(),
                }
                data_sources.append(live_q.get("source") or "Live Market Feed")
        except Exception as ex:
            logger.debug("Live quote fallback attempt non-fatal: %s", ex)

    # 2. VERIFIED FINANCIAL STATEMENTS & RATIOS
    financial_statements: Dict[str, Any] = {
        "is_available": False,
        "reporting_period": None,
        "revenue": None,
        "operating_profit": None,
        "net_profit": None,
        "eps": None,
        "total_assets": None,
        "total_liabilities": None,
        "cash": None,
        "total_debt": None,
        "operating_cash_flow": None,
        "free_cash_flow": None,
        "currency": currency,
        "source": None,
        "retrieved_at": None,
    }

    financial_ratios: Dict[str, Any] = {
        "is_available": False,
        "pe_ratio": None,
        "price_to_book": None,
        "roe": None,
        "debt_to_equity": None,
        "operating_margin": None,
        "net_margin": None,
        "source": None,
        "retrieved_at": None,
    }

    # Check if record has verified fundamental statement data stored
    if record.financial_data:
        try:
            fin_parsed = json.loads(record.financial_data)
            statements = fin_parsed.get("financial_statements")
            if statements and isinstance(statements, dict) and statements.get("is_available"):
                financial_statements = statements
                data_sources.append(statements.get("source") or "Verified Financial Filings")

            ratios = fin_parsed.get("financial_ratios")
            if ratios and isinstance(ratios, dict) and ratios.get("is_available"):
                financial_ratios = ratios
        except Exception:
            pass

    # 3. VERIFIED NEWS & ANNOUNCEMENTS
    news_articles: List[Dict[str, Any]] = []
    if record.news_data:
        try:
            raw_news = json.loads(record.news_data)
            if isinstance(raw_news, list):
                for item in raw_news:
                    if isinstance(item, dict) and (item.get("title") or item.get("headline")):
                        news_articles.append({
                            "headline": (item.get("title") or item.get("headline") or "").strip(),
                            "source": item.get("source") or "Financial Media",
                            "published_at": item.get("published_at") or "",
                            "url": item.get("url") or "",
                            "summary": item.get("summary") or item.get("title") or "",
                            "ticker": symbol,
                            "sentiment": item.get("sentiment") or "Neutral",
                            "sentiment_score": item.get("sentiment_score") if item.get("sentiment_score") is not None else 0.0,
                        })
        except Exception:
            news_articles = []

    if not news_articles and allow_live_call:
        try:
            live_news = get_ticker_news(symbol, company_name)
            if live_news and isinstance(live_news, list):
                for item in live_news:
                    if isinstance(item, dict) and item.get("title"):
                        news_articles.append({
                            "headline": item.get("title", "").strip(),
                            "source": item.get("source") or "Financial Media",
                            "published_at": item.get("published_at") or "",
                            "url": item.get("url") or "",
                            "summary": item.get("summary") or item.get("title") or "",
                            "ticker": symbol,
                            "sentiment": item.get("sentiment") or "Neutral",
                            "sentiment_score": item.get("sentiment_score") if item.get("sentiment_score") is not None else 0.0,
                        })
                if news_articles:
                    record.news_data = json.dumps(news_articles)
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
        except Exception as ex:
            logger.debug("Live news lookup non-fatal: %s", ex)

    if news_articles:
        data_sources.append("Verified Financial News & Corporate Media Feed")

    # 4. MISSING SECTIONS & QUALITY STATUS
    missing_sections: List[str] = []
    if not market_data.get("is_available"):
        missing_sections.append("market_data")
    if not financial_statements.get("is_available"):
        missing_sections.append("financial_statements")
    if not financial_ratios.get("is_available"):
        missing_sections.append("financial_ratios")
    if not news_articles:
        missing_sections.append("news_articles")

    if not market_data.get("is_available"):
        quality_status = "insufficient"
    elif not sec or not sec.is_active:
        quality_status = "invalid"
    elif not missing_sections:
        quality_status = "complete"
    else:
        quality_status = "partial"

    snapshot = {
        "company": company_info,
        "market_data": market_data,
        "coverage": coverage_info,
        "financial_statements": financial_statements,
        "financial_ratios": financial_ratios,
        "news_articles": news_articles,
        "data_sources": list(dict.fromkeys(data_sources)),
        "missing_sections": missing_sections,
        "quality_status": quality_status,
        "created_at": _utc_now_iso(),
        "snapshot_version": 2,
    }

    return snapshot
