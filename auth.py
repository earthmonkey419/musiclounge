from functools import wraps
from flask import session, redirect, url_for


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
