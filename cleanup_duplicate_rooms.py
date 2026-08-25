import sqlite3
import config
conn = sqlite3.connect(config.DB_PATH)
rows = conn.execute("SELECT session_id, room_name, started_at FROM room_sessions WHERE ended_by_admin = 0 ORDER BY started_at DESC").fetchall()
print(f"Active rooms found: {len(rows)}")
for r in rows:
    print(" -", r)
if len(rows) > 1:
    keep = rows[0][0]
    conn.execute("UPDATE room_sessions SET ended_by_admin = 1 WHERE ended_by_admin = 0 AND session_id != ?", (keep,))
    conn.commit()
    print(f"Ended {len(rows)-1} stale duplicate room(s), kept the newest: {keep}")
else:
    print("No cleanup needed.")
conn.close()
