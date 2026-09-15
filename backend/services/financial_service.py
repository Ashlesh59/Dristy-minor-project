"""
services/financial_service.py
--------------------------------------------------------------------------
Wraps the Alpha Vantage GLOBAL_QUOTE endpoint for a single stock ticker.

This is the ONLY file that knows Alpha Vantage exists -- its URL, its
response shape, its quirks. routes/research.py just calls
get_stock_quote(ticker) and gets back either a clean, normalized dict
or one of the exceptions below. That separation means if the project
ever swaps or adds another data provider later, only this file needs
to change, not the route.

The API key is read from the ALPHA_VANTAGE_API_KEY environment
variable at call time -- never hardcoded, never returned in any
response, never logged.
--------------------------------------------------------------------------
"""

import os

import requests

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

# A generous but finite timeout -- long enough for a normal Alpha
# Vantage response, short enough that a hung connection doesn't leave
# a Flask request (and the person waiting on it) stuck indefinitely.
REQUEST_TIMEOUT_SECONDS = 10


class FinancialServiceError(Exception):
    """Base class for every error this service can raise, so routes
    can catch just this one type if they don't need to distinguish
    the specific cause."""


class MissingApiKeyError(FinancialServiceError):
    """ALPHA_VANTAGE_API_KEY isn't set in the environment."""


class FinancialServiceUnavailableError(FinancialServiceError):
    """Couldn't reach Alpha Vantage at all -- network/timeout/DNS
    issue, or Alpha Vantage itself is rate-limiting/throttling us."""


class FinancialServiceBadResponseError(FinancialServiceError):
    """Alpha Vantage responded, but with something other than a
    valid, parseable quote -- a malformed body, an error message
    field, or (most commonly) an empty result for a ticker it doesn't
    recognize."""


def get_stock_quote(ticker_symbol):
    """
    Fetches and normalizes a real-time quote for `ticker_symbol` from
    Alpha Vantage's GLOBAL_QUOTE endpoint.

    Returns a dict shaped like:
        {
            "symbol": "AAPL",
            "price": "...",
            "change": "...",
            "change_percent": "...",
            "volume": "...",
            "latest_trading_day": "..."
        }

    Raises MissingApiKeyError, FinancialServiceUnavailableError, or
    FinancialServiceBadResponseError on failure -- callers should
    catch these and translate them into an appropriate HTTP response
    rather than letting a raw exception (or the API key) leak out.
    """
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "ALPHA_VANTAGE_API_KEY is not configured in the environment."
        )

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker_symbol,
        "apikey": api_key,
    }

    try:
        response = requests.get(
            ALPHA_VANTAGE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout as exc:
        raise FinancialServiceUnavailableError(
            "Timed out waiting for a response from Alpha Vantage."
        ) from exc
    except requests.exceptions.RequestException as exc:
        # Covers connection errors, DNS failures, etc. -- anything
        # that means the HTTP request itself never completed.
        raise FinancialServiceUnavailableError(
            "Could not reach Alpha Vantage."
        ) from exc

    if response.status_code != 200:
        raise FinancialServiceBadResponseError(
            f"Alpha Vantage returned unexpected status {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise FinancialServiceBadResponseError(
            "Alpha Vantage returned a response that wasn't valid JSON."
        ) from exc

    # Alpha Vantage doesn't use HTTP status codes for its own errors --
    # it always answers 200 and puts the problem inside the JSON body
    # instead, under one of these keys depending on the situation:
    #   "Error Message" -> the symbol/function combination is invalid
    #   "Note"          -> the per-minute call frequency limit was hit
    #   "Information"   -> the daily call limit was hit (newer wording)
    if "Error Message" in payload:
        raise FinancialServiceBadResponseError(
            f"Alpha Vantage could not find data for ticker '{ticker_symbol}'."
        )

    if "Note" in payload or "Information" in payload:
        raise FinancialServiceUnavailableError(
            "Alpha Vantage rate limit reached. Please try again shortly."
        )

    quote = payload.get("Global Quote")

    # A valid symbol with no error field still comes back as an empty
    # {} for tickers Alpha Vantage simply doesn't recognize -- this is
    # the most common "invalid ticker" case in practice.
    if not quote:
        raise FinancialServiceBadResponseError(
            f"No quote data available for ticker '{ticker_symbol}'."
        )

    try:
        # Detect currency if possible based on symbol suffix
        currency = "USD"
        sym = quote["01. symbol"].upper()
        if sym.endswith(".BSE") or sym.endswith(".NSE") or sym.endswith(".IN") or sym.endswith(".BO") or sym.endswith(".NS"):
            currency = "INR"
        elif sym.endswith(".L") or sym.endswith(".LON"):
            currency = "GBP"
        elif sym.endswith(".TO") or sym.endswith(".TRT"):
            currency = "CAD"
        elif sym.endswith(".AX"):
            currency = "AUD"
        elif sym.endswith(".DE") or sym.endswith(".PA") or sym.endswith(".FR"):
            currency = "EUR"

        return {
            "symbol": quote["01. symbol"],
            "open": quote["02. open"],
            "high": quote["03. high"],
            "low": quote["04. low"],
            "price": quote["05. price"],
            "volume": quote["06. volume"],
            "latest_trading_day": quote["07. latest trading day"],
            "previous_close": quote["08. previous close"],
            "change": quote["09. change"],
            "change_percent": quote["10. change percent"],
            "currency": currency
        }
    except KeyError as exc:
        # Alpha Vantage responded with a "Global Quote" object, but
        # not shaped the way this function expects (e.g. a future API
        # change). Treat it the same as any other bad/unusable
        # response rather than letting a raw KeyError escape.
        raise FinancialServiceBadResponseError(
            "Alpha Vantage response was missing an expected field."
        ) from exc


def search_symbols(keywords):
    """
    Searches for stock tickers and company names using Alpha Vantage SYMBOL_SEARCH endpoint.
    Returns a list of dicts:
    [
        {"symbol": "AAPL", "name": "Apple Inc", "type": "Equity", "region": "United States", "currency": "USD"}
    ]
    """
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "ALPHA_VANTAGE_API_KEY is not configured in the environment."
        )

    params = {
        "function": "SYMBOL_SEARCH",
        "keywords": keywords,
        "apikey": api_key,
    }

    try:
        response = requests.get(
            ALPHA_VANTAGE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout as exc:
        raise FinancialServiceUnavailableError(
            "Timed out waiting for a response from Alpha Vantage."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise FinancialServiceUnavailableError(
            "Could not reach Alpha Vantage."
        ) from exc

    if response.status_code != 200:
        raise FinancialServiceBadResponseError(
            f"Alpha Vantage returned unexpected status {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise FinancialServiceBadResponseError(
            "Alpha Vantage returned a response that wasn't valid JSON."
        ) from exc

    if "Error Message" in payload:
        raise FinancialServiceBadResponseError(
            f"Alpha Vantage search failed for '{keywords}'."
        )

    if "Note" in payload or "Information" in payload:
        raise FinancialServiceUnavailableError(
            "Alpha Vantage rate limit reached. Please try again shortly."
        )

    best_matches = payload.get("bestMatches", [])
    results = []
    for match in best_matches:
        results.append({
            "symbol": match.get("1. symbol"),
            "name": match.get("2. name"),
            "type": match.get("3. type"),
            "region": match.get("4. region"),
            "currency": match.get("8. currency")
        })
    return results
