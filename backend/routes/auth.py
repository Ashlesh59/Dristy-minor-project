"""
routes/auth.py
--------------------------------------------------------------------------
Authentication-related routes.
--------------------------------------------------------------------------
"""

import re
import traceback

from flask import Blueprint, request, jsonify, current_app, session

from database.db import db
from models.user import User
from utils.limiter import rate_limit

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

MIN_PASSWORD_LENGTH = 8


@auth_bp.route("/signup", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=60, key_prefix="auth_signup")
def signup():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "message": "Request body must be valid JSON."
        }), 400

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({
            "success": False,
            "message": "Name, email and password are all required."
        }), 400

    if not EMAIL_PATTERN.match(email):
        return jsonify({
            "success": False,
            "message": "Please provide a valid email address."
        }), 400

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({
            "success": False,
            "message": f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        }), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({
            "success": False,
            "message": "An account with this email already exists."
        }), 409

    try:
        new_user = User(name=name, email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()
        session["user_id"] = new_user.id
    except Exception as e:
        # Roll back so the failed, half-done change doesn't linger in
        # the session.
        db.session.rollback()

        current_app.logger.error("Signup failed: %s: %s", type(e).__name__, e)
        traceback.print_exc()

        return jsonify({
            "success": False,
            "message": "Something went wrong while creating your account. Please try again."
        }), 500

    return jsonify({
        "success": True,
        "message": "Account created successfully",
        "user": new_user.to_public_dict()
    }), 201


# ==========================================================================
# PHASE 4: LOGIN & AUTHENTICATION
# --------------------------------------------------------------------------
# Uses Flask's built-in server-side session, not a new dependency. When a
# route does `session["user_id"] = user.id`, Flask stores that value in a
# cookie -- but signed with Config.SECRET_KEY, not sent in the clear, so
# the browser can hold it but can't read or forge it. Nothing more than
# the numeric id ever goes in the session; the actual user record is
# re-fetched from the database on every request that needs it (see
# get_current_user() below), so there's no risk of stale/incorrect data
# sitting in the cookie itself.
# ==========================================================================

def get_current_user():
    """
    Looks up the User for the currently logged-in session, or None if
    nobody is logged in (or the session refers to a user that no
    longer exists). Centralized here so every route that needs "am I
    logged in, and as whom" does it the same way.
    """
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return db.session.get(User, user_id)


@auth_bp.route("/login", methods=["POST"])
@rate_limit(max_requests=10, window_seconds=60, key_prefix="auth_login")
def login():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "message": "Request body must be valid JSON."
        }), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({
            "success": False,
            "message": "Email and password are required."
        }), 400

    user = User.query.filter_by(email=email).first()

    # Deliberately the SAME error, same status code, whether the email
    # doesn't exist at all or the password is wrong for a real
    # account. Distinguishing the two ("no such email" vs "wrong
    # password") would let an attacker discover which emails are
    # registered by testing login attempts -- a real information leak
    # sometimes called a "user enumeration" vulnerability.
    if user is None or not user.check_password(password):
        return jsonify({
            "success": False,
            "message": "Invalid email or password."
        }), 401

    # Only the id goes in the session -- never the password or
    # password_hash. Flask signs this cookie with Config.SECRET_KEY,
    # so the browser can't tamper with or forge the user_id it holds.
    session["user_id"] = user.id

    return jsonify({
        "success": True,
        "message": "Login successful",
        "user": user.to_public_dict()
    }), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    user = get_current_user()
    if user is None:
        return jsonify({
            "success": False,
            "message": "You are not logged in."
        }), 401

    return jsonify({
        "success": True,
        "user": user.to_public_dict()
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    # .pop(..., None) removes "user_id" if it's there and does nothing
    # (no error) if it isn't -- so calling logout when nobody is
    # logged in is always safe, as required.
    session.pop("user_id", None)

    return jsonify({
        "success": True,
        "message": "Logout successful"
    }), 200


@auth_bp.route("/profile", methods=["PUT"])
def update_profile():
    """
    Updates the logged-in user's own profile fields. name/email plus
    the optional company/job_role/phone/country/timezone fields added
    in models/user.py. Never accepts user_id or password here --
    password changes go through PUT /api/auth/password instead, which
    requires the current password.
    """
    user = get_current_user()
    if user is None:
        return jsonify({
            "success": False,
            "message": "You are not logged in."
        }), 401

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "message": "Request body must be valid JSON."
        }), 400

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({
                "success": False,
                "message": "Name cannot be empty."
            }), 400
        user.name = name

    if "email" in data:
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({
                "success": False,
                "message": "Email cannot be empty."
            }), 400
        if not EMAIL_PATTERN.match(email):
            return jsonify({
                "success": False,
                "message": "Please provide a valid email address."
            }), 400
        existing = User.query.filter(User.email == email, User.id != user.id).first()
        if existing:
            return jsonify({
                "success": False,
                "message": "An account with this email already exists."
            }), 409
        user.email = email

    # Optional free-text fields -- each only touched if present in the
    # request body at all, so a partial update (e.g. just changing
    # `phone`) never blanks out the others.
    for field in ("company", "job_role", "phone", "country", "timezone"):
        if field in data:
            value = data.get(field)
            setattr(user, field, (value or "").strip() or None)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Profile update failed: %s: %s", type(e).__name__, e)
        return jsonify({
            "success": False,
            "message": "Something went wrong while updating your profile. Please try again."
        }), 500

    return jsonify({
        "success": True,
        "message": "Profile updated successfully",
        "user": user.to_public_dict()
    }), 200


@auth_bp.route("/password", methods=["PUT"])
def change_password():
    """
    Changes the logged-in user's password. Requires the current
    password to be correct (never assumes an authenticated session
    alone is enough for this) and validates the new one the same way
    signup does.
    """
    user = get_current_user()
    if user is None:
        return jsonify({
            "success": False,
            "message": "You are not logged in."
        }), 401

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({
            "success": False,
            "message": "Request body must be valid JSON."
        }), 400

    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if not current_password or not new_password:
        return jsonify({
            "success": False,
            "message": "Current password and new password are both required."
        }), 400

    if not user.check_password(current_password):
        return jsonify({
            "success": False,
            "message": "Current password is incorrect."
        }), 401

    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify({
            "success": False,
            "message": f"New password must be at least {MIN_PASSWORD_LENGTH} characters long."
        }), 400

    try:
        user.set_password(new_password)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Password change failed: %s: %s", type(e).__name__, e)
        return jsonify({
            "success": False,
            "message": "Something went wrong while changing your password. Please try again."
        }), 500

    return jsonify({
        "success": True,
        "message": "Password changed successfully"
    }), 200


@auth_bp.route("/protected", methods=["GET"])
def protected():
    """
    Development/testing route only -- exists purely to give a simple
    way to confirm the session mechanism works (via curl or Postman)
    without needing a real feature page. Not linked from the frontend.
    """
    user = get_current_user()
    if user is None:
        return jsonify({
            "success": False,
            "message": "You are not logged in."
        }), 401

    return jsonify({
        "success": True,
        "message": "You are authenticated",
        "user_id": user.id
    }), 200
