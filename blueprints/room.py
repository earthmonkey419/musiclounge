import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, Response, stream_with_context, current_app

import config
import db
import plex_client
from auth import guest_required

bp = Blueprint("room", __name__)


def _require_live_room():
    """Call at the top of every guest action endpoint. Returns None if
    the guest's session room is still genuinely active; otherwise
    clears the stale session and returns a (response, status) tuple
    the caller should return immediately.

    This closes a real gap: guest_required only checks that a room_id
    is *present* in the session, not that it's still the currently
    active room. Without this, a guest whose tab stayed open across a
    room restart/end could keep POSTing successfully into a dead room
    — writes that silently never show up on the (correctly different)
    live dashboard."""
    room_id = session.get("room_id")
    if not db.is_room_live(room_id):
        session.pop("room_id", None)
        return jsonify({"error": "This room has ended. Please rejoin.", "room_ended": True}), 410
    return None


@bp.route("/join/<code>")
def join_by_code(code):
    """Instant join via QR scan — skips the manual code-entry form.
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

@bp.route("/api/search")
@guest_required
def api_search():
    guard = _require_live_room()
    if guard:
        return guard
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    try:
        return jsonify(plex_client.search_tracks(q))
    except Exception:
        current_app.logger.exception("Plex search failed for query: %r", q)
        return jsonify({"error": "Couldn't reach the music library. Try again in a moment."}), 502


@bp.route("/api/mood/<mood_key>")
@guest_required
def api_mood(mood_key):
    guard = _require_live_room()
    if guard:
        return guard
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
    # Used by both the guest portal (session-scoped) and the admin
    # dashboard (looks up the one active room directly, no guest
    # session cookie involved).
    room_id = session.get("room_id")
    if not room_id:
        room = db.get_active_room()
        room_id = room["session_id"] if room else None
    if not room_id:
        return jsonify({"error": "no active room"}), 404
    state = _room_state(room_id)
    return jsonify(state) if state else (jsonify({"error": "not found"}), 404)


@bp.route("/api/queue/add", methods=["POST"])
@guest_required
def api_queue_add():
    guard = _require_live_room()
    if guard:
        return guard

    room_id = session["room_id"]
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
@guest_required
def api_skip():
    guard = _require_live_room()
    if guard:
        return guard
    room_id = session["room_id"]
    if not db.can_skip(room_id):
        return jsonify({"error": "Skipping too fast — try again in a moment."}), 429
    db.record_skip(room_id)
    nxt = db.pop_next(room_id)
    if nxt:
        db.set_now_playing(room_id, db.queue_row_to_track(nxt))
    db.log_action(room_id, "skip")
    return jsonify({"ok": True})


@bp.route("/api/playpause", methods=["POST"])
@guest_required
def api_playpause():
    guard = _require_live_room()
    if guard:
        return guard
    room_id = session["room_id"]
    room = db.get_room(room_id)
    db.set_play_state(room_id, not room["is_playing"])
    db.log_action(room_id, "play_pause")
    return jsonify({"ok": True})


@bp.route("/api/volume", methods=["POST"])
@guest_required
def api_volume():
    guard = _require_live_room()
    if guard:
        return guard
    room_id = session["room_id"]
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
    """Proxies album art from Plex, same token-hiding pattern as /stream.
    Cached client-side hard, since a given rating_key's art never
    changes — cuts down repeat requests for the same album across a
    session's search results and queue."""
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
    """Proxies audio from Plex. The real Plex token never reaches any
    client — it's attached here, server-side, on the upstream request
    only. Range-request passthrough for seeking."""
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
