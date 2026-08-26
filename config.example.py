"""
MusicLounge Jukebox for Plex — config.

Two valid ways to use this file:

1. File-based (PM2/manual install, or Docker with a bind mount):
   copy this to config.py and edit the values directly.

2. Environment-variable-based (Docker/Portainer): every setting below
   checks os.environ first. Set real values as environment variables
   in your docker-compose.yml or Portainer's Environment variables UI
   — no file editing or SSH access needed. The Docker image already
   has a working copy of this file baked in (safe placeholder values
   only, no real secrets), so the container boots with zero file
   mounts required; env vars override the placeholders at runtime.

Either way works — mix and match if you like (e.g. edit DB_PATH in
the file, but set PLEX_TOKEN via a Portainer secret).
"""
import os


def _bool(key, default):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(key, default):
    val = os.environ.get(key)
    return int(val) if val is not None else default


def _int_list(key, default):
    val = os.environ.get(key)
    if val is None:
        return default
    return [int(x.strip()) for x in val.split(",") if x.strip()]


# --- Plex ---
PLEX_URL = os.environ.get("PLEX_URL", "http://10.0.0.251:32400")   # local Plex Media Server URL
PLEX_TOKEN = os.environ.get("PLEX_TOKEN", "REPLACE_ME")             # never exposed to any client
MUSIC_LIB = os.environ.get("MUSIC_LIB", "Music")                    # library section name

# --- Admin ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "REPLACE_ME")     # single shared admin password, v1
COOKIE_SECURE = _bool("COOKIE_SECURE", False)                       # MUST be True in production (HTTPS only)
SECRET_KEY = os.environ.get("SECRET_KEY", "REPLACE_ME_RANDOM")      # Flask session signing key

# --- Server ---
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = _int("PORT", 8679)

# --- Database ---
# Docker users: set to "/app/data/musiclounge.db" to match the
# musiclounge-data volume mount in the README — otherwise the DB lives
# in the container's root filesystem and gets wiped on every recreate.
DB_PATH = os.environ.get("DB_PATH", "musiclounge.db")

# --- Mode A: Room ---
ROOM_SESSION_TIMEOUT_MINUTES = _int("ROOM_SESSION_TIMEOUT_MINUTES", 90)   # auto-expire if driver doesn't end it
ROOM_VOLUME_CEILING = _int("ROOM_VOLUME_CEILING", 80)                     # guest volume clamp (0-100)
ROOM_SKIP_RATE_LIMIT_SECONDS = _int("ROOM_SKIP_RATE_LIMIT_SECONDS", 20)
ROOM_MAX_QUEUE_ADDS_PER_SESSION = _int("ROOM_MAX_QUEUE_ADDS_PER_SESSION", 50)

# --- Mode B: Share ---
# Comma-separated if set via env var, e.g. SHARE_LINK_DURATIONS_HOURS=24,48,72
SHARE_LINK_DURATIONS_HOURS = _int_list("SHARE_LINK_DURATIONS_HOURS", [24, 48, 72])
SHARE_TOKEN_BYTES = _int("SHARE_TOKEN_BYTES", 32)   # long, random, unguessable — see scope doc

# --- SMTP (Share Mode "Email It") ---
# Host's own SMTP relay — each self-hosted instance brings its own,
# same BYOK philosophy as the Plex token. Never sent to any client.
SMTP_HOST = os.environ.get("SMTP_HOST", "REPLACE_ME")               # e.g. smtp.vp-fun.com or provider relay
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "REPLACE_ME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "REPLACE_ME")
SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
SMTP_FROM_ADDRESS = os.environ.get("SMTP_FROM_ADDRESS", "REPLACE_ME")           # fixed, domain-verified — not user-editable
SMTP_FROM_DISPLAY_NAME = os.environ.get("SMTP_FROM_DISPLAY_NAME", "MusicLounge") # editable per-share at send time in the UI
