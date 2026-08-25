from flask import Blueprint, render_template, request, jsonify, url_for, current_app

import config
import db
import plex_client
from email_utils import send_share_email

bp = Blueprint("share", __name__)


@bp.route("/", methods=["GET"])
def new_share():
    # Three-stage flow: what are you sharing / choose it / how long.
    return render_template("share_new.html", durations=config.SHARE_LINK_DURATIONS_HOURS)


@bp.route("/api/search")
def api_share_search():
    content_type = request.args.get("type", "").strip().lower()
    q = request.args.get("q", "").strip()
    if not q or content_type not in ("album", "artist", "playlist"):
        return jsonify([])
    try:
        return jsonify(plex_client.search_content(content_type, q))
    except Exception:
        current_app.logger.exception("Share search failed type=%r q=%r", content_type, q)
        return jsonify({"error": "Couldn't reach the music library. Try again in a moment."}), 502


@bp.route("/create", methods=["POST"])
def create_share():
    body = request.get_json(silent=True) or {}
    content_type = body.get("content_type")
    content_ref = body.get("content_ref")
    content_title = body.get("content_title", "")
    content_artist = body.get("content_artist", "")
    duration = body.get("duration_hours")

    if content_type not in ("album", "artist", "playlist"):
        return jsonify({"error": "Pick what you're sharing first."}), 400
    if duration not in config.SHARE_LINK_DURATIONS_HOURS:
        return jsonify({"error": "Pick a valid duration (24/48/72 hours)."}), 400
    if not content_ref:
        return jsonify({"error": "Pick something to share first."}), 400

    # Validate the content actually resolves in Plex before minting a link
    try:
        plex_client.get_plex().fetchItem(int(content_ref))
    except Exception:
        current_app.logger.exception("Share create: content_ref invalid %r", content_ref)
        return jsonify({"error": "Couldn't find that in your library."}), 404

    token = db.create_share(content_type, str(content_ref), content_title, content_artist, duration)
    share_url = request.host_url.rstrip("/") + url_for("linked.view_share", share_token=token)
    return jsonify({"ok": True, "token": token, "share_url": share_url})


@bp.route("/<token>/email", methods=["POST"])
def email_share(token):
    if not db.is_share_live(token):
        return jsonify({"error": "This link has expired or is invalid."}), 410

    body = request.get_json(silent=True) or {}
    recipient = body.get("email", "").strip()
    display_name = body.get("from_display_name", "").strip()
    if not recipient:
        return jsonify({"error": "Enter a recipient email address."}), 400

    share = db.get_share(token)
    share_url = request.host_url.rstrip("/") + url_for("linked.view_share", share_token=token)

    try:
        send_share_email(recipient, share_url, share["content_title"], display_name)
    except Exception:
        current_app.logger.exception("SMTP send failed for token=%r to=%r", token, recipient)
        return jsonify({"error": "Couldn't send the email — check SMTP settings in config.py."}), 502

    db.mark_share_delivery(token, "email", recipient, display_name)
    return jsonify({"ok": True})
