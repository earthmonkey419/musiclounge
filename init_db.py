"""
MusicLounge Jukebox for Plex — DB initialization.

Run once: python3.12 init_db.py

Schema follows RiderMusic's proven shape for Mode A (Room) almost
directly, and adds a `shares` table for Mode B — a DB row, not a
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
    room_name        TEXT,               -- e.g. "Louis's Lounge", host-editable
    join_code        TEXT,                -- short code, host-supervised, room-scoped
    started_at       TEXT,
    expires_at       TEXT,
    ended_by_admin   INTEGER DEFAULT 0,
    device_count     INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS room_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT,
    position        INTEGER,
    track_ref       TEXT,                -- Plex rating key
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
    action_type     TEXT,   -- 'queue_add', 'skip', 'volume', 'play_pause', 'join'
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
    share_token       TEXT PRIMARY KEY,   -- long random token, IS the /linked/<token> URL segment
    content_type      TEXT,               -- 'album' | 'playlist' | 'artist'
    content_ref       TEXT,               -- Plex rating key for the shared item
    content_title     TEXT,
    content_artist    TEXT,
    created_at        TEXT,
    expires_at        TEXT,               -- created_at + 24/48/72h, fixed set only
    duration_hours    INTEGER,            -- 24 | 48 | 72, stored for display/audit
    delivery_method   TEXT,               -- 'copy' | 'email' | NULL (not yet delivered)
    recipient_email   TEXT,               -- nullable — only set if emailed
    from_display_name TEXT,               -- editable display name used at send time
    revoked           INTEGER DEFAULT 0,  -- host can revoke early (free with DB-row design)
    access_count      INTEGER DEFAULT 0,
    last_accessed_at  TEXT
)
""")

# ---------------------------------------------------------------
# Shared config (host-set, not per-ride/per-share)
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
