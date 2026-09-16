"""
routes/securities.py
--------------------------------------------------------------------------
Security market data retrieval routes (Latest EOD and Historical Time-Series).
Protected by session authentication.
--------------------------------------------------------------------------
"""

from datetime import datetime
from flask import Blueprint, request, jsonify

from routes.auth import get_current_user
from services.market_data_service import (
    MarketDataService,
    SecurityNotFoundError,
    InvalidRangeError,
)
from utils.limiter import rate_limit

securities_bp = Blueprint("securities", __name__, url_prefix="/api/securities")


def _login_required_response():
    return jsonify({
        "success": False,
        "message": "You must be logged in to do that."
    }), 401


@securities_bp.route("/<int:security_id>/market-data/latest", methods=["GET"])
@rate_limit(max_requests=60, window_seconds=60, key_prefix="market_data_latest")
def get_latest_market_data(security_id: int):
    user = get_current_user()
    if user is None:
        return _login_required_response()

    try:
        data = MarketDataService.get_latest_market_data(security_id)
        return jsonify(data), 200
    except SecurityNotFoundError as sne:
        return jsonify({
            "success": False,
            "message": str(sne)
        }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving latest market data."
        }), 500


@securities_bp.route("/<int:security_id>/market-data/summary", methods=["GET"])
@rate_limit(max_requests=60, window_seconds=60, key_prefix="market_data_summary")
def get_market_summary(security_id: int):
    user = get_current_user()
    if user is None:
        return _login_required_response()

    try:
        data = MarketDataService.get_market_summary(security_id)
        return jsonify(data), 200
    except SecurityNotFoundError as sne:
        return jsonify({
            "success": False,
            "message": str(sne)
        }), 404
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving market summary data."
        }), 500


@securities_bp.route("/<int:security_id>/market-data/history", methods=["GET"])
@rate_limit(max_requests=60, window_seconds=60, key_prefix="market_data_history")
def get_price_history(security_id: int):
    user = get_current_user()
    if user is None:
        return _login_required_response()

    range_key = request.args.get("range")
    raw_start = request.args.get("start")
    raw_end = request.args.get("end")
    raw_limit = request.args.get("limit", "2000")
    price_mode = request.args.get("price_mode", "raw")
    version = request.args.get("version", "split_bonus_v1")

    start_date = None
    if raw_start:
        try:
            start_date = datetime.strptime(raw_start.strip(), "%Y-%m-%d").date()
        except ValueError:
            return jsonify({
                "success": False,
                "message": f"Invalid start date '{raw_start}'. Format must be YYYY-MM-DD."
            }), 400

    end_date = None
    if raw_end:
        try:
            end_date = datetime.strptime(raw_end.strip(), "%Y-%m-%d").date()
        except ValueError:
            return jsonify({
                "success": False,
                "message": f"Invalid end date '{raw_end}'. Format must be YYYY-MM-DD."
            }), 400

    try:
        limit = int(raw_limit)
        if limit < 1:
            return jsonify({
                "success": False,
                "message": "Limit must be a positive integer."
            }), 400
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid limit parameter. Must be an integer."
        }), 400

    try:
        history_data = MarketDataService.get_price_history(
            security_id=security_id,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            price_mode=price_mode,
            adjustment_version=version,
        )
        return jsonify(history_data), 200

    except SecurityNotFoundError as sne:
        return jsonify({
            "success": False,
            "message": str(sne)
        }), 404
    except InvalidRangeError as ire:
        return jsonify({
            "success": False,
            "message": str(ire)
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving historical market data."
        }), 500
