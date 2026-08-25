from flask import Blueprint, render_template, request, redirect, url_for, session
import io
import base64
import qrcode
import config
import db
from auth import admin_required

bp = Blueprint("admin", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == config.ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin.dashboard"))
        return render_template("admin_login.html", error="Wrong password.")
    return render_template("admin_login.html")


@bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("home.index"))


@bp.route("/dashboard", methods=["GET", "POST"])
@admin_required
def dashboard():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "start":
            room_name = request.form.get("room_name", "").strip() or "My Lounge"
            db.create_room(room_name)
        elif action == "end":
            room = db.get_active_room()
            if room:
                db.end_room(room["session_id"])
        return redirect(url_for("admin.dashboard"))

    room = db.get_active_room()
    queue = db.get_queue(room["session_id"]) if room else []

    qr_data_uri = None
    join_url = None
    if room:
        join_url = request.host_url.rstrip("/") + url_for("room.join_by_code", code=room["join_code"])
        qr_img = qrcode.make(join_url, border=2)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    return render_template("admin_dashboard.html", room=room, queue=queue, qr_data_uri=qr_data_uri, join_url=join_url)
