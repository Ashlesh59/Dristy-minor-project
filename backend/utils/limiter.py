"""
utils/limiter.py
--------------------------------------------------------------------------
In-memory sliding-window rate limiter for protecting endpoints against
brute-force attacks and external API quota exhaustion.
--------------------------------------------------------------------------
"""

import time
import threading
from functools import wraps
from flask import request, jsonify, current_app

_lock = threading.Lock()
_ip_request_history = {}  # key: (key_prefix, ip_or_ident), value: list of timestamps


def _clean_old_requests(timestamps, window_seconds, current_time):
    cutoff = current_time - window_seconds
    return [ts for ts in timestamps if ts > cutoff]


def rate_limit(max_requests=10, window_seconds=60, key_prefix="general"):
    """
    Rate limiting decorator.
    :param max_requests: Maximum allowed requests within the time window.
    :param window_seconds: Time window in seconds.
    :param key_prefix: Distinct prefix for grouping limits (e.g. 'auth', 'research').
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_app and current_app.config.get("TESTING"):
                return fn(*args, **kwargs)

            # Identify caller by X-Forwarded-For or remote_addr
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
            else:
                client_ip = request.remote_addr or "127.0.0.1"

            key = (key_prefix, client_ip)
            now = time.time()

            with _lock:
                history = _ip_request_history.get(key, [])
                history = _clean_old_requests(history, window_seconds, now)

                if len(history) >= max_requests:
                    retry_after = int(window_seconds - (now - history[0])) + 1
                    response = jsonify({
                        "success": False,
                        "message": f"Too many requests. Please wait {max_requests} requests per {window_seconds}s limit. Try again in {retry_after}s."
                    })
                    response.status_code = 429
                    response.headers["Retry-After"] = str(retry_after)
                    return response

                history.append(now)
                _ip_request_history[key] = history

            return fn(*args, **kwargs)
        return wrapper
    return decorator
