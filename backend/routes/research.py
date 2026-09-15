"""
routes/research.py
--------------------------------------------------------------------------
Investment research routes. Phase 5 only stores research *requests* --
no live financial data, no AI analysis. Every route here requires a
logged-in user (via the existing Flask session from routes/auth.py) and
every query is scoped to that user's own records, so nobody can read,
list, or delete another user's research by guessing an id.
--------------------------------------------------------------------------
"""

import json

from flask import Blueprint, request, jsonify, current_app

from database.db import db
from models.research import Research
from routes.auth import get_current_user
from services.financial_service import (
    get_stock_quote,
    search_symbols,
    MissingApiKeyError,
    FinancialServiceUnavailableError,
    FinancialServiceBadResponseError,
)
from services.news_service import (
    get_ticker_news,
    MissingApiKeyError as NewsMissingApiKeyError,
    NewsServiceUnavailableError,
    NewsServiceBadResponseError,
)
from services.ai_service import (
    generate_research_analysis,
    MissingApiKeyError as AIMissingApiKeyError,
    AIServiceUnavailableError,
    AIServiceBadResponseError,
)
from services.report_service import build_investment_report, ReportServiceError
from utils.limiter import rate_limit

research_bp = Blueprint("research", __name__, url_prefix="/api/research")


def login_required_response():
    """
    The one consistent 401 body returned by every route below when
    there's no logged-in user. Kept in a single place so the message
    can't drift between routes.
    """
    return jsonify({
        "success": False,
        "message": "You must be logged in to do that."
    }), 401


POPULAR_SYMBOLS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "NFLX", "name": "Netflix Inc.", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "INTC", "name": "Intel Corporation", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "DIS", "name": "The Walt Disney Company", "type": "Equity", "region": "United States", "currency": "USD"},
    {"symbol": "RELIANCE.BSE", "name": "Reliance Industries", "type": "Equity", "region": "India", "currency": "INR"},
    {"symbol": "TCS.BSE", "name": "Tata Consultancy Services", "type": "Equity", "region": "India", "currency": "INR"},
    {"symbol": "INFY", "name": "Infosys Limited", "type": "Equity", "region": "United States/India", "currency": "USD"},
]


@research_bp.route("/ticker-search", methods=["GET"])
@rate_limit(max_requests=60, window_seconds=60, key_prefix="ticker_search")
def search_ticker():
    user = get_current_user()
    if user is None:
        return login_required_response()

    keywords = (request.args.get("keywords") or request.args.get("q") or "").strip()
    if not keywords:
        return jsonify({
            "success": True,
            "matches": []
        }), 200

    try:
        matches = search_symbols(keywords)
    except (MissingApiKeyError, FinancialServiceUnavailableError, FinancialServiceBadResponseError) as e:
        current_app.logger.warning("Ticker search fallback triggered: %s", e)
        kw_lower = keywords.lower()
        matches = [
            s for s in POPULAR_SYMBOLS
            if kw_lower in s["symbol"].lower() or kw_lower in s["name"].lower()
        ]

    return jsonify({
        "success": True,
        "matches": matches
    }), 200


@research_bp.route("", methods=["POST"])
def create_research():
    user = get_current_user()
    if user is None:
        return login_required_response()

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "message": "Request body must be valid JSON."
        }), 400

    company_name = (data.get("company_name") or "").strip()
    ticker_symbol = (data.get("ticker_symbol") or "").strip().upper()
    # research_type is optional -- Research.research_type already
    # defaults to "general" at the database level, but we still handle
    # it explicitly here so an empty string in the request body (e.g.
    # `"research_type": ""`) falls back to "general" too, rather than
    # being saved as blank.
    research_type = (data.get("research_type") or "general").strip() or "general"

    if not company_name:
        return jsonify({
            "success": False,
            "message": "company_name is required."
        }), 400

    if not ticker_symbol:
        return jsonify({
            "success": False,
            "message": "ticker_symbol is required."
        }), 400

    # user_id always comes from the logged-in session, never from the
    # request body -- this is what stops a client from creating a
    # research record "as" another user.
    new_research = Research(
        user_id=user.id,
        company_name=company_name,
        ticker_symbol=ticker_symbol,
        research_type=research_type,
        status="pending",
    )

    db.session.add(new_research)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Research request created",
        "research": new_research.to_dict()
    }), 201


@research_bp.route("", methods=["GET"])
def list_research():
    user = get_current_user()
    if user is None:
        return login_required_response()

    # Scoped with filter_by(user_id=user.id) -- this is what makes
    # sure the response only ever contains this user's own records,
    # regardless of how many other users' research exists in the
    # table.
    records = Research.query.filter_by(user_id=user.id).order_by(
        Research.created_at.desc()
    ).all()

    # include_details=False: the list view (dashboard, saved reports)
    # never needs the full persisted financial/news/analysis/report
    # JSON blobs, just enough to render a card/row -- see
    # Research.to_dict().
    return jsonify({
        "success": True,
        "research": [r.to_dict(include_details=False) for r in records]
    }), 200


@research_bp.route("/stats", methods=["GET"])
def get_research_stats():
    """
    Returns aggregated research and search counts from the database for the current user.
    """
    user = get_current_user()
    if user is None:
        return login_required_response()

    records = Research.query.filter_by(user_id=user.id).all()
    total_searches = len(records)
    completed_reports = sum(1 for r in records if r.status == "completed")
    distinct_companies = len(set(r.ticker_symbol for r in records))
    
    scored = [r.ai_score for r in records if r.ai_score is not None]
    average_score = round(sum(scored) / len(scored)) if scored else None

    return jsonify({
        "success": True,
        "stats": {
            "total_searches": total_searches,
            "completed_reports": completed_reports,
            "distinct_companies": distinct_companies,
            "average_score": average_score
        }
    }), 200


@research_bp.route("/<int:research_id>", methods=["GET"])
def get_research(research_id):
    user = get_current_user()
    if user is None:
        return login_required_response()

    # Filtering by BOTH id and user_id in the same query -- rather
    # than fetching by id alone and checking ownership afterwards --
    # means a request for someone else's research id looks identical
    # to a request for an id that doesn't exist at all: both come back
    # empty, and both get the same 404 below. That's deliberate, for
    # the same reason login gives one generic error either way: it
    # avoids confirming to a client whether a given id belongs to
    # *someone* (just not them) versus not existing at all.
    record = Research.query.filter_by(id=research_id, user_id=user.id).first()

    if record is None:
        return jsonify({
            "success": False,
            "message": "Research not found."
        }), 404

    return jsonify({
        "success": True,
        "research": record.to_dict()
    }), 200


@research_bp.route("/<int:research_id>", methods=["DELETE"])
def delete_research(research_id):
    user = get_current_user()
    if user is None:
        return login_required_response()

    record = Research.query.filter_by(id=research_id, user_id=user.id).first()

    if record is None:
        return jsonify({
            "success": False,
            "message": "Research not found."
        }), 404

    db.session.delete(record)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Research deleted"
    }), 200


@research_bp.route("/<int:research_id>/financials", methods=["GET"])
def get_research_financials(research_id):
    """
    Phase 6: fetches a live quote for the ticker on an existing
    research record. This doesn't store anything new -- it's a
    read-through to Alpha Vantage each time it's called, scoped to a
    research record the logged-in user actually owns.
    """
    user = get_current_user()
    if user is None:
        return login_required_response()

    # Same ownership-scoped lookup as get_research()/delete_research()
    # above -- an id that exists but belongs to someone else looks
    # identical to one that doesn't exist at all.
    record = Research.query.filter_by(id=research_id, user_id=user.id).first()
    if record is None:
        return jsonify({
            "success": False,
            "message": "Research not found."
        }), 404

    try:
        financial_data = get_stock_quote(record.ticker_symbol)
    except MissingApiKeyError as e:
        # Server misconfiguration, not the user's fault -- log the
        # real reason for whoever's running the server, but never put
        # it (or the missing key itself) in the response.
        current_app.logger.error("Financial service misconfigured: %s", e)
        return jsonify({
            "success": False,
            "message": "Financial data is temporarily unavailable. Please try again later."
        }), 500
    except FinancialServiceUnavailableError as e:
        current_app.logger.warning("Financial service unavailable: %s", e)
        return jsonify({
            "success": False,
            "message": "Financial data provider is temporarily unavailable. Please try again shortly."
        }), 503
    except FinancialServiceBadResponseError as e:
        current_app.logger.warning("Financial service bad response: %s", e)
        return jsonify({
            "success": False,
            "message": "Could not retrieve financial data for this ticker."
        }), 502

    # Persist the real, just-fetched quote on the research record so a
    # later page load (e.g. reopening a saved report) can show the
    # last-known real data without necessarily re-calling Alpha
    # Vantage. This never invents a value -- it only stores exactly
    # what the provider returned.
    record.financial_data = json.dumps(financial_data)
    db.session.commit()

    return jsonify({
        "success": True,
        "research_id": record.id,
        "ticker_symbol": record.ticker_symbol,
        "financial_data": financial_data
    }), 200


@research_bp.route("/<int:research_id>/news", methods=["GET"])
def get_research_news(research_id):
    """
    Phase 7: fetches recent news + sentiment for the ticker on an
    existing research record. Same shape as get_research_financials()
    above -- a read-through to Alpha Vantage each time, scoped to a
    research record the logged-in user actually owns.
    """
    user = get_current_user()
    if user is None:
        return login_required_response()

    record = Research.query.filter_by(id=research_id, user_id=user.id).first()
    if record is None:
        return jsonify({
            "success": False,
            "message": "Research not found."
        }), 404

    try:
        news = get_ticker_news(record.ticker_symbol)
    except NewsMissingApiKeyError as e:
        current_app.logger.error("News service misconfigured: %s", e)
        return jsonify({
            "success": False,
            "message": "News data is temporarily unavailable. Please try again later."
        }), 500
    except NewsServiceUnavailableError as e:
        current_app.logger.warning("News service unavailable: %s", e)
        return jsonify({
            "success": False,
            "message": "News provider is temporarily unavailable. Please try again shortly."
        }), 503
    except NewsServiceBadResponseError as e:
        current_app.logger.warning("News service bad response: %s", e)
        return jsonify({
            "success": False,
            "message": "Could not retrieve news for this ticker."
        }), 502

    record.news_data = json.dumps(news)
    db.session.commit()

    return jsonify({
        "success": True,
        "research_id": record.id,
        "ticker_symbol": record.ticker_symbol,
        "news": news
    }), 200


def _get_analysis_or_error(record, force_refresh=False):
    """
    Retrieves or generates analysis for a research record.
    If force_refresh=False and analysis_data is present, returns cached analysis.
    Otherwise fetches latest data and runs Gemini AI analysis.
    """
    if not force_refresh and record.analysis_data:
        try:
            return json.loads(record.analysis_data), None
        except Exception:
            pass

    financial_data = None
    if not force_refresh and record.financial_data:
        try:
            financial_data = json.loads(record.financial_data)
        except Exception:
            pass

    if not financial_data:
        try:
            financial_data = get_stock_quote(record.ticker_symbol)
            record.financial_data = json.dumps(financial_data)
            db.session.commit()
        except (MissingApiKeyError, FinancialServiceUnavailableError, FinancialServiceBadResponseError) as e:
            current_app.logger.warning("Financial service non-fatal fallback: %s", e)
            if record.financial_data:
                try:
                    financial_data = json.loads(record.financial_data)
                except Exception:
                    financial_data = None
            if not financial_data:
                financial_data = {"symbol": record.ticker_symbol, "currency": "USD"}

    news_articles = []
    if not force_refresh and record.news_data:
        try:
            news_articles = json.loads(record.news_data)
        except Exception:
            pass

    if not news_articles:
        try:
            news_articles = get_ticker_news(record.ticker_symbol)
            if news_articles:
                record.news_data = json.dumps(news_articles)
                db.session.commit()
        except (NewsMissingApiKeyError, NewsServiceUnavailableError, NewsServiceBadResponseError) as e:
            current_app.logger.warning("News service non-fatal error: %s", e)
            news_articles = []

    try:
        analysis = generate_research_analysis(
            company_name=record.company_name,
            ticker_symbol=record.ticker_symbol,
            financial_data=financial_data,
            news_articles=news_articles,
        )
    except AIMissingApiKeyError as e:
        current_app.logger.error("AI service misconfigured: %s", e)
        return None, (jsonify({
            "success": False,
            "message": "AI analysis is temporarily unavailable. Please try again later."
        }), 500)
    except AIServiceUnavailableError as e:
        current_app.logger.warning("AI service unavailable: %s", e)
        return None, (jsonify({
            "success": False,
            "message": "AI analysis provider is temporarily unavailable. Please try again shortly."
        }), 503)
    except AIServiceBadResponseError as e:
        current_app.logger.warning("AI service bad response: %s", e)
        return None, (jsonify({
            "success": False,
            "message": "Could not generate an analysis for this research."
        }), 502)

    return analysis, None


@research_bp.route("/<int:research_id>/analyze", methods=["POST"])
@rate_limit(max_requests=15, window_seconds=60, key_prefix="research_analyze")
def analyze_research(research_id):
    """
    Phase 8: generates a structured AI analysis for a research record.
    Generates a fresh analysis with Gemini when called.
    """
    user = get_current_user()
    if user is None:
        return login_required_response()

    record = Research.query.filter_by(id=research_id, user_id=user.id).first()
    if record is None:
        return jsonify({
            "success": False,
            "message": "Research not found."
        }), 404

    analysis, error = _get_analysis_or_error(record, force_refresh=True)
    if error is not None:
        return error

    # Persist the real Gemini-generated analysis and set status to completed
    record.analysis_data = json.dumps(analysis)
    record.report_data = None  # Invalidate previous report cache so report reflects new analysis
    record.ai_score = analysis.get("ai_score")
    record.recommendation = analysis.get("recommendation")
    record.status = "completed"
    db.session.commit()

    return jsonify({
        "success": True,
        "research_id": record.id,
        "ticker_symbol": record.ticker_symbol,
        "analysis": analysis
    }), 200


@research_bp.route("/<int:research_id>/report", methods=["POST"])
@rate_limit(max_requests=15, window_seconds=60, key_prefix="research_report")
def generate_report(research_id):
    """
    Phase 9: turns AI analysis into a fuller, structured investment report.
    Reuses existing report_data or analysis_data if already generated.
    """
    user = get_current_user()
    if user is None:
        return login_required_response()

    record = Research.query.filter_by(id=research_id, user_id=user.id).first()
    if record is None:
        return jsonify({
            "success": False,
            "message": "Research not found."
        }), 404

    if record.report_data:
        try:
            report = json.loads(record.report_data)
            return jsonify({
                "success": True,
                "research_id": record.id,
                "ticker_symbol": record.ticker_symbol,
                "report": report
            }), 200
        except Exception:
            pass

    analysis, error = _get_analysis_or_error(record)
    if error is not None:
        return error

    try:
        report = build_investment_report(
            company_name=record.company_name,
            ticker_symbol=record.ticker_symbol,
            analysis=analysis,
        )
    except ReportServiceError as e:
        current_app.logger.warning("Report service error: %s", e)
        return jsonify({
            "success": False,
            "message": "Could not generate a report for this research."
        }), 502

    record.analysis_data = json.dumps(analysis)
    record.report_data = json.dumps(report)
    record.ai_score = analysis.get("ai_score")
    record.recommendation = analysis.get("recommendation")
    record.status = "completed"
    db.session.commit()

    return jsonify({
        "success": True,
        "research_id": record.id,
        "ticker_symbol": record.ticker_symbol,
        "report": report
    }), 200
