"""
services/news_service.py
--------------------------------------------------------------------------
Wraps the Alpha Vantage NEWS_SENTIMENT endpoint for a single stock
ticker.

Structured the same way as services/financial_service.py -- same
error-type pattern, same "read the key at call time, never store or
log it" rule -- so anyone already familiar with that file will
recognize this one immediately. As with financial_service.py, this is
the only file that knows Alpha Vantage's NEWS_SENTIMENT shape; routes
just call get_ticker_news(ticker) and get back a clean list or one of
the exceptions below.
--------------------------------------------------------------------------
"""

import os

import requests

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

REQUEST_TIMEOUT_SECONDS = 10

# How many articles to return -- NEWS_SENTIMENT can return a lot of
# items; capping this keeps the response small and fast for the
# frontend to render without needing its own pagination yet.
MAX_ARTICLES = 10


class NewsServiceError(Exception):
    """Base class for every error this service can raise."""


class MissingApiKeyError(NewsServiceError):
    """ALPHA_VANTAGE_API_KEY isn't set in the environment."""


class NewsServiceUnavailableError(NewsServiceError):
    """Couldn't reach Alpha Vantage at all -- network/timeout/DNS
    issue, or Alpha Vantage itself is rate-limiting/throttling us."""


class NewsServiceBadResponseError(NewsServiceError):
    """Alpha Vantage responded, but with something other than a
    valid, parseable news list -- a malformed body, an error message
    field, or no articles for a ticker it doesn't recognize."""


def get_ticker_news(ticker_symbol):
    """
    Fetches and normalizes recent news + sentiment for `ticker_symbol`
    from Alpha Vantage's NEWS_SENTIMENT endpoint.

    Returns a list of dicts shaped like:
        {
            "title": "...",
            "summary": "...",
            "source": "...",
            "url": "...",
            "published_at": "...",
            "sentiment": "Bullish",
            "sentiment_score": 0.35
        }

    An empty list is a normal, valid result (a real ticker with no
    recent news) -- NOT an error. Raises MissingApiKeyError,
    NewsServiceUnavailableError, or NewsServiceBadResponseError on
    actual failure, same pattern as financial_service.get_stock_quote().
    """
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "ALPHA_VANTAGE_API_KEY is not configured in the environment."
        )

    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": ticker_symbol,
        "apikey": api_key,
    }

    try:
        response = requests.get(
            ALPHA_VANTAGE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.Timeout as exc:
        raise NewsServiceUnavailableError(
            "Timed out waiting for a response from Alpha Vantage."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise NewsServiceUnavailableError(
            "Could not reach Alpha Vantage."
        ) from exc

    if response.status_code != 200:
        raise NewsServiceBadResponseError(
            f"Alpha Vantage returned unexpected status {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise NewsServiceBadResponseError(
            "Alpha Vantage returned a response that wasn't valid JSON."
        ) from exc

    # Same error-signaling convention as GLOBAL_QUOTE: Alpha Vantage
    # answers 200 either way and puts the real problem inside the body.
    if "Error Message" in payload:
        raise NewsServiceBadResponseError(
            f"Alpha Vantage could not find news for ticker '{ticker_symbol}'."
        )

    if "Note" in payload or "Information" in payload:
        raise NewsServiceUnavailableError(
            "Alpha Vantage rate limit reached. Please try again shortly."
        )

    articles = payload.get("feed")

    # No "feed" key at all means something unexpected about the
    # response shape -- different from a real, valid empty result.
    if articles is None:
        raise NewsServiceBadResponseError(
            "Alpha Vantage response was missing the expected news feed."
        )

    normalized = []
    for item in articles[:MAX_ARTICLES]:
        # Each article carries its own per-ticker sentiment breakdown
        # under "ticker_sentiment" (a list, one entry per ticker
        # mentioned in that article) in addition to an overall
        # article-level sentiment. Prefer the ticker-specific score
        # when this specific ticker appears in that list -- it's more
        # relevant than the article's overall sentiment when an
        # article mentions several companies -- and fall back to the
        # overall score otherwise.
        ticker_sentiment = None
        for ts in item.get("ticker_sentiment", []):
            if ts.get("ticker") == ticker_symbol:
                ticker_sentiment = ts
                break

        if ticker_sentiment:
            sentiment_label = ticker_sentiment.get("ticker_sentiment_label")
            sentiment_score = ticker_sentiment.get("ticker_sentiment_score")
        else:
            sentiment_label = item.get("overall_sentiment_label")
            sentiment_score = item.get("overall_sentiment_score")

        normalized.append({
            "title": item.get("title"),
            "summary": item.get("summary"),
            "source": item.get("source"),
            "url": item.get("url"),
            "published_at": item.get("time_published"),
            "sentiment": sentiment_label,
            "sentiment_score": sentiment_score,
        })

    return normalized
