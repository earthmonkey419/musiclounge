import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, Response, stream_with_context, current_app

import config
import db
import plex_client
from auth import guest_required

bp = Blueprint("room", __name__)


def _resolve_action_room():
    """Resolves which room an action (search/queue-add/skip/playpause/
    volume) should apply to. Works for EITHER a guest (room_id in
    session, room still live) OR an admin.

    This matters because the admin dashboard IS the host device -- it's
    the one with the actual <audio> element and transport controls --
    but the admin never goes through /join, so it never has a guest
    room_id session. Every one of these endpoints used to require
    @guest_required alone, which silently 302-redirected every call
    the dashboard ever made (skip, play/pause, the auto-advance-on-
    track-end handler) to /join. fetch() follows redirects and the
    resulting JSON-parse failure was swallowed by a bare .catch(), so
    it failed completely invisibly: is_playing never cleared, so the
    next 4s poll saw "should be playing" + "audio actually paused"
    and replayed the same finished track forever -- the reported
    "stuck on one track, playing over and over" bug.

    Returns (room_id, None) on success, or (None, (response, status))
    for the caller to return immediately."""
    room_id = session.get("room_id")
    if room_id and db.is_room_live(room_id):
        return room_id, None

    if session.get("is_admin"):
        room = db.get_active_room()
        if room:
            return room["session_id"], None
        return None, (jsonify({"error": "No active room."}), 404)

    if room_id:
        session.pop("room_id", None)
        return None, (jsonify({"error": "This room has ended. Please rejoin.", "room_ended": True}), 410)

    return None, (jsonify({"error": "Not authorized."}), 401)


@bp.route("/join/<code>")
def join_by_code(code):
    """Instant join via QR scan -- skips the manual code-entry form.
    Same join logic as the POST /join path, just triggered by a GET
    so a scanned QR link does the whole thing in one step."""
    room = db.get_room_by_code(code)
    if not room:
        return render_template("join.html", error="That code didn't match an active room.")
    session["room_id"] = room["session_id"]
    db.bump_device_count(room["session_id"])
    db.log_action(room["session_id"], "join")
    return redirect(url_for("room.guest"))


@bp.route("/join", methods=["GET", "POST"])
def join():
    if request.method == "POST":
        code = request.form.get("join_code", "").strip()
        room = db.get_room_by_code(code)
        if not room:
            return render_template("join.html", error="That code didn't match an active room.")
        session["room_id"] = room["session_id"]
        db.bump_device_count(room["session_id"])
        db.log_action(room["session_id"], "join")
        return redirect(url_for("room.guest"))
    return render_template("join.html")


@bp.route("/guest")
@guest_required
def guest():
    room = db.get_room(session["room_id"])
    if not room or not db.is_room_live(session["room_id"]):
        session.pop("room_id", None)
        return redirect(url_for("room.join"))
    return render_template("guest.html", room=room)


# --- JSON API, used by guest.html + admin_dashboard.html's JS ---
# Every action endpoint below accepts either a guest or an admin
# session -- see _resolve_action_room() above for why that matters.

@bp.route("/api/search")
def api_search():
    room_id, err = _resolve_action_room()
    if err:
        return err
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    try:
        return jsonify(plex_client.search_tracks(q))
    except Exception:
        current_app.logger.exception("Plex search failed for query: %r", q)
        return jsonify({"error": "Couldn't reach the music library. Try again in a moment."}), 502


@bp.route("/api/mood/<mood_key>")
def api_mood(mood_key):
    room_id, err = _resolve_action_room()
    if err:
        return err
    try:
        return jsonify(plex_client.tracks_by_mood(mood_key))
    except Exception:
        current_app.logger.exception("Plex mood lookup failed for: %r", mood_key)
        return jsonify({"error": "Couldn't reach the music library. Try again in a moment."}), 502


def _room_state(room_id):
    room = db.get_room(room_id)
    if not room:
        return None
    queue = db.get_queue(room_id)
    return {
        "now_playing": {
            "ref": room["now_playing_ref"],
            "title": room["now_playing_title"],
            "artist": room["now_playing_artist"],
            "duration_sec": room["now_playing_duration"],
            "is_playing": bool(room["is_playing"]),
            "volume": room["volume"],
        } if room["now_playing_ref"] else None,
        "queue": [dict(q) for q in queue],
        "join_code": room["join_code"],
        "room_name": room["room_name"],
    }


@bp.route("/api/room-state")
def api_room_state():
    room_id = session.get("room_id")
    if not room_id:
        room = db.get_active_room()
        room_id = room["session_id"] if room else None
    if not room_id:
        return jsonify({"error": "no active room"}), 404
    state = _room_state(room_id)
    return jsonify(state) if state else (jsonify({"error": "not found"}), 404)


@bp.route("/api/queue/add", methods=["POST"])
def api_queue_add():
    room_id, err = _resolve_action_room()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    rating_key = body.get("rating_key")

    try:
        room = db.get_room(room_id)
        if db.queue_count(room_id) >= config.ROOM_MAX_QUEUE_ADDS_PER_SESSION:
            return jsonify({"error": "This room's queue is full for now."}), 429

        try:
            track = plex_client.get_track(rating_key)
        except Exception:
            current_app.logger.exception("Plex track lookup failed for rating_key=%r", rating_key)
            return jsonify({"error": "Couldn't find that track."}), 404

        track_dict = plex_client._track_to_dict(track)
        db.add_to_queue(room_id, track_dict)
        db.log_action(room_id, "queue_add", track_dict["title"])

        if not room["now_playing_ref"]:
            nxt = db.pop_next(room_id)
            if nxt:
                db.set_now_playing(room_id, db.queue_row_to_track(nxt))

        return jsonify({"ok": True})

    except Exception:
        current_app.logger.exception("queue/add failed unexpectedly for rating_key=%r, room=%r", rating_key, room_id)
        return jsonify({"error": "Something went wrong adding that track."}), 500


@bp.route("/api/skip", methods=["POST"])
def api_skip():
    room_id, err = _resolve_action_room()
    if err:
        return err
    if not db.can_skip(room_id):
        return jsonify({"error": "Skipping too fast -- try again in a moment."}), 429
    db.record_skip(room_id)
    nxt = db.pop_next(room_id)
    if nxt:
        db.set_now_playing(room_id, db.queue_row_to_track(nxt))
    else:
        db.set_play_state(room_id, False)
    db.log_action(room_id, "skip")
    return jsonify({"ok": True})


@bp.route("/api/playpause", methods=["POST"])
def api_playpause():
    room_id, err = _resolve_action_room()
    if err:
        return err
    room = db.get_room(room_id)
    db.set_play_state(room_id, not room["is_playing"])
    db.log_action(room_id, "play_pause")
    return jsonify({"ok": True})


@bp.route("/api/volume", methods=["POST"])
def api_volume():
    room_id, err = _resolve_action_room()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    try:
        vol = int(body.get("volume", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "bad volume"}), 400
    clamped = db.set_volume(room_id, vol)
    db.log_action(room_id, "volume", str(clamped))
    return jsonify({"ok": True, "volume": clamped})


@bp.route("/art/<rating_key>")
def art(rating_key):
    try:
        thumb_path = plex_client.track_art_path(rating_key)
        if not thumb_path:
            return "", 404
    except Exception:
        return "", 404

    plex_url = f"{config.PLEX_URL}{thumb_path}?X-Plex-Token={config.PLEX_TOKEN}"
    try:
        upstream = requests.get(plex_url, timeout=6)
    except Exception:
        return "", 502
    if upstream.status_code != 200:
        return "", 404

    resp = Response(upstream.content, content_type=upstream.headers.get("Content-Type", "image/jpeg"))
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@bp.route("/stream/<rating_key>")
def stream(rating_key):
    try:
        part_path = plex_client.track_stream_part(rating_key)
    except Exception:
        return "Track not found", 404

    plex_url = f"{config.PLEX_URL}{part_path}?X-Plex-Token={config.PLEX_TOKEN}"
    headers = {}
    if "Range" in request.headers:
        headers["Range"] = request.headers["Range"]

    upstream = requests.get(plex_url, headers=headers, stream=True)

    def generate():
        for chunk in upstream.iter_content(chunk_size=8192):
            yield chunk

    resp = Response(
        stream_with_context(generate()),
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "audio/mpeg"),
    )
    for h in ("Content-Range", "Content-Length", "Accept-Ranges"):
        if h in upstream.headers:
            resp.headers[h] = upstream.headers[h]
    return resp
