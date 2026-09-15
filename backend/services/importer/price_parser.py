"""
services/importer/price_parser.py
--------------------------------------------------------------------------
Parser and strict validator for exchange Bhavcopy price records (UDiFF & aliases).
--------------------------------------------------------------------------
"""

import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional, Tuple


class PriceValidationError(Exception):
    """Raised when a price row fails validation rules."""
    pass


# Map of standard canonical fields to list of possible header variations
HEADER_ALIASES = {
    "trading_date": ["TradDt", "TRAD_DT", "TRADING_DATE", "TIMESTAMP", "DATE"],
    "symbol": ["TckrSymb", "SYMBOL", "TCKR_SYMB", "SECURITY_SYMBOL"],
    "series": ["SctySrs", "SERIES", "SCTY_SRS", "SECURITY_SERIES"],
    "isin": ["ISIN", "ISIN_NO", "ISIN_NUMBER"],
    "open": ["OpnPric", "OPEN", "OPEN_PRICE", "OPENING_PRICE"],
    "high": ["HghPric", "HIGH", "HIGH_PRICE"],
    "low": ["LwPric", "LOW", "LOW_PRICE"],
    "close": ["ClsPric", "CLOSE", "CLOSE_PRICE", "CLOSING_PRICE"],
    "last": ["LastPric", "LAST", "LAST_PRICE", "LTP"],
    "prev_close": ["PrvsClsgPric", "PREVCLOSE", "PREVIOUS_CLOSE", "PREV_CLOSE"],
    "vwap": ["Vwap", "VWAP", "AVG_PRICE", "AVERAGE_PRICE"],
    "volume": ["TtlTradgVol", "VOLUME", "TOTTRDQTY", "TOTAL_TRADED_QTY"],
    "turnover": ["TtlTrdVal", "TtlTrfVal", "TURNOVER", "TOTTRDVAL", "TOTAL_TRADED_VAL"],
    "trade_count": ["TtlNbOfTxsExctd", "TOTAL_TRADES", "NO_OF_TRADES", "TRADES"],
    "delivery_qty": ["DlvryQty", "DELIV_QTY", "DELIVERABLE_QTY"],
    "delivery_pct": ["DlvryPrcnt", "DlvryPer", "DELIV_PER", "DELIVERABLE_PER", "DELIV_PCT"],
}


def build_header_map(fieldnames: list) -> Dict[str, str]:
    """
    Builds a normalized mapping from canonical keys to the actual CSV header names.
    """
    raw_headers = {fn.strip(): fn for fn in fieldnames if fn}
    header_map = {}

    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            # Check exact match or case-insensitive match
            for rh_clean, rh_orig in raw_headers.items():
                if rh_clean.upper() == alias.upper():
                    header_map[canonical] = rh_orig
                    break
            if canonical in header_map:
                break

    return header_map


def parse_trading_date(val: Any) -> date:
    """
    Parses trading date from formats: YYYY-MM-DD, YYYYMMDD, DD-MMM-YYYY.
    """
    if not val:
        raise PriceValidationError("Trading date is missing.")

    if isinstance(val, date):
        return val

    clean_val = str(val).strip()
    if not clean_val:
        raise PriceValidationError("Trading date is empty.")

    # Try common exchange date formats
    date_formats = [
        "%Y-%m-%d",       # 2026-09-15
        "%Y%m%d",         # 20260915
        "%d-%b-%Y",       # 15-Sep-2026 / 15-SEP-2026
        "%d-%m-%Y",       # 15-09-2026
        "%d/%m/%Y",       # 15/09/2026
        "%Y/%m/%d",       # 2026/09/15
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(clean_val, fmt).date()
        except ValueError:
            continue

    raise PriceValidationError(f"Unrecognized date format: '{clean_val}'. Expected YYYY-MM-DD, YYYYMMDD, or DD-MMM-YYYY.")


def parse_decimal(val: Any, field_name: str, allow_none: bool = False, allow_zero: bool = True) -> Optional[Decimal]:
    """
    Parses a Decimal value from string or numeric input.
    Validates non-negativity and decimal structure.
    """
    if val is None or str(val).strip() == "" or str(val).strip().upper() in ("-", "NA", "NULL", "N/A"):
        if allow_none:
            return None
        raise PriceValidationError(f"Required price field '{field_name}' is missing.")

    clean_str = str(val).strip().replace(",", "")
    try:
        dec = Decimal(clean_str)
    except (InvalidOperation, ValueError):
        raise PriceValidationError(f"Invalid decimal number for '{field_name}': '{val}'.")

    if dec < Decimal("0"):
        raise PriceValidationError(f"'{field_name}' cannot be negative: {dec}.")

    if not allow_zero and dec == Decimal("0"):
        raise PriceValidationError(f"'{field_name}' cannot be zero.")

    return dec


def parse_int(val: Any, field_name: str, allow_none: bool = True) -> Optional[int]:
    """
    Parses a non-negative integer.
    """
    if val is None or str(val).strip() == "" or str(val).strip().upper() in ("-", "NA", "NULL", "N/A"):
        if allow_none:
            return None
        raise PriceValidationError(f"Required integer field '{field_name}' is missing.")

    clean_str = str(val).strip().replace(",", "")
    try:
        # Handles potential decimal string like "100.0" from float export
        float_val = float(clean_str)
        int_val = int(float_val)
    except (ValueError, TypeError):
        raise PriceValidationError(f"Invalid integer for '{field_name}': '{val}'.")

    if int_val < 0:
        raise PriceValidationError(f"'{field_name}' cannot be negative: {int_val}.")

    return int_val


def parse_and_validate_row(row: Dict[str, str], header_map: Dict[str, str], row_num: int) -> Dict[str, Any]:
    """
    Extracts, converts, and validates a raw Bhavcopy CSV row.
    
    Returns:
        dict: Fully parsed and validated price record dictionary.
    
    Raises:
        PriceValidationError: If any required field is missing or violates validation rules.
    """
    def _get_val(canonical_key: str) -> Optional[str]:
        header_col = header_map.get(canonical_key)
        if header_col and header_col in row:
            return row[header_col]
        return None

    # 1. Symbol & Series validation
    raw_symbol = _get_val("symbol")
    if not raw_symbol or not raw_symbol.strip():
        raise PriceValidationError("Symbol is missing or empty.")
    symbol = raw_symbol.strip().upper()

    raw_series = _get_val("series")
    if not raw_series or not raw_series.strip():
        raise PriceValidationError("Series is missing or empty.")
    series = raw_series.strip().upper()

    isin = (_get_val("isin") or "").strip().upper() or None

    # 2. Trading Date
    trading_date = parse_trading_date(_get_val("trading_date"))

    # 3. OHLC Prices
    open_price = parse_decimal(_get_val("open"), "open_price", allow_none=False)
    high_price = parse_decimal(_get_val("high"), "high_price", allow_none=False)
    low_price = parse_decimal(_get_val("low"), "low_price", allow_none=False)
    close_price = parse_decimal(_get_val("close"), "close_price", allow_none=False)

    # 4. Optional Prices
    last_price = parse_decimal(_get_val("last"), "last_price", allow_none=True)
    previous_close = parse_decimal(_get_val("prev_close"), "previous_close", allow_none=True)
    vwap = parse_decimal(_get_val("vwap"), "vwap", allow_none=True)

    # 5. Volume & Quantities
    volume = parse_int(_get_val("volume"), "volume", allow_none=True)
    turnover = parse_decimal(_get_val("turnover"), "turnover", allow_none=True)
    trade_count = parse_int(_get_val("trade_count"), "trade_count", allow_none=True)
    deliverable_qty = parse_int(_get_val("delivery_qty"), "deliverable_quantity", allow_none=True)
    deliverable_pct = parse_decimal(_get_val("delivery_pct"), "deliverable_percentage", allow_none=True)

    if deliverable_pct is not None and deliverable_pct > Decimal("100.0"):
        raise PriceValidationError(f"Deliverable percentage exceeds 100%: {deliverable_pct}.")

    # 6. OHLC Relationship Logic
    # For active trading: High must be >= max(Open, Low, Close) and Low must be <= min(Open, High, Close)
    if high_price < low_price:
        raise PriceValidationError(
            f"Invalid OHLC relationship: High price ({high_price}) is less than Low price ({low_price})."
        )
    if high_price < open_price:
        raise PriceValidationError(
            f"Invalid OHLC relationship: High price ({high_price}) is less than Open price ({open_price})."
        )
    if high_price < close_price:
        raise PriceValidationError(
            f"Invalid OHLC relationship: High price ({high_price}) is less than Close price ({close_price})."
        )
    if low_price > open_price:
        raise PriceValidationError(
            f"Invalid OHLC relationship: Low price ({low_price}) is greater than Open price ({open_price})."
        )
    if low_price > close_price:
        raise PriceValidationError(
            f"Invalid OHLC relationship: Low price ({low_price}) is greater than Close price ({close_price})."
        )

    # Calculate VWAP if missing but volume & turnover exist
    if vwap is None and volume and volume > 0 and turnover and turnover > Decimal("0"):
        vwap = (turnover / Decimal(volume)).quantize(Decimal("0.0001"))

    return {
        "symbol": symbol,
        "series": series,
        "isin": isin,
        "trading_date": trading_date,
        "open_price": open_price,
        "high_price": high_price,
        "low_price": low_price,
        "close_price": close_price,
        "last_price": last_price,
        "previous_close": previous_close,
        "vwap": vwap,
        "volume": volume,
        "turnover": turnover,
        "trade_count": trade_count,
        "deliverable_quantity": deliverable_qty,
        "deliverable_percentage": deliverable_pct,
        "source_row_number": row_num,
    }
