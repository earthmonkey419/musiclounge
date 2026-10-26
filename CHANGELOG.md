# Changelog

All notable changes to MusicLounge Jukebox (Lite) for Plex are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `SHARE_REQUIRES_LOGIN` setting (default `true`): creating share links now requires the host login, the same as starting a Room. Set it to `false` to keep the previous open behavior

### Security
- Share creation, search, and "Email It" were reachable without logging in, so anyone who could reach the app could browse the library, mint links, and send email through your SMTP settings. They are now gated by default (reported in issue #2). Recipients' `/linked/<token>` pages are unaffected

## [1.1.0] - 2026-10-24

### Added
- Share links: recipients now see the artist on every track and the album in the Now Playing card, and can tap the album art to enlarge it

### Changed
- Renamed to MusicLounge Jukebox (Lite) for Plex

### Fixed
- Share creation: picking a search result no longer fails for titles containing an apostrophe (e.g. "Sgt. Pepper's")
- Compilation/Various Artists tracks now show the real per-track artist (`originalTitle`) instead of the album artist

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
