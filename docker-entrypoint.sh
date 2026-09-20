#!/bin/sh
# init_db.py creates any missing tables (CREATE TABLE IF NOT EXISTS —
# safe every start). migrate_room_columns.py handles the case that
# leaves that alone: an EXISTING table (e.g. in a persisted Docker
# volume from before a schema change) missing newer columns — also
# safe to run every start, it checks before adding anything.
python init_db.py
python migrate_room_columns.py

# ONE worker on purpose: result_cache.py and the mood pools are plain
# in-process caches. Extra workers would each build their own copy, so a
# guest's "load more" could land on a worker holding a different pool.
# --threads 4 gives real concurrency within the single process.
exec gunicorn --bind 0.0.0.0:8679 --workers 1 --threads 16 --worker-class gthread app:app
