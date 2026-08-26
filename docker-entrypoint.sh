#!/bin/sh
# Ensures the DB schema exists before the app starts serving requests.
# init_db.py uses CREATE TABLE IF NOT EXISTS throughout — safe to run
# on every container start, not just the first one. Without this, a
# fresh container has an empty SQLite file and the first real request
# fails with "no such table".
python init_db.py

exec gunicorn --bind 0.0.0.0:8679 --workers 2 --threads 4 --worker-class gthread app:app
