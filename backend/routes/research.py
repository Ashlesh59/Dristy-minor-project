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
from models.security import Security
from routes.auth import get_current_user
from services.market_data_service import MarketDataService
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
    generate_deterministic_analysis,
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


from models.company import Company
from models.security import Security


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

    raw_security_id = data.get("security_id")
    if raw_security_id is None or not isinstance(raw_security_id, int):
        return jsonify({
            "success": False,
            "message": "security_id (integer) is required for new research requests."
        }), 400

    research_type = (data.get("research_type") or "general").strip() or "general"

    # Query the authoritative Security and Company from the local database
    security = db.session.get(Security, raw_security_id)
    if not security or not security.is_active or not security.company or not security.company.is_active:
        return jsonify({
            "success": False,
            "message": "Security not found or is no longer active."
        }), 404

    # Server controls and populates company_name and ticker_symbol from verified database rows
    new_research = Research(
        user_id=user.id,
        company_id=security.company.id,
        security_id=security.id,
        company_name=security.company.display_name,
        ticker_symbol=security.symbol,
        research_type=research_type,
        status="pending",
    )

    db.session.add(new_research)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Research request created successfully.",
        "research": new_research.to_dict(),
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

    # Prioritize verified local database Bhavcopy market data
    sec = None
    if record.security_id:
        sec = db.session.get(Security, record.security_id)
    if not sec and record.ticker_symbol:
        sec = Security.query.filter_by(symbol=record.ticker_symbol.upper()).first()

    if sec:
        try:
            latest_summary = MarketDataService.get_market_summary(sec.id)
            if latest_summary and latest_summary.get("summary") and latest_summary["summary"].get("close"):
                s = latest_summary["summary"]
                chg_pct = f"{s.get('day_change_percent')}%" if s.get("day_change_percent") is not None else ""
                financial_data = {
                    "symbol": sec.symbol,
                    "price": str(s.get("close") or ""),
                    "change": str(s.get("day_change") or ""),
                    "change_percent": chg_pct,
                    "open": str(s.get("open") or ""),
                    "high": str(s.get("high") or ""),
                    "low": str(s.get("low") or ""),
                    "previous_close": str(s.get("previous_close") or ""),
                    "volume": str(s.get("volume") or ""),
                    "currency": sec.currency or "INR",
                    "source": "NSE Bhavcopy"
                }
                record.financial_data = json.dumps(financial_data)
                db.session.commit()
                return jsonify({
                    "success": True,
                    "research_id": record.id,
                    "ticker_symbol": record.ticker_symbol,
                    "financial_data": financial_data
                }), 200
        except Exception as e:
            current_app.logger.warning("Local market data lookup non-fatal error: %s", e)

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
        # Prioritize verified local database Bhavcopy market data
        sec = None
        if record.security_id:
            sec = db.session.get(Security, record.security_id)
        if not sec and record.ticker_symbol:
            sec = Security.query.filter_by(symbol=record.ticker_symbol.upper()).first()

        if sec:
            try:
                latest_summary = MarketDataService.get_market_summary(sec.id)
                if latest_summary and latest_summary.get("summary") and latest_summary["summary"].get("close"):
                    s = latest_summary["summary"]
                    chg_pct = f"{s.get('day_change_percent')}%" if s.get("day_change_percent") is not None else ""
                    financial_data = {
                        "symbol": sec.symbol,
                        "price": str(s.get("close") or ""),
                        "change": str(s.get("day_change") or ""),
                        "change_percent": chg_pct,
                        "open": str(s.get("open") or ""),
                        "high": str(s.get("high") or ""),
                        "low": str(s.get("low") or ""),
                        "previous_close": str(s.get("previous_close") or ""),
                        "volume": str(s.get("volume") or ""),
                        "vwap": str(s.get("vwap") or ""),
                        "week_52_high": str(s.get("week_52_high") or ""),
                        "week_52_low": str(s.get("week_52_low") or ""),
                        "sma_20": str(s.get("sma_20") or ""),
                        "sma_50": str(s.get("sma_50") or ""),
                        "average_volume_30": str(s.get("average_volume_30") or ""),
                        "volatility": str(s.get("volatility") or ""),
                        "returns": s.get("returns") or {},
                        "coverage": s.get("coverage") or {},
                        "currency": sec.currency or "INR",
                        "source": "NSE Bhavcopy",
                        "source_date": s.get("trading_date"),
                    }
                    record.financial_data = json.dumps(financial_data)
                    db.session.commit()
            except Exception as e:
                current_app.logger.warning("Local market data lookup non-fatal error: %s", e)

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
                    financial_data = {"symbol": record.ticker_symbol, "currency": "INR"}

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
    except (AIMissingApiKeyError, AIServiceUnavailableError, AIServiceBadResponseError, Exception) as e:
        current_app.logger.warning("AI service fallback to deterministic data-driven report: %s", e)
        analysis = generate_deterministic_analysis(
            company_name=record.company_name,
            ticker_symbol=record.ticker_symbol,
            financial_data=financial_data,
            news_articles=news_articles,
        )

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
