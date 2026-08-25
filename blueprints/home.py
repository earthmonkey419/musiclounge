from flask import Blueprint, render_template

bp = Blueprint("home", __name__)


@bp.route("/")
def index():
    # Two cards: "Start a Room" (-> /join or /admin/dashboard for host)
    # and "Share Some Music" (-> /admin/share for host).
    return render_template("home.html")
