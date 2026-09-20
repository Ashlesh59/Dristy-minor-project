"""
services/financial_service.py
--------------------------------------------------------------------------
Resilient multi-tier financial data service.
Provides real-time stock quotes, historical time-series candles, and symbol search.
Tiers:
  1. Alpha Vantage API (when configured and within quota)
  2. Public live market quotes & historical candles (Yahoo Finance API)
  3. Local Bhavcopy market database fallback
--------------------------------------------------------------------------
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT_SECONDS = 10
YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class FinancialServiceError(Exception):
    """Base class for financial service errors."""
    pass


class MissingApiKeyError(FinancialServiceError):
    """API key is not configured."""
    pass


class FinancialServiceUnavailableError(FinancialServiceError):
    """Service is temporarily unreachable or rate limited."""
    pass


class FinancialServiceBadResponseError(FinancialServiceError):
    """Invalid or empty response for symbol."""
    pass


def _detect_currency(symbol: str) -> str:
    sym = (symbol or "").upper()
    if sym.endswith(".BSE") or sym.endswith(".NSE") or sym.endswith(".IN") or sym.endswith(".BO") or sym.endswith(".NS"):
        return "INR"
    if sym.endswith(".L") or sym.endswith(".LON"):
        return "GBP"
    if sym.endswith(".TO") or sym.endswith(".TRT"):
        return "CAD"
    if sym.endswith(".AX"):
        return "AUD"
    if sym.endswith(".DE") or sym.endswith(".PA") or sym.endswith(".FR"):
        return "EUR"
    if sym.endswith(".T") or sym.endswith(".TYO"):
        return "JPY"
    return "USD"


def _fetch_alpha_vantage_quote(ticker_symbol: str) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return None

    # Determine optimal ticker candidate for Alpha Vantage
    candidates = [ticker_symbol]
    if not any(ticker_symbol.endswith(sfx) for sfx in [".BSE", ".NSE", ".LON", ".TO", ".AX", ".DE"]):
        # Add BSE candidate for Indian stocks
        candidates.append(f"{ticker_symbol}.BSE")

    for sym in candidates:
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": sym,
                "apikey": api_key,
            }
            response = requests.get(ALPHA_VANTAGE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code != 200:
                continue

            payload = response.json()
            if "Note" in payload or "Information" in payload:
                logger.info("Alpha Vantage rate limit reached for '%s'", sym)
                return None
            if "Error Message" in payload:
                continue

            quote = payload.get("Global Quote")
            if not quote or not quote.get("05. price"):
                continue

            currency = _detect_currency(sym)
            return {
                "symbol": ticker_symbol,
                "open": quote.get("02. open"),
                "high": quote.get("03. high"),
                "low": quote.get("04. low"),
                "price": quote.get("05. price"),
                "volume": quote.get("06. volume"),
                "latest_trading_day": quote.get("07. latest trading day"),
                "previous_close": quote.get("08. previous close"),
                "change": quote.get("09. change"),
                "change_percent": quote.get("10. change percent"),
                "currency": currency,
                "source": "Alpha Vantage",
            }
        except Exception as ex:
            logger.debug("Alpha Vantage attempt for %s failed: %s", sym, ex)

    return None


def _fetch_live_chart_quote(ticker_symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetches real-time market quote using Yahoo Finance chart endpoint.
    Handles US and Indian equities with automatic suffix resolution.
    """
    clean_sym = ticker_symbol.strip().upper()
    candidates = [clean_sym]
    if not any(clean_sym.endswith(s) for s in [".NS", ".BO", ".BSE"]):
        candidates.extend([f"{clean_sym}.NS", f"{clean_sym}.BO"])

    for sym in candidates:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
            res = requests.get(url, headers=YF_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            if res.status_code != 200:
                continue

            data = res.json()
            results = data.get("chart", {}).get("result")
            if not results or len(results) == 0:
                continue

            res_obj = results[0]
            meta = res_obj.get("meta", {})
            price = meta.get("regularMarketPrice")
            if price is None:
                continue

            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or price
            change = (price - prev_close) if (price is not None and prev_close is not None) else 0.0
            change_percent = ((change / prev_close) * 100.0) if (prev_close and prev_close != 0) else 0.0

            t_stamp = meta.get("regularMarketTime") or int(datetime.now(timezone.utc).timestamp())
            trading_day = datetime.fromtimestamp(t_stamp, timezone.utc).strftime("%Y-%m-%d")

            curr = meta.get("currency") or _detect_currency(sym)
            day_high = meta.get("regularMarketDayHigh") or meta.get("dayHigh") or price
            day_low = meta.get("regularMarketDayLow") or meta.get("dayLow") or price
            day_open = meta.get("regularMarketOpen") or meta.get("open") or price
            volume = meta.get("regularMarketVolume") or meta.get("volume") or 0

            return {
                "symbol": clean_sym,
                "price": str(round(float(price), 2)),
                "previous_close": str(round(float(prev_close), 2)),
                "change": str(round(float(change), 2)),
                "change_percent": f"{change_percent:+.2f}%",
                "open": str(round(float(day_open), 2)),
                "high": str(round(float(day_high), 2)),
                "low": str(round(float(day_low), 2)),
                "volume": str(int(volume)),
                "latest_trading_day": trading_day,
                "currency": curr,
                "source": "Live Market Feed",
            }
        except Exception as ex:
            logger.debug("Live quote attempt for %s failed: %s", sym, ex)

    return None


def get_stock_quote(ticker_symbol: str) -> Dict[str, Any]:
    """
    Fetches a real-time quote for `ticker_symbol` using multi-tier fallback:
    1. Alpha Vantage
    2. Live Market Feed (Yahoo Finance)
    3. Local database Bhavcopy (if available)
    """
    clean_ticker = (ticker_symbol or "").strip()
    if not clean_ticker:
        raise FinancialServiceBadResponseError("Ticker symbol cannot be empty.")

    # Tier 1: Alpha Vantage (if configured and working)
    try:
        av_quote = _fetch_alpha_vantage_quote(clean_ticker)
        if av_quote:
            return av_quote
    except Exception as ex:
        logger.info("Alpha Vantage lookup failed for %s: %s", clean_ticker, ex)

    # Tier 2: Live Market Feed (Yahoo Finance)
    try:
        live_quote = _fetch_live_chart_quote(clean_ticker)
        if live_quote:
            return live_quote
    except Exception as ex:
        logger.info("Live market feed lookup failed for %s: %s", clean_ticker, ex)

    # Tier 3: Local SQLite Bhavcopy fallback
    try:
        from models.security import Security
        from services.market_data_service import MarketDataService
        sec = Security.query.filter_by(symbol=clean_ticker.upper()).first()
        if sec:
            summary = MarketDataService.get_market_summary(sec.id)
            if summary and summary.get("summary") and summary["summary"].get("close"):
                s = summary["summary"]
                chg_pct = f"{s.get('day_change_percent')}%" if s.get("day_change_percent") is not None else ""
                return {
                    "symbol": sec.symbol,
                    "price": str(s.get("close") or ""),
                    "change": str(s.get("day_change") or ""),
                    "change_percent": chg_pct,
                    "open": str(s.get("open") or ""),
                    "high": str(s.get("high") or ""),
                    "low": str(s.get("low") or ""),
                    "previous_close": str(s.get("previous_close") or ""),
                    "volume": str(s.get("volume") or ""),
                    "latest_trading_day": s.get("trading_date") or "",
                    "currency": sec.currency or "INR",
                    "source": "NSE Bhavcopy",
                }
    except Exception as ex:
        logger.debug("Local Bhavcopy fallback failed for %s: %s", clean_ticker, ex)

    raise FinancialServiceBadResponseError(f"Could not retrieve financial quote for '{ticker_symbol}'.")


def get_stock_history(ticker_symbol: str, range_key: str = "1y") -> List[Dict[str, Any]]:
    """
    Fetches historical daily OHLCV candles from Live Market Feed for securities
    that lack stored local Bhavcopy data.
    """
    clean_sym = (ticker_symbol or "").strip().upper()
    range_map = {
        "1m": "1mo",
        "3m": "3mo",
        "6m": "6mo",
        "1y": "1y",
        "3y": "5y",
        "5y": "5y",
        "max": "max",
    }
    yf_range = range_map.get((range_key or "1y").lower(), "1y")

    candidates = [clean_sym]
    if not any(clean_sym.endswith(s) for s in [".NS", ".BO", ".BSE"]):
        candidates.extend([f"{clean_sym}.NS", f"{clean_sym}.BO"])

    for sym in candidates:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range={yf_range}"
            res = requests.get(url, headers=YF_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            if res.status_code != 200:
                continue

            data = res.json()
            results = data.get("chart", {}).get("result")
            if not results or len(results) == 0:
                continue

            res_obj = results[0]
            timestamps = res_obj.get("timestamp", [])
            quotes = res_obj.get("indicators", {}).get("quote", [{}])[0]
            opens = quotes.get("open", [])
            highs = quotes.get("high", [])
            lows = quotes.get("low", [])
            closes = quotes.get("close", [])
            volumes = quotes.get("volume", [])

            points = []
            for i in range(len(timestamps)):
                c = closes[i] if i < len(closes) else None
                if c is None:
                    continue
                dt_str = datetime.fromtimestamp(timestamps[i], timezone.utc).strftime("%Y-%m-%d")
                points.append({
                    "date": dt_str,
                    "open": round(float(opens[i]) if i < len(opens) and opens[i] is not None else float(c), 2),
                    "high": round(float(highs[i]) if i < len(highs) and highs[i] is not None else float(c), 2),
                    "low": round(float(lows[i]) if i < len(lows) and lows[i] is not None else float(c), 2),
                    "close": round(float(c), 2),
                    "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                })

            if points:
                return points
        except Exception as ex:
            logger.debug("Historical fetch for %s failed: %s", sym, ex)

    return []


def search_symbols(keywords: str) -> List[Dict[str, Any]]:
    """
    Searches for global stock tickers and company names.
    Queries Live Market discovery endpoint and falls back to Alpha Vantage SYMBOL_SEARCH.
    """
    clean_kw = (keywords or "").strip()
    if not clean_kw:
        return []

    results = []

    # 1. Live Market Search (Yahoo Finance search endpoint)
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={clean_kw}&quotesCount=10&newsCount=0"
        res = requests.get(url, headers=YF_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
        if res.status_code == 200:
            quotes = res.json().get("quotes", [])
            for item in quotes:
                quote_type = item.get("quoteType", "").upper()
                if quote_type not in ("EQUITY", "ETF"):
                    continue
                sym = item.get("symbol", "")
                if not sym or "=" in sym or "^" in sym:
                    continue
                name = item.get("shortname") or item.get("longname") or sym
                exch = item.get("exchDisp") or item.get("exchange") or "US"
                is_indian = sym.endswith(".NS") or sym.endswith(".BO") or exch in ("NSE", "BSE")
                clean_sym = sym.replace(".NS", "").replace(".BO", "") if is_indian else sym

                results.append({
                    "symbol": clean_sym,
                    "raw_symbol": sym,
                    "name": name,
                    "exchange": "NSE" if (sym.endswith(".NS") or exch == "NSE") else ("BSE" if (sym.endswith(".BO") or exch == "BSE") else exch),
                    "type": "Equity" if quote_type == "EQUITY" else "ETF",
                    "currency": "INR" if is_indian else "USD",
                    "country": "IN" if is_indian else "US",
                })
    except Exception as ex:
        logger.info("Global symbol search live endpoint error: %s", ex)

    # 2. Alpha Vantage SYMBOL_SEARCH fallback
    if not results:
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
        if api_key:
            try:
                params = {"function": "SYMBOL_SEARCH", "keywords": clean_kw, "apikey": api_key}
                response = requests.get(ALPHA_VANTAGE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
                if response.status_code == 200:
                    best_matches = response.json().get("bestMatches", [])
                    for match in best_matches:
                        results.append({
                            "symbol": match.get("1. symbol"),
                            "raw_symbol": match.get("1. symbol"),
                            "name": match.get("2. name"),
                            "exchange": match.get("4. region", "US"),
                            "type": match.get("3. type", "Equity"),
                            "currency": match.get("8. currency", "USD"),
                            "country": match.get("4. region", "US"),
                        })
            except Exception as ex:
                logger.info("Alpha Vantage search fallback error: %s", ex)

    def _rank_match(item):
        sym = item.get("symbol", "").upper()
        q = clean_kw.upper()
        exch = (item.get("exchange") or "").upper()
        if sym == q:
            return (0, len(sym))
        if exch in ("NASDAQ", "NYSE", "NSE", "BSE", "NMS", "NYQ"):
            return (1, len(sym))
        if "." not in sym:
            return (2, len(sym))
        return (3, len(sym))

    results.sort(key=_rank_match)
    return results

