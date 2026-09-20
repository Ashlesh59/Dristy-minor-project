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


def _ensure_record_financial_data(record, allow_live_call=True):
    """
    Guarantees that a research record always has valid financial data.
    1. Checks if record already has valid financial JSON with a price.
    2. Resolves from local Bhavcopy DailyPrice if present.
    3. Falls back to live quote (Alpha Vantage / Yahoo) if needed and allowed.
    4. Persists the result to the record in SQLite.
    """
    if record.financial_data:
        try:
            parsed = json.loads(record.financial_data)
            if parsed and parsed.get("price"):
                return parsed
        except Exception:
            pass

    sec = None
    if record.security_id:
        sec = db.session.get(Security, record.security_id)
    if not sec and record.ticker_symbol:
        sec = Security.query.filter_by(symbol=record.ticker_symbol.upper()).first()

    fin_data = None
    if sec:
        try:
            latest_summary = MarketDataService.get_market_summary(sec.id)
            m = latest_summary.get("market_data") or latest_summary.get("summary")
            if m and m.get("close") and m.get("source") != "Live Market Feed":
                chg_pct = f"{m.get('change_percent')}%" if m.get("change_percent") is not None and not str(m.get("change_percent")).endswith("%") else str(m.get("change_percent") or "")
                fin_data = {
                    "symbol": sec.symbol,
                    "price": str(m.get("close") or ""),
                    "change": str(m.get("change") or ""),
                    "change_percent": chg_pct,
                    "open": str(m.get("open") or ""),
                    "high": str(m.get("high") or ""),
                    "low": str(m.get("low") or ""),
                    "previous_close": str(m.get("previous_close") or ""),
                    "volume": str(m.get("volume") or ""),
                    "vwap": str(m.get("vwap") or ""),
                    "week_52_high": str(m.get("week_52_high") or ""),
                    "week_52_low": str(m.get("week_52_low") or ""),
                    "currency": sec.currency or "INR",
                    "source": "NSE Bhavcopy",
                    "latest_trading_day": m.get("trading_date"),
                }
        except Exception as e:
            current_app.logger.debug("Local market data lookup non-fatal: %s", e)

    if not fin_data and record.ticker_symbol and allow_live_call:
        from flask import current_app
        is_testing = False
        try:
            is_testing = bool(current_app and current_app.config.get("TESTING", False) and not current_app.config.get("ENABLE_LIVE_FALLBACK", False))
        except Exception:
            pass
        if not is_testing:
            try:
                fin_data = get_stock_quote(record.ticker_symbol)
            except Exception as e:
                current_app.logger.debug("Live quote lookup non-fatal: %s", e)

    if fin_data:
        record.financial_data = json.dumps(fin_data)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return fin_data


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
    db.session.flush()

    # Pre-populate local Bhavcopy data if available
    _ensure_record_financial_data(new_research, allow_live_call=False)
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

    # Ensure financial_data is resolved and persisted
    if not record.financial_data or record.financial_data in ("null", "{}"):
        _ensure_record_financial_data(record)

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

    sec = None
    if record.security_id:
        sec = db.session.get(Security, record.security_id)
    if not sec and record.ticker_symbol:
        sec = Security.query.filter_by(symbol=record.ticker_symbol.upper()).first()

    if sec:
        try:
            latest_summary = MarketDataService.get_market_summary(sec.id)
            m = latest_summary.get("market_data") or latest_summary.get("summary")
            if m and m.get("close") and m.get("source") != "Live Market Feed":
                chg_pct = f"{m.get('change_percent')}%" if m.get("change_percent") is not None and not str(m.get("change_percent")).endswith("%") else str(m.get("change_percent") or "")
                financial_data = {
                    "symbol": sec.symbol,
                    "price": str(m.get("close") or ""),
                    "change": str(m.get("change") or ""),
                    "change_percent": chg_pct,
                    "open": str(m.get("open") or ""),
                    "high": str(m.get("high") or ""),
                    "low": str(m.get("low") or ""),
                    "previous_close": str(m.get("previous_close") or ""),
                    "volume": str(m.get("volume") or ""),
                    "currency": sec.currency or "INR",
                    "source": "NSE Bhavcopy",
                    "latest_trading_day": m.get("trading_date"),
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
        news = get_ticker_news(record.ticker_symbol, record.company_name)
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
    If force_refresh=False and analysis_data is present (and not stale), returns cached analysis.
    Otherwise fetches latest data and runs Gemini AI analysis.
    """
    financial_data = _ensure_record_financial_data(record)

    cached_analysis = None
    if not force_refresh and record.analysis_data:
        try:
            cached_analysis = json.loads(record.analysis_data)
            # Invalidate stale placeholder analysis if real financial data is now present
            fin_assessment = str(cached_analysis.get("financial_assessment") or "").lower()
            if financial_data and ("absence of specific live price" in fin_assessment or "no financial data" in fin_assessment or "financial data hasn't been fetched" in fin_assessment):
                cached_analysis = None
        except Exception:
            cached_analysis = None

    if cached_analysis:
        return cached_analysis, None

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
            news_articles = get_ticker_news(record.ticker_symbol, record.company_name)
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


@research_bp.route("/<int:research_id>/report", methods=["POST", "GET"])
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
