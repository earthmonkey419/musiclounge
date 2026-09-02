from flask import Blueprint, render_template, request, redirect, url_for, session, Response, current_app
import io
import csv
import base64
from datetime import datetime
import qrcode
import config
import db
from auth import admin_required
from email_utils import send_password_reset_email

bp = Blueprint("admin", __name__)


SHARE_CSV_COLUMNS = [
    "share_token", "content_type", "content_ref", "content_title", "content_artist",
    "created_at", "expires_at", "duration_hours", "delivery_method", "recipient_email",
    "from_display_name", "revoked", "access_count", "last_accessed_at",
]
ROOM_CSV_COLUMNS = [
    "session_id", "room_name", "join_code", "started_at", "expires_at", "ended_by_admin",
    "device_count", "now_playing_ref", "now_playing_title", "now_playing_artist",
    "now_playing_duration", "position_sec", "is_playing", "volume", "last_skip_at",
]


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if db.verify_admin_password(request.form.get("password", "")):
            session["is_admin"] = True
            return redirect(url_for("admin.dashboard"))
        return render_template("admin_login.html", error="Wrong password.")
    return render_template("admin_login.html")


@bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("home.index"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        if config.ADMIN_RECOVERY_EMAIL:
            token = db.create_password_reset()
            reset_url = request.host_url.rstrip("/") + url_for("admin.reset_password", token=token)
            try:
                send_password_reset_email(reset_url)
            except Exception:
                current_app.logger.exception("Failed to send password reset email")
        return render_template("admin_forgot_password.html", sent=True)
    return render_template("admin_forgot_password.html", sent=False)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if not db.is_password_reset_valid(token):
        return render_template("admin_forgot_password.html", sent=False,
                                error="That reset link is invalid or has expired. Request a new one below.")

    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(new_password) < 8:
            return render_template("admin_reset_password.html", token=token, error="Password must be at least 8 characters.")
        if new_password != confirm:
            return render_template("admin_reset_password.html", token=token, error="Passwords don't match.")
        db.set_admin_password(new_password)
        db.use_password_reset(token)
        return redirect(url_for("admin.login"))

    return render_template("admin_reset_password.html", token=token, error=None)


@bp.route("/stats")
@admin_required
def stats():
    conn = db.get_db()
    now = datetime.utcnow().isoformat()

    share_rows = conn.execute("SELECT * FROM shares ORDER BY created_at DESC LIMIT 200").fetchall()
    shares = []
    for row in share_rows:
        d = dict(row)
        if d["revoked"]:
            d["status"] = "revoked"
        elif d["expires_at"] <= now:
            d["status"] = "expired"
        else:
            d["status"] = "live"
        shares.append(d)

    rooms = conn.execute(
        "SELECT * FROM room_sessions ORDER BY started_at DESC LIMIT 100"
    ).fetchall()

    conn.close()
    return render_template("admin_stats.html", shares=shares, rooms=rooms)


@bp.route("/stats/download/<kind>")
@admin_required
def stats_download(kind):
    if kind not in ("shares", "rooms"):
        return "Invalid export type.", 400

    conn = db.get_db()
    if kind == "shares":
        rows = conn.execute("SELECT * FROM shares ORDER BY created_at DESC").fetchall()
        columns = SHARE_CSV_COLUMNS
    else:
        rows = conn.execute("SELECT * FROM room_sessions ORDER BY started_at DESC").fetchall()
        columns = ROOM_CSV_COLUMNS
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[c] for c in columns])

    resp = Response(buf.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename=musiclounge-{kind}.csv"
    return resp


@bp.route("/stats/clear", methods=["POST"])
@admin_required
def stats_clear():
    kind = request.form.get("kind")
    conn = db.get_db()
    now = datetime.utcnow().isoformat()
    if kind == "shares":
        conn.execute("DELETE FROM shares WHERE revoked = 1 OR expires_at <= ?", (now,))
    elif kind == "rooms":
        conn.execute("DELETE FROM room_sessions WHERE ended_by_admin = 1")
    conn.commit()
    conn.close()
    return redirect(url_for("admin.stats"))


@bp.route("/stats/end-room", methods=["POST"])
@admin_required
def stats_end_room():
    session_id = request.form.get("session_id")
    if session_id:
        db.end_room(session_id)
    return redirect(url_for("admin.stats"))


@bp.route("/stats/revoke-share", methods=["POST"])
@admin_required
def stats_revoke_share():
    token = request.form.get("token")
    if token:
        db.revoke_share(token)
    return redirect(url_for("admin.stats"))


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
