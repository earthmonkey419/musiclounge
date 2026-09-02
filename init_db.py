"""
MusicLounge Jukebox for Plex -- DB initialization.

Run once: python3 init_db.py

Schema follows RiderMusic's proven shape for Mode A (Room) almost
directly, and adds a `shares` table for Mode B -- a DB row, not a
signed token, per the scope doc's reasoning (free reuse of the
sessions/expires_at pattern; revocable; no new crypto infra).
"""
import sqlite3
import config

conn = sqlite3.connect(config.DB_PATH)
c = conn.cursor()

# ---------------------------------------------------------------
# Mode A: Room
# ---------------------------------------------------------------

c.execute("""
CREATE TABLE IF NOT EXISTS room_sessions (
    session_id      TEXT PRIMARY KEY,
    room_name        TEXT,
    join_code        TEXT,
    started_at       TEXT,
    expires_at       TEXT,
    ended_by_admin   INTEGER DEFAULT 0,
    device_count     INTEGER DEFAULT 0,
    now_playing_ref     TEXT,
    now_playing_title   TEXT,
    now_playing_artist  TEXT,
    now_playing_duration INTEGER,
    position_sec        INTEGER DEFAULT 0,
    is_playing           INTEGER DEFAULT 0,
    volume                INTEGER DEFAULT 80,
    last_skip_at           TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS room_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT,
    position        INTEGER,
    track_ref       TEXT,
    title           TEXT,
    artist          TEXT,
    duration_sec    INTEGER,
    added_at        TEXT,
    played          INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES room_sessions(session_id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS room_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT,
    action_type     TEXT,
    detail          TEXT,
    ts              TEXT,
    FOREIGN KEY (session_id) REFERENCES room_sessions(session_id)
)
""")

# ---------------------------------------------------------------
# Mode B: Share (/linked)
# ---------------------------------------------------------------

c.execute("""
CREATE TABLE IF NOT EXISTS shares (
    share_token       TEXT PRIMARY KEY,
    content_type      TEXT,
    content_ref       TEXT,
    content_title     TEXT,
    content_artist    TEXT,
    created_at        TEXT,
    expires_at        TEXT,
    duration_hours    INTEGER,
    delivery_method   TEXT,
    recipient_email   TEXT,
    from_display_name TEXT,
    revoked           INTEGER DEFAULT 0,
    access_count      INTEGER DEFAULT 0,
    last_accessed_at  TEXT
)
""")

# ---------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------

c.execute("""
CREATE TABLE IF NOT EXISTS password_resets (
    token       TEXT PRIMARY KEY,
    created_at  TEXT,
    expires_at  TEXT,
    used        INTEGER DEFAULT 0
)
""")

# ---------------------------------------------------------------
# Shared config (host-set, not per-ride/per-share) -- also now
# holds the DB-backed admin password hash, see db.py
# ---------------------------------------------------------------

c.execute("""
CREATE TABLE IF NOT EXISTS config (
    key     TEXT PRIMARY KEY,
    value   TEXT
)
""")

conn.commit()
conn.close()
print(f"MusicLounge DB initialized at {config.DB_PATH}")
