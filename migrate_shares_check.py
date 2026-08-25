import sqlite3
import config
conn = sqlite3.connect(config.DB_PATH)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("Tables present:", tables)
if "shares" not in tables:
    conn.execute("""
    CREATE TABLE shares (
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
    conn.commit()
    print("Created missing shares table.")
else:
    print("shares table already present.")
conn.close()
