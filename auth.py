from functools import wraps
from flask import session, redirect, url_for, jsonify

import config


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login"))
        return f(*a, **kw)
    return wrapper


def guest_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("room_id"):
            return redirect(url_for("room.join"))
        return f(*a, **kw)
    return wrapper


def _share_login_required():
    # getattr so an older config.py without the setting keeps working
    # (and defaults to the safe behavior: login required).
    return getattr(config, "SHARE_REQUIRES_LOGIN", True)


def share_access_required(f):
    """Gate the Share Mode creation page. When SHARE_REQUIRES_LOGIN is on
    (default), only a logged-in admin gets through; everyone else is sent
    to the admin login. Recipients' /linked/<token> pages are never gated."""
    @wraps(f)
    def wrapper(*a, **kw):
        if _share_login_required() and not session.get("is_admin"):
            return redirect(url_for("admin.login"))
        return f(*a, **kw)
    return wrapper


def share_api_access_required(f):
    """Same gate for the share JSON endpoints (search / create / email):
    answers 401 JSON instead of redirecting, so the share page's fetch()
    calls can show the message."""
    @wraps(f)
    def wrapper(*a, **kw):
        if _share_login_required() and not session.get("is_admin"):
            return jsonify({"error": "Please log in as the host to share music."}), 401
        return f(*a, **kw)
    return wrapper
