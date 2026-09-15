"""
services/importer/normalizer.py
--------------------------------------------------------------------------
Data normalization, date parsing, numeric conversions, and field sanitization
for NSE equity listings.
--------------------------------------------------------------------------
"""

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import re
from typing import Optional, Dict, Any, Tuple

from services.importer.isin_validator import validate_isin


PUNCTUATION_STRIP_REGEX = re.compile(r"[\.,;:\(\)\'\"\-&]+")
WHITESPACE_COLLAPSE_REGEX = re.compile(r"\s+")


def normalize_company_name(raw_name: str) -> str:
    """
    Normalizes a company name for indexed, case-insensitive comparison.
    Preserves word boundaries and spaces.
    Example: 'Tata Motors Limited' -> 'tata motors limited'
    """
    if not raw_name:
        return ""
    # Convert to lowercase
    lower = raw_name.lower()
    # Replace punctuation with spaces
    no_punct = PUNCTUATION_STRIP_REGEX.sub(" ", lower)
    # Collapse multiple consecutive spaces
    collapsed = WHITESPACE_COLLAPSE_REGEX.sub(" ", no_punct)
    return collapsed.strip()


def parse_listing_date(raw_val: str) -> Tuple[Optional[date], Optional[str]]:
    """
    Parses date strings like '06-OCT-2008' or '2024-05-15'.
    Returns (parsed_date, warning_message).
    """
    if not raw_val:
        return None, None

    clean = raw_val.strip().upper()
    formats = ["%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(clean, fmt)
            return dt.date(), None
        except ValueError:
            continue

    return None, f"Could not parse listing date: '{raw_val}'"


def parse_decimal(raw_val: str) -> Tuple[Optional[Decimal], Optional[str]]:
    """Safely parses decimal/numeric strings."""
    if not raw_val:
        return None, None
    clean = raw_val.strip().replace(",", "")
    try:
        return Decimal(clean), None
    except (InvalidOperation, ValueError):
        return None, f"Invalid numeric value: '{raw_val}'"


def parse_integer(raw_val: str) -> Tuple[Optional[int], Optional[str]]:
    """Safely parses integer strings."""
    if not raw_val:
        return None, None
    clean = raw_val.strip().replace(",", "")
    try:
        # If string contains a float like '1.0', convert via float first
        val = int(float(clean))
        return val, None
    except (ValueError, TypeError):
        return None, f"Invalid integer value: '{raw_val}'"


class ParsedNSEEquity:
    def __init__(
        self,
        symbol: str,
        legal_name: str,
        display_name: str,
        normalized_name: str,
        series: str,
        isin: Optional[str],
        listing_date: Optional[date],
        paid_up_value: Optional[Decimal],
        market_lot: Optional[int],
        face_value: Optional[Decimal],
        warnings: list,
    ):
        self.symbol = symbol
        self.legal_name = legal_name
        self.display_name = display_name
        self.normalized_name = normalized_name
        self.series = series
        self.isin = isin
        self.listing_date = listing_date
        self.paid_up_value = paid_up_value
        self.market_lot = market_lot
        self.face_value = face_value
        self.warnings = warnings


def normalize_nse_row(row_dict: Dict[str, str]) -> Tuple[Optional[ParsedNSEEquity], Optional[str]]:
    """
    Maps raw NSE row headers to normalized domain fields.
    Returns (ParsedNSEEquity, fatal_error_message).
    """
    warnings = []

    # 1. Symbol (Fatal if missing)
    raw_symbol = row_dict.get("SYMBOL", "").strip().upper()
    if not raw_symbol:
        return None, "Missing required 'SYMBOL'"

    # 2. Company Name (Fatal if missing)
    raw_name = (
        row_dict.get("NAME OF COMPANY")
        or row_dict.get("NAME_OF_COMPANY")
        or row_dict.get("COMPANY NAME")
        or ""
    ).strip()
    if not raw_name:
        return None, f"Symbol '{raw_symbol}' is missing required 'NAME OF COMPANY'"

    display_name = WHITESPACE_COLLAPSE_REGEX.sub(" ", raw_name).strip()
    normalized_name = normalize_company_name(display_name)

    # 3. Series (Non-null, defaults to 'EQ')
    raw_series = row_dict.get("SERIES", "").strip().upper()
    series = raw_series if raw_series else "EQ"

    # 4. ISIN (Validate format & Luhn checksum)
    raw_isin = (row_dict.get("ISIN NUMBER") or row_dict.get("ISIN") or "").strip().upper()
    isin = raw_isin if raw_isin else None
    if isin:
        is_valid, isin_err = validate_isin(isin, expected_country="IN")
        if not is_valid:
            warnings.append(isin_err)

    # 5. Listing Date (Optional / Non-fatal)
    raw_listing_date = (row_dict.get("DATE OF LISTING") or row_dict.get("LISTING DATE") or "").strip()
    listing_date, date_warn = parse_listing_date(raw_listing_date)
    if date_warn:
        warnings.append(date_warn)

    # 6. Paid Up Value (Optional / Non-fatal)
    raw_paid_up = (row_dict.get("PAID UP VALUE") or row_dict.get("PAID_UP_VALUE") or "").strip()
    paid_up_value, paid_up_warn = parse_decimal(raw_paid_up)
    if paid_up_warn:
        warnings.append(paid_up_warn)

    # 7. Market Lot (Optional / Non-fatal)
    raw_lot = (row_dict.get("MARKET LOT") or row_dict.get("MARKET_LOT") or "").strip()
    market_lot, lot_warn = parse_integer(raw_lot)
    if lot_warn:
        warnings.append(lot_warn)

    # 8. Face Value (Optional / Non-fatal)
    raw_face = (row_dict.get("FACE VALUE") or row_dict.get("FACE_VALUE") or "").strip()
    face_value, face_warn = parse_decimal(raw_face)
    if face_warn:
        warnings.append(face_warn)

    parsed = ParsedNSEEquity(
        symbol=raw_symbol,
        legal_name=display_name,
        display_name=display_name,
        normalized_name=normalized_name,
        series=series,
        isin=isin,
        listing_date=listing_date,
        paid_up_value=paid_up_value,
        market_lot=market_lot,
        face_value=face_value,
        warnings=warnings,
    )
    return parsed, None
