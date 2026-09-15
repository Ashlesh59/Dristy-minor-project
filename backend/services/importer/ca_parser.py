"""
Corporate Action Parser — Normalizes raw exchange action rows and extracts split/bonus ratios.
"""
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional, Tuple


class CorporateActionParser:
    """
    Parses and standardizes raw corporate action CSV rows into structured domain models.
    """

    MONTH_MAP = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
    }

    @classmethod
    def parse_date(cls, raw_val: Any) -> Optional[date]:
        """
        Parses dates in DD-MMM-YYYY, YYYY-MM-DD, or DD/MM/YYYY format.
        """
        if raw_val is None:
            return None
        s = str(raw_val).strip()
        if not s or s.upper() in ("NA", "N/A", "NULL", "-"):
            return None

        # Try ISO format YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except ValueError:
                return None

        # Try DD-MMM-YYYY (e.g. 15-SEP-2026 or 15-Sep-2026)
        m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$", s)
        if m:
            day, month_str, year = int(m.group(1)), m.group(2).upper(), int(m.group(3))
            month = cls.MONTH_MAP.get(month_str)
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    return None

        # Try DD/MM/YYYY
        if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
            try:
                return datetime.strptime(s, "%d/%m/%Y").date()
            except ValueError:
                return None

        return None

    @classmethod
    def parse_purpose(cls, raw_purpose: str) -> Dict[str, Any]:
        """
        Analyzes the Purpose/Subject string and extracts action_type, ratios, and processing_status.
        """
        desc = (raw_purpose or "").strip()
        if not desc:
            return {
                "action_type": "other",
                "processing_status": "manual_review",
                "review_reason": "Missing purpose description",
                "ratio_from": None,
                "ratio_to": None,
                "cash_amount": None,
            }

        desc_lower = desc.lower()

        # 1. Stock Split / Sub-division
        if "split" in desc_lower or "sub-division" in desc_lower or "subdivision" in desc_lower:
            return cls._parse_split(desc, desc_lower)

        # 2. Bonus Issue
        if "bonus" in desc_lower:
            return cls._parse_bonus(desc, desc_lower)

        # 3. Cash Dividend
        if "dividend" in desc_lower:
            return cls._parse_dividend(desc, desc_lower)

        # 4. Rights Issue
        if "rights" in desc_lower or "right issue" in desc_lower:
            return {
                "action_type": "rights_issue",
                "processing_status": "manual_review",
                "review_reason": "Rights issues require manual TERP calculation",
                "ratio_from": None,
                "ratio_to": None,
                "cash_amount": None,
            }

        # 5. Buyback
        if "buyback" in desc_lower or "buy back" in desc_lower:
            return {
                "action_type": "buyback",
                "processing_status": "manual_review",
                "review_reason": "Buyback requires manual tender review",
                "ratio_from": None,
                "ratio_to": None,
                "cash_amount": None,
            }

        # 6. Merger / Demerger / Amalgamation
        if "merger" in desc_lower or "demerger" in desc_lower or "amalgamation" in desc_lower or "arrangement" in desc_lower:
            return {
                "action_type": "merger" if "demerger" not in desc_lower else "demerger",
                "processing_status": "manual_review",
                "review_reason": "Restructuring requires manual ratio mapping",
                "ratio_from": None,
                "ratio_to": None,
                "cash_amount": None,
            }

        # 7. Symbol change
        if "symbol change" in desc_lower or "change in name" in desc_lower or "name change" in desc_lower:
            return {
                "action_type": "symbol_change",
                "processing_status": "manual_review",
                "review_reason": "Symbol/name change requires security linkage review",
                "ratio_from": None,
                "ratio_to": None,
                "cash_amount": None,
            }

        # Unrecognized
        return {
            "action_type": "other",
            "processing_status": "manual_review",
            "review_reason": "Unrecognized corporate action purpose",
            "ratio_from": None,
            "ratio_to": None,
            "cash_amount": None,
        }

    @classmethod
    def _parse_split(cls, desc: str, desc_lower: str) -> Dict[str, Any]:
        """
        Parses split descriptions like 'Split From Rs 10/- To Rs 2/-' or 'Split 10:2'.
        """
        # Pattern 1: Face value from X to Y (e.g. From Rs 10/- to Rs 2/- or from Rs. 10 to Rs. 1)
        m = re.search(
            r"(?:from\s+)?(?:rs\.?\s*)?(\d+(?:\.\d+)?)\s*(?:\/-)?\s*(?:to\s+)(?:rs\.?\s*)?(\d+(?:\.\d+)?)\s*(?:\/-)?",
            desc_lower
        )
        if m:
            try:
                old_fv = Decimal(m.group(1))
                new_fv = Decimal(m.group(2))
                if old_fv > Decimal("0") and new_fv > Decimal("0") and old_fv > new_fv:
                    return {
                        "action_type": "stock_split",
                        "processing_status": "verified",
                        "review_reason": None,
                        "ratio_from": old_fv,
                        "ratio_to": new_fv,
                        "cash_amount": None,
                    }
                elif old_fv <= new_fv:
                    return {
                        "action_type": "stock_split",
                        "processing_status": "manual_review",
                        "review_reason": f"Invalid split face values: old ({old_fv}) <= new ({new_fv})",
                        "ratio_from": old_fv,
                        "ratio_to": new_fv,
                        "cash_amount": None,
                    }
            except (InvalidOperation, ValueError):
                pass


        # Pattern 2: Split X:Y (e.g. Split 10:1 or Sub-division 5:1)
        m2 = re.search(r"(?:split|sub-division|subdivision)\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", desc_lower)
        if m2:
            try:
                val1 = Decimal(m2.group(1))
                val2 = Decimal(m2.group(2))
                if val1 > val2 and val2 > Decimal("0"):
                    # 10:2 means 10 face value to 2
                    return {
                        "action_type": "stock_split",
                        "processing_status": "verified",
                        "review_reason": None,
                        "ratio_from": val1,
                        "ratio_to": val2,
                        "cash_amount": None,
                    }
            except (InvalidOperation, ValueError):
                pass

        return {
            "action_type": "stock_split",
            "processing_status": "manual_review",
            "review_reason": "Could not reliably extract stock split ratio",
            "ratio_from": None,
            "ratio_to": None,
            "cash_amount": None,
        }

    @classmethod
    def _parse_bonus(cls, desc: str, desc_lower: str) -> Dict[str, Any]:
        """
        Parses bonus descriptions like 'Bonus 1:1' or 'Bonus 1:2' (1 bonus for 2 existing).
        """
        # Pattern 1: Bonus X:Y (e.g. Bonus 1:1, Bonus 1:2, Bonus 3:1)
        # In Indian markets, Bonus A:B means A bonus shares for every B existing shares held.
        m = re.search(r"bonus\s*(?:issue)?\s*(?:of)?\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", desc_lower)
        if m:
            try:
                bonus_qty = Decimal(m.group(1))
                existing_qty = Decimal(m.group(2))
                if bonus_qty > Decimal("0") and existing_qty > Decimal("0"):
                    # Existing shares = existing_qty, New total shares = existing_qty + bonus_qty
                    ratio_from = existing_qty
                    ratio_to = existing_qty + bonus_qty
                    return {
                        "action_type": "bonus",
                        "processing_status": "verified",
                        "review_reason": None,
                        "ratio_from": ratio_from,
                        "ratio_to": ratio_to,
                        "cash_amount": None,
                    }
            except (InvalidOperation, ValueError):
                pass

        # Pattern 2: 'Bonus issue of X equity shares for every Y equity shares held'
        m2 = re.search(r"(\d+(?:\.\d+)?)\s*(?:equity\s*)?shares?\s*for\s*(?:every\s*)?(\d+(?:\.\d+)?)", desc_lower)
        if m2:
            try:
                bonus_qty = Decimal(m2.group(1))
                existing_qty = Decimal(m2.group(2))
                if bonus_qty > Decimal("0") and existing_qty > Decimal("0"):
                    ratio_from = existing_qty
                    ratio_to = existing_qty + bonus_qty
                    return {
                        "action_type": "bonus",
                        "processing_status": "verified",
                        "review_reason": None,
                        "ratio_from": ratio_from,
                        "ratio_to": ratio_to,
                        "cash_amount": None,
                    }
            except (InvalidOperation, ValueError):
                pass

        return {
            "action_type": "bonus",
            "processing_status": "manual_review",
            "review_reason": "Could not reliably extract bonus ratio",
            "ratio_from": None,
            "ratio_to": None,
            "cash_amount": None,
        }

    @classmethod
    def _parse_dividend(cls, desc: str, desc_lower: str) -> Dict[str, Any]:
        """
        Parses dividend descriptions like 'Dividend - Rs 5.50 Per Share' or 'Interim Dividend Rs 10'.
        """
        m = re.search(r"rs\.?\s*(\d+(?:\.\d+)?)", desc_lower)
        cash_amount = None
        if m:
            try:
                cash_amount = Decimal(m.group(1))
            except (InvalidOperation, ValueError):
                pass

        return {
            "action_type": "cash_dividend",
            "processing_status": "verified" if cash_amount is not None else "manual_review",
            "review_reason": None if cash_amount is not None else "Could not extract cash dividend amount",
            "ratio_from": None,
            "ratio_to": None,
            "cash_amount": cash_amount,
        }
