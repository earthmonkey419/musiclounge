# MusicLounge Jukebox for Plex — config
# Copy to config.py and fill in real values. config.py is never committed
# and never baked into the Docker image (bind-mounted at runtime), same
# pattern as RiderMusic.

# --- Plex ---
PLEX_URL = "http://10.0.0.251:32400"     # local Plex Media Server URL
PLEX_TOKEN = "REPLACE_ME"                 # never exposed to any client
MUSIC_LIB = "Music"                       # library section name

# --- Admin ---
ADMIN_PASSWORD = "REPLACE_ME"             # single shared admin password, v1
COOKIE_SECURE = False                     # MUST be True in production (HTTPS only)
SECRET_KEY = "REPLACE_ME_RANDOM"          # Flask session signing key

# --- Server ---
HOST = "0.0.0.0"
PORT = 8679

# --- Database ---
# Docker users: set this to "/app/data/musiclounge.db" to match the
# musiclounge-data volume mount in the README — otherwise the DB lives
# in the container's root filesystem and gets wiped on every recreate.
DB_PATH = "musiclounge.db"

# --- Mode A: Room ---
ROOM_SESSION_TIMEOUT_MINUTES = 90         # auto-expire if driver doesn't end it
ROOM_VOLUME_CEILING = 80                  # guest volume clamp (0-100)
ROOM_SKIP_RATE_LIMIT_SECONDS = 20
ROOM_MAX_QUEUE_ADDS_PER_SESSION = 50

# --- Mode B: Share ---
SHARE_LINK_DURATIONS_HOURS = [24, 48, 72] # fixed set only, no arbitrary duration
SHARE_TOKEN_BYTES = 32                    # long, random, unguessable — see scope doc

# --- SMTP (Share Mode "Email It") ---
# Host's own SMTP relay — each self-hosted instance brings its own,
# same BYOK philosophy as the Plex token. Never sent to any client.
SMTP_HOST = "REPLACE_ME"                  # e.g. smtp.vp-fun.com or provider relay
SMTP_PORT = 587
SMTP_USERNAME = "REPLACE_ME"
SMTP_PASSWORD = "REPLACE_ME"
SMTP_USE_TLS = True
SMTP_FROM_ADDRESS = "REPLACE_ME"          # fixed, domain-verified — not user-editable
SMTP_FROM_DISPLAY_NAME = "MusicLounge"    # editable per-share at send time in the UI
