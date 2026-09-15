"""
services/importer/isin_validator.py
--------------------------------------------------------------------------
ISO 6166 ISIN format and Luhn-based check-digit validator.
--------------------------------------------------------------------------
"""

import re
from typing import Tuple


ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def calculate_isin_check_digit(isin_body: str) -> int:
    """
    Calculates the ISO 6166 Luhn check digit for an 11-character ISIN prefix.
    1. Converts letters A-Z to numbers 10-35.
    2. Doubles digits in alternating positions from right to left.
    3. Sums all individual digits.
    4. Computes (10 - (sum % 10)) % 10.
    """
    digits_str = ""
    for char in isin_body.upper():
        if char.isalpha():
            digits_str += str(ord(char) - ord("A") + 10)
        else:
            digits_str += char

    total = 0
    # Double every second digit from right to left (starting with the rightmost digit of the converted string)
    reverse_digits = digits_str[::-1]
    for idx, d_char in enumerate(reverse_digits):
        d = int(d_char)
        if idx % 2 == 0:
            doubled = d * 2
            total += (doubled // 10) + (doubled % 10)
        else:
            total += d

    return (10 - (total % 10)) % 10


def validate_isin(isin_str: str, expected_country: str = "IN") -> Tuple[bool, str]:
    """
    Validates an ISIN string.
    Returns (True, "") if valid, or (False, error_reason).
    """
    if not isin_str:
        return True, ""  # Nullable / optional in source

    clean_isin = isin_str.strip().upper()

    if len(clean_isin) != 12:
        return False, f"ISIN must be exactly 12 characters, got '{clean_isin}' (length {len(clean_isin)})"

    if not ISIN_REGEX.match(clean_isin):
        return False, f"ISIN '{clean_isin}' does not match standard alphanumeric pattern (2 letters + 9 alphanumeric + 1 digit)"

    country_code = clean_isin[:2]
    if expected_country and country_code != expected_country:
        return False, f"ISIN '{clean_isin}' country code '{country_code}' does not match expected '{expected_country}'"

    # Verify Luhn Check Digit
    expected_check_digit = calculate_isin_check_digit(clean_isin[:11])
    actual_check_digit = int(clean_isin[11])

    if actual_check_digit != expected_check_digit:
        return False, (
            f"ISIN '{clean_isin}' has invalid Luhn check digit (expected {expected_check_digit}, got {actual_check_digit})"
        )

    return True, ""
