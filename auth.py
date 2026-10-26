from functools import wraps
from flask import session, redirect, url_for, jsonify


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


def admin_api_required(f):
    """Same gate as admin_required, for JSON endpoints: answers 401 JSON
    instead of redirecting, so fetch() callers (the share page) can show
    the message."""
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("is_admin"):
            return jsonify({"error": "Please log in as the host to share music."}), 401
        return f(*a, **kw)
    return wrapper
