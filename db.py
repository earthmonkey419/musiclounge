"""
Room Mode DB helpers. Short join codes here (not the long/random
share tokens) are intentional and match the scope doc's reasoning:
room codes are host-supervised and short-lived, same class of
guardrail as RiderMusic's 4-digit code — a different security profile
than the unattended, 24-72hr /linked tokens in share.py.
"""
import sqlite3
import random
import string
import secrets
import uuid
from datetime import datetime, timedelta

import config


def get_db():
    # WAL mode + busy_timeout: standard fix for "database is locked"
    # under concurrent writers. Our gunicorn setup runs 2 worker
    # PROCESSES (not just threads) x 4 threads each, all potentially
    # opening their own connection — SQLite's default rollback-journal
    # locking mode can throw immediately on write contention. WAL lets
    # readers and a writer coexist without blocking each other, and
    # busy_timeout makes any remaining contention retry for up to 10s
    # instead of failing instantly.
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.utcnow().isoformat()


def _gen_join_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# --- Sessions ---------------------------------------------------------

def create_room(room_name):
    conn = get_db()
    # Enforce a single active room per instance (v1 assumption stated in
    # the scope doc). Without this, a second "Start a Room" click leaves
    # two simultaneously-active rooms — the dashboard always shows the
    # newest one via get_active_room(), but an already-joined guest could
    # still be attached to the older one, silently diverging.
    conn.execute("UPDATE room_sessions SET ended_by_admin = 1 WHERE ended_by_admin = 0")

    session_id = str(uuid.uuid4())
    join_code = _gen_join_code()
    started_at = _now()
    expires_at = (datetime.utcnow() + timedelta(minutes=config.ROOM_SESSION_TIMEOUT_MINUTES)).isoformat()
    conn.execute(
        """INSERT INTO room_sessions
           (session_id, room_name, join_code, started_at, expires_at, volume)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, room_name, join_code, started_at, expires_at, config.ROOM_VOLUME_CEILING),
    )
    conn.commit()
    conn.close()
    return session_id


def get_active_room():
    """The one active (non-ended, non-expired) room, if any. v1 assumes
    a single concurrent room per instance, matching RiderMusic."""
    conn = get_db()
    row = conn.execute(
        """SELECT * FROM room_sessions
           WHERE ended_by_admin = 0 AND expires_at > ?
           ORDER BY started_at DESC LIMIT 1""",
        (_now(),),
    ).fetchone()
    conn.close()
    return row


def get_room(session_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM room_sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return row


def get_room_by_code(join_code):
    conn = get_db()
    row = conn.execute(
        """SELECT * FROM room_sessions
           WHERE join_code = ? AND ended_by_admin = 0 AND expires_at > ?""",
        (join_code.upper(), _now()),
    ).fetchone()
    conn.close()
    return row


def end_room(session_id):
    conn = get_db()
    conn.execute("UPDATE room_sessions SET ended_by_admin = 1 WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def bump_device_count(session_id):
    conn = get_db()
    conn.execute("UPDATE room_sessions SET device_count = device_count + 1 WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def set_now_playing(session_id, track):
    """`track` must be the plex_client._track_to_dict() shape: keys
    rating_key/title/artist/duration_sec. If you have a room_queue row
    instead (different column names — track_ref, not rating_key), pass
    it through queue_row_to_track() first."""
    conn = get_db()
    conn.execute(
        """UPDATE room_sessions SET
           now_playing_ref = ?, now_playing_title = ?, now_playing_artist = ?,
           now_playing_duration = ?, position_sec = 0, is_playing = 1
           WHERE session_id = ?""",
        (track["rating_key"], track["title"], track["artist"], track["duration_sec"], session_id),
    )
    conn.commit()
    conn.close()


def queue_row_to_track(row):
    """room_queue rows use different column names (track_ref, not
    rating_key) than plex_client._track_to_dict()'s output. This bridges
    the two shapes — use this, not a bare dict(row), before passing a
    popped queue row into set_now_playing()."""
    return {
        "rating_key": row["track_ref"],
        "title": row["title"],
        "artist": row["artist"],
        "duration_sec": row["duration_sec"],
    }


def set_play_state(session_id, is_playing):
    conn = get_db()
    conn.execute("UPDATE room_sessions SET is_playing = ? WHERE session_id = ?", (1 if is_playing else 0, session_id))
    conn.commit()
    conn.close()


def set_volume(session_id, volume):
    clamped = max(0, min(volume, config.ROOM_VOLUME_CEILING))
    conn = get_db()
    conn.execute("UPDATE room_sessions SET volume = ? WHERE session_id = ?", (clamped, session_id))
    conn.commit()
    conn.close()
    return clamped


def can_skip(session_id):
    room = get_room(session_id)
    if not room or not room["last_skip_at"]:
        return True
    last = datetime.fromisoformat(room["last_skip_at"])
    return (datetime.utcnow() - last).total_seconds() >= config.ROOM_SKIP_RATE_LIMIT_SECONDS


def record_skip(session_id):
    conn = get_db()
    conn.execute("UPDATE room_sessions SET last_skip_at = ? WHERE session_id = ?", (_now(), session_id))
    conn.commit()
    conn.close()


# --- Queue --------------------------------------------------------------

def is_room_live(session_id):
    """A room existing isn't enough — it must also be un-ended and
    un-expired. Guest API endpoints need this check explicitly: the
    guest_required decorator only confirms a room_id is *present* in
    the session, not that it's still the currently active room."""
    room = get_room(session_id)
    if not room:
        return False
    if room["ended_by_admin"]:
        return False
    if room["expires_at"] <= _now():
        return False
    return True


def queue_count(session_id):
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as n FROM room_queue WHERE session_id = ? AND played = 0", (session_id,)
    ).fetchone()
    conn.close()
    return row["n"]


def add_to_queue(session_id, track):
    conn = get_db()
    max_pos = conn.execute(
        "SELECT COALESCE(MAX(position), 0) as m FROM room_queue WHERE session_id = ?", (session_id,)
    ).fetchone()["m"]
    conn.execute(
        """INSERT INTO room_queue
           (session_id, position, track_ref, title, artist, duration_sec, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, max_pos + 1, track["rating_key"], track["title"], track["artist"],
         track["duration_sec"], _now()),
    )
    conn.commit()
    conn.close()


def get_queue(session_id):
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM room_queue WHERE session_id = ? AND played = 0
           ORDER BY position ASC""",
        (session_id,),
    ).fetchall()
    conn.close()
    return rows


def pop_next(session_id):
    """Marks the earliest un-played queue item as played and returns it,
    or None if the queue is empty."""
    conn = get_db()
    row = conn.execute(
        """SELECT * FROM room_queue WHERE session_id = ? AND played = 0
           ORDER BY position ASC LIMIT 1""",
        (session_id,),
    ).fetchone()
    if row:
        conn.execute("UPDATE room_queue SET played = 1 WHERE id = ?", (row["id"],))
        conn.commit()
    conn.close()
    return row


# --- Actions log ----------------------------------------------------------

def log_action(session_id, action_type, detail=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO room_actions (session_id, action_type, detail, ts) VALUES (?, ?, ?, ?)",
        (session_id, action_type, detail, _now()),
    )
    conn.commit()
    conn.close()


# --- Share Mode (/linked) -------------------------------------------------

def create_share(content_type, content_ref, content_title, content_artist, duration_hours):
    """Mints a share as a DB row — long random token, expiry set at
    creation time from the fixed 24/48/72hr set. Per the scope doc:
    a DB row rather than a signed token, because it's free (same
    pattern as room_sessions) and keeps revocation possible."""
    token = secrets.token_urlsafe(config.SHARE_TOKEN_BYTES)
    created_at = _now()
    expires_at = (datetime.utcnow() + timedelta(hours=duration_hours)).isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO shares
           (share_token, content_type, content_ref, content_title, content_artist,
            created_at, expires_at, duration_hours)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (token, content_type, content_ref, content_title, content_artist,
         created_at, expires_at, duration_hours),
    )
    conn.commit()
    conn.close()
    return token


def get_share(token):
    conn = get_db()
    row = conn.execute("SELECT * FROM shares WHERE share_token = ?", (token,)).fetchone()
    conn.close()
    return row


def is_share_live(token):
    """A share existing isn't enough — must also be un-revoked and
    un-expired. Never distinguish 'expired' from 'never existed' to
    callers — both should just look like 404, per the scope doc's
    security reasoning."""
    row = get_share(token)
    if not row:
        return False
    if row["revoked"]:
        return False
    if row["expires_at"] <= _now():
        return False
    return True


def record_share_access(token):
    conn = get_db()
    conn.execute(
        "UPDATE shares SET access_count = access_count + 1, last_accessed_at = ? WHERE share_token = ?",
        (_now(), token),
    )
    conn.commit()
    conn.close()


def mark_share_delivery(token, method, recipient_email=None, from_display_name=None):
    conn = get_db()
    conn.execute(
        "UPDATE shares SET delivery_method = ?, recipient_email = ?, from_display_name = ? WHERE share_token = ?",
        (method, recipient_email, from_display_name, token),
    )
    conn.commit()
    conn.close()
