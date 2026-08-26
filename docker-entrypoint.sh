#!/bin/sh
# init_db.py creates any missing tables (CREATE TABLE IF NOT EXISTS —
# safe every start). migrate_room_columns.py handles the case that
# leaves that alone: an EXISTING table (e.g. in a persisted Docker
# volume from before a schema change) missing newer columns — also
# safe to run every start, it checks before adding anything.
python init_db.py
python migrate_room_columns.py

exec gunicorn --bind 0.0.0.0:8679 --workers 2 --threads 4 --worker-class gthread app:app
