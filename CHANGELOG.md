# Changelog

All notable changes to MusicLounge Jukebox for Plex are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0]

### Added
- Room Mode: host-started sessions guests join with a code (QR supported), a shared real-time queue, and one authoritative Now Playing
- Real-time host dashboard
- Mood buckets for browsing
- Shuffle (Fisher-Yates)
- Share Mode: time-limited links (24/48/72 hours) to a single album, playlist, or artist, streamed at `/linked/<token>`
- Share link email delivery with album art; links always copyable independent of email
- Now Playing display on `/linked`
- Stats page
- Admin password reset via emailed single-use token (30-minute expiry)
- Back-to-top button
- Server-side Plex audio proxy, so the Plex token never reaches a browser
- SQLite storage in WAL mode for concurrent Room writers
- Docker support with bind-mounted `config.py` and a persistent data volume
- MIT license
