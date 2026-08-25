import sqlite3
import config

conn = sqlite3.connect(config.DB_PATH)
c = conn.cursor()
existing = {row[1] for row in c.execute("PRAGMA table_info(room_sessions)")}

new_columns = {
    "now_playing_ref": "TEXT",
    "now_playing_title": "TEXT",
    "now_playing_artist": "TEXT",
    "now_playing_duration": "INTEGER",
    "position_sec": "INTEGER DEFAULT 0",
    "is_playing": "INTEGER DEFAULT 0",
    "volume": "INTEGER DEFAULT 80",
    "last_skip_at": "TEXT",
}

added = []
for col, coltype in new_columns.items():
    if col not in existing:
        c.execute(f"ALTER TABLE room_sessions ADD COLUMN {col} {coltype}")
        added.append(col)

conn.commit()
conn.close()
print(f"Added columns: {added}" if added else "Schema already up to date.")
