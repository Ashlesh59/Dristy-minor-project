"""
routes/companies.py
--------------------------------------------------------------------------
Local Company & Security discovery routes.
Protected by session authentication.
--------------------------------------------------------------------------
"""

import re
from flask import Blueprint, request, jsonify

from routes.auth import get_current_user
from services.company_search_service import CompanySearchService
from utils.limiter import rate_limit

companies_bp = Blueprint("companies", __name__, url_prefix="/api/companies")


def _login_required_response():
    return jsonify({
        "success": False,
        "message": "You must be logged in to do that."
    }), 401


FILTER_FORMAT_REGEX = re.compile(r"^[A-Za-z0-9_\-\s]{1,30}$")


@companies_bp.route("/search", methods=["GET"])
@rate_limit(max_requests=60, window_seconds=60, key_prefix="company_search")
def search_companies():
    user = get_current_user()
    if user is None:
        return _login_required_response()

    raw_q = request.args.get("q")
    if raw_q is None:
        return jsonify({
            "success": False,
            "message": "Query parameter 'q' is required."
        }), 400

    clean_q = raw_q.strip()
    if not clean_q:
        return jsonify({
            "success": False,
            "message": "Query parameter 'q' cannot be empty."
        }), 400

    # 1-character rule: allowed only if alphanumeric for exact ticker lookup
    if len(clean_q) < 2:
        if not (len(clean_q) == 1 and clean_q.isalnum()):
            return jsonify({
                "success": False,
                "message": "Search query must be at least 2 characters long."
            }), 400

    # Limit validation
    raw_limit = request.args.get("limit", "10")
    try:
        limit_val = int(raw_limit)
        if limit_val < 1:
            return jsonify({
                "success": False,
                "message": "Limit must be a positive integer between 1 and 20."
            }), 400
        limit = min(limit_val, 20)
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid limit parameter. Must be an integer."
        }), 400

    # Filter validations
    country = request.args.get("country")
    exchange = request.args.get("exchange")
    asset_type = request.args.get("asset_type")

    for f_name, f_val in [("country", country), ("exchange", exchange), ("asset_type", asset_type)]:
        if f_val is not None:
            if not f_val.strip() or not FILTER_FORMAT_REGEX.match(f_val.strip()):
                return jsonify({
                    "success": False,
                    "message": f"Invalid filter value for '{f_name}'."
                }), 400

    results = CompanySearchService.search(
        query=clean_q,
        country=country,
        exchange=exchange,
        asset_type=asset_type,
        limit=limit,
        active_only=True,
    )

    return jsonify({
        "success": True,
        "query": clean_q,
        "count": len(results),
        "results": results,
    }), 200
