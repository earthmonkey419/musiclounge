from flask import Blueprint, render_template, abort, current_app

import db
import plex_client

bp = Blueprint("linked", __name__)


@bp.route("/<share_token>")
def view_share(share_token):
    # 404 whether the token is expired, revoked, or never existed —
    # never distinguish, per the scope doc's security reasoning.
    if not db.is_share_live(share_token):
        abort(404)

    share = db.get_share(share_token)

    try:
        title, artist, tracks = plex_client.get_content_tracks(share["content_type"], share["content_ref"])
    except Exception:
        current_app.logger.exception("Linked view failed to load content for token=%r", share_token)
        # Degrade gracefully: show what we stored at share-creation time
        # rather than a hard failure, even if Plex is unreachable right now.
        title = share["content_title"]
        artist = share["content_artist"]
        tracks = []

    db.record_share_access(share_token)

    return render_template(
        "linked.html",
        share=share,
        tracks=tracks,
        content_title=title,
        content_artist=artist,
    )
