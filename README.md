<p align="center">
  <img src="assets/og-image.jpg" alt="MusicLounge Jukebox for Plex" width="100%">
</p>

# MusicLounge Jukebox for Plex

A self-hosted jukebox for your Plex music library — from the makers of
[MusicMind for Plex](https://musicmind.vp-fun.com/) and
[RiderMusic](https://ridermusic.vp-fun.com/).

Two ways to share your library: **Room Mode**, a shared queue people join
with a code and DJ together in real time, and **Share Mode**, a private
link to a single album, playlist, or artist that one person streams on
their own schedule. No login, no app install, either way.

**Status: scoped, in active development.** See
[`MUSICLOUNGE-SCOPE.md`](./MUSICLOUNGE-SCOPE.md) for the full design.

## How it works

```
Room Mode:   Guests (join code) -> shared queue -> one "now playing" -> host's device -> speakers
Share Mode:  Recipient -> /linked/<token> -> their own <audio> element, independent playback
                                |
                                v
                          Plex Media Server
```

- **Room Mode:** a host starts a session, guests join via code, everyone
  searches and queues from the library, one authoritative "now playing"
  drives every joined device.
- **Share Mode:** a host picks an album, playlist, or artist and mints a
  time-limited link (24/48/72 hours). The recipient opens `/linked/<token>`
  — a locked, single-item player, nothing else in the library exposed.
- Both modes proxy audio server-side, so the real Plex token never
  reaches a client browser.

## Requirements

- A Plex Media Server with a music library
- A way to expose the app to the internet — guests and share-link
  recipients both need to reach it from outside your home network. See
  "Exposing it to the internet" below.
- Docker (recommended), or Python 3.12+ for a manual install
- An SMTP relay, if you want Share Mode to email links (links are also
  always copyable directly, independent of email)

## Setup

### Docker (recommended)

```bash
git clone https://github.com/earthmonkey419/musiclounge.git
cd musiclounge

docker build -t musiclounge .
docker run -d --name musiclounge \
  -p 8679:8679 \
  -e PLEX_URL="http://10.0.0.251:32400" \
  -e PLEX_TOKEN="your-real-token" \
  -e MUSIC_LIB="Music" \
  -e ADMIN_PASSWORD="your-real-password" \
  -e COOKIE_SECURE="true" \
  -e DB_PATH="/app/data/musiclounge.db" \
  -v musiclounge-data:/app/data \
  musiclounge

# No config.py file needed — every setting reads from an environment
# variable first, falling back to a safe placeholder default if unset.
# The image already has a working config.py baked in (placeholders
# only, no real secrets), so the container boots even with zero -e
# flags; just be sure to actually set the real ones above before
# relying on it. Still want a file instead? Bind-mount one the old
# way (-v $(pwd)/config.py:/app/config.py:ro) and it'll win over any
# env vars you also set.
```

Your real Plex token, admin password, and SMTP credentials only ever
exist as environment variables you set at `docker run` (or in
Portainer's UI) — Docker never writes an environment variable into
any image layer. The image does contain a `config.py`, but it's built
from `config.example.py`, which only has safe placeholder values
(`REPLACE_ME` etc.) — `.dockerignore` makes sure your *real* local
`config.py`, if you have one sitting in the build directory, never
enters the build context in the first place.

`musiclounge-data` is a named volume for the SQLite database (room
sessions, queue, and share links) so it survives container recreation —
**only works if `DB_PATH` actually points inside that mounted
directory** (`/app/data/musiclounge.db`, set via the `-e DB_PATH=...`
flag above). Worth knowing this if you're comparing against
RiderMusic's docker run command, which doesn't persist a data volume
the same way.

### Manual (Python)

```bash
git clone https://github.com/earthmonkey419/musiclounge.git
cd musiclounge
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config.example.py config.py
# edit config.py as above

python init_db.py
python app.py
```

App runs on port `8679` by default — chosen specifically because port
`8788` was already taken by another service on the NAS this was
originally built on. Check that `8679` is actually free on your own
box before relying on it; RiderMusic's own default is a different
port (`6869`) by its own separate design, not because of any
collision.

**Before real use:** `COOKIE_SECURE` must be `True`, which requires the
app to be served over HTTPS. `False` is for local development only.

**Getting a real Plex token:** see
[Plex's own guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

### Using Portainer

No SSH or File Station access needed — every real setting (Plex
token, admin password, SMTP credentials) can be filled in entirely
through Portainer's own UI.

1. In Portainer, go to Stacks then Add stack.
   Repository method (recommended): paste
   https://github.com/earthmonkey419/musiclounge.git as the
   repository URL, leave the compose path as docker-compose.yml,
   and deploy. Portainer builds the image automatically.
   Web editor method: paste the contents of docker-compose.yml
   directly instead, if you'd rather not have Portainer pull from
   GitHub itself.
2. Before (or after) deploying, edit the stack's Environment
   variables in Portainer's UI and paste something like this
   (adjust for your setup):

       HOST_PORT=8679
       PLEX_URL=http://10.0.0.251:32400
       PLEX_TOKEN=your-real-token
       MUSIC_LIB=Music
       ADMIN_PASSWORD=your-real-password
       SECRET_KEY=your-random-secret
       COOKIE_SECURE=false
       DB_PATH=/app/data/musiclounge.db
       SMTP_HOST=REPLACE_ME
       SMTP_PORT=587
       SMTP_USERNAME=REPLACE_ME
       SMTP_PASSWORD=REPLACE_ME
       SMTP_FROM_ADDRESS=REPLACE_ME
       SMTP_FROM_DISPLAY_NAME=MusicLounge

   Set HOST_PORT to something other than 8679 if that port is
   already taken on your box. Leave COOKIE_SECURE=false until this
   is genuinely behind HTTPS -- see the note above.
3. Once deployed, the app is reachable at http://your-host:HOST_PORT
   (8679 unless you changed it).

Prefer a file over environment variables? Uncomment the config.py
bind mount in docker-compose.yml instead — that still works exactly
like the file-based setup above, and takes priority over any
environment variables you also set.

## Exposing it to the internet

Both Room Mode guests and Share Mode recipients need to reach the app
from outside your home network.

**Cloudflare Tunnel is the tested, recommended path** (same as RiderMusic
and MusicMind). Broad steps, assuming you already have a domain on
Cloudflare:

1. In the Cloudflare Zero Trust dashboard, create a tunnel (or reuse an
   existing one if you're already running other services through
   Cloudflare)
2. Add a **Public Hostname** — pick a subdomain, and set the **Service
   URL** to `http://localhost:8679` (or whatever host/port MusicLounge is
   actually running on)
3. **Leave the Path field completely empty.** Setting it to something
   specific (e.g. testing `/admin/dashboard` first and forgetting to
   widen it) silently restricts routing to only that exact path — every
   other route (`/join`, `/guest`, `/linked/<token>`, static assets)
   will 404 even though the app itself is working fine. An empty Path
   routes the whole domain through.
4. Set `COOKIE_SECURE = True` in `config.py` and restart the app —
   Cloudflare terminates HTTPS at its edge, so cookies marked `Secure`
   will work correctly once traffic is genuinely coming through the
   tunnel's HTTPS endpoint.

## License

MIT
