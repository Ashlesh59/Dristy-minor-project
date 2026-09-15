"""
services/ai_service.py
--------------------------------------------------------------------------
Wraps Google's Gemini API to turn a research record's financial data +
news into a short, structured AI analysis.

Structured the same way as services/financial_service.py and
services/news_service.py: this is the only file that knows Gemini
exists, the key is read from the environment at call time (never
hardcoded, never returned, never logged), and callers get back either
a clean dict or one of the exceptions below to translate into an HTTP
response. This file does NOT call financial_service.py or
news_service.py itself -- routes/research.py already has that data
from its own calls to those services and simply passes it in here, so
each service still only knows about its own single external API.
--------------------------------------------------------------------------
"""

import json
import os

from google import genai
from google.genai import errors as genai_errors
from google.genai.types import GenerateContentConfig

# Primary and fallback models for Gemini API
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]
GEMINI_MODEL = "gemini-2.5-flash"

REQUIRED_FIELDS = [
    "summary",
    "financial_assessment",
    "news_sentiment",
    "key_risks",
    "key_opportunities",
    "overall_outlook",
]

# ai_score/recommendation are handled separately from REQUIRED_FIELDS
# (which are all plain strings): ai_score is coerced to an int 0-100
# and recommendation is constrained to one of RECOMMENDATION_VALUES,
# each with its own validation/fallback below, rather than being
# accepted as free-form Gemini output.
RECOMMENDATION_VALUES = {"Buy", "Hold", "Sell"}


class AIServiceError(Exception):
    """Base class for every error this service can raise."""


class MissingApiKeyError(AIServiceError):
    """GEMINI_API_KEY isn't set in the environment."""


class AIServiceUnavailableError(AIServiceError):
    """Couldn't reach Gemini, or Gemini itself is rate-limiting /
    temporarily erroring on its end."""


class AIServiceBadResponseError(AIServiceError):
    """Gemini responded, but the content wasn't usable -- empty,
    not valid JSON, or missing one of the fields this service
    requires."""


def _build_prompt(company_name, ticker_symbol, financial_data, news_articles):
    """
    Assembles the prompt sent to Gemini.
    Instructs the AI to act as a seasoned financial analyst, synthesizing real-time market data,
    news sentiment, and fundamental domain knowledge about the company to produce unique,
    actionable insights and distinct confidence scores.
    """
    news_lines = "\n".join(
        f"- {a.get('title')} (sentiment: {a.get('sentiment')})"
        for a in (news_articles or [])
    ) or "No recent news headlines available."

    return f"""You are an expert equity research analyst. Provide an insightful, realistic, and company-specific investment analysis for the following company based on the provided live market data, news sentiment, and your comprehensive knowledge of this company's business model, industry standing, competitors, and fundamentals.

Company: {company_name}
Ticker: {ticker_symbol}

Live Financial Data:
{json.dumps(financial_data or {}, indent=2)}

Recent News & Sentiment:
{news_lines}

Instructions:
1. Provide a sharp, tailored analysis unique to {company_name} ({ticker_symbol}).
2. Evaluate real valuation, recent price action/momentum, competitive moats, growth catalysts, and macro/regulatory risks.
3. Calculate a realistic, differentiated AI confidence score (0-100) reflecting your holistic assessment of the company's investment appeal and risk/reward profile.
4. Give a definitive recommendation: Buy, Hold, or Sell.

Respond with ONLY a single JSON object (no markdown formatting, no backticks, no extra text) with exactly these keys:
{{
  "summary": "2-3 crisp sentences summarizing the company's business and current market posture",
  "financial_assessment": "2-3 sentences evaluating the current stock price, recent performance, trading volume, and financial health",
  "news_sentiment": "1-2 sentences on recent market sentiment, sector trends, or public perception",
  "key_risks": "2-3 key headwinds, risks, or competitive threats specific to this company",
  "key_opportunities": "2-3 growth catalysts, market expansion opportunities, or competitive advantages",
  "overall_outlook": "2-3 sentences providing a clear forward-looking investment thesis",
  "ai_score": 78,
  "recommendation": "Buy"
}}
"""


def generate_research_analysis(company_name, ticker_symbol, financial_data, news_articles):
    """
    Calls Gemini with the given company context, financial data, and
    news, and returns a dict with exactly the keys in REQUIRED_FIELDS.

    Raises MissingApiKeyError, AIServiceUnavailableError, or
    AIServiceBadResponseError on failure, same pattern as the other
    two services' get_*() functions.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "GEMINI_API_KEY is not configured in the environment."
        )

    client = genai.Client(api_key=api_key)
    prompt = _build_prompt(company_name, ticker_symbol, financial_data, news_articles)

    last_error = None
    response = None
    for model_name in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            if response and getattr(response, "text", None):
                break
        except (genai_errors.ClientError, genai_errors.ServerError, genai_errors.APIError, Exception) as exc:
            last_error = exc
            continue

    if not response or not getattr(response, "text", None):
        if last_error:
            raise AIServiceUnavailableError(f"Gemini error: {last_error}") from last_error
        raise AIServiceBadResponseError("Gemini returned an empty response.")

    raw_text = getattr(response, "text", None)
    if not raw_text:
        raise AIServiceBadResponseError("Gemini returned an empty response.")

    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    try:
        parsed = json.loads(raw_text)
    except (ValueError, TypeError) as exc:
        raise AIServiceBadResponseError(
            "Gemini response was not valid JSON."
        ) from exc

    if not isinstance(parsed, dict):
        raise AIServiceBadResponseError("Gemini response was not a JSON object.")

    # Fill any missing required string fields with graceful defaults rather than crashing
    result = {}
    for field in REQUIRED_FIELDS:
        val = parsed.get(field)
        if val is not None and str(val).strip():
            result[field] = str(val).strip()
        else:
            result[field] = f"Analysis for {field.replace('_', ' ')} is currently being updated."

    # ai_score/recommendation are validated (not just cast) rather than
    # trusted outright, since a value outside 0-100 or outside
    # {Buy, Hold, Sell} would be actively misleading in the UI. If
    # Gemini's response doesn't include a usable value for either, we
    # leave it as None -- the frontend/report treat that as "not
    # available," never as a fabricated default score/recommendation.
    ai_score = None
    try:
        raw_score = int(parsed.get("ai_score"))
        if 0 <= raw_score <= 100:
            ai_score = raw_score
    except (TypeError, ValueError):
        ai_score = None
    result["ai_score"] = ai_score

    raw_recommendation = str(parsed.get("recommendation") or "").strip().title()
    result["recommendation"] = (
        raw_recommendation if raw_recommendation in RECOMMENDATION_VALUES else None
    )

    return result
