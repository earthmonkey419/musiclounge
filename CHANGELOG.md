# Changelog

All notable changes to MusicLounge Jukebox (Lite) for Plex are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security
- Share Mode creation (the page, library search, link creation, and "Email It") now requires the host login, same as starting a Room. Previously these were reachable without logging in, so anyone who could reach the app could browse the library, mint links, and send email through your SMTP settings. Recipients' `/linked/<token>` pages are unaffected
- `/stream/<id>` and `/art/<id>` no longer answer anonymous requests, which previously let anyone walk track IDs and download the whole library through the proxy. Audio is now limited to the host and to tracks in a share link the browser has opened (checked against the live share on every request, so expiry and "End this link" cut it off immediately). Cover art is also available to guests in a live Room, and to anyone for the shared item's own cover (share emails and link previews need it). Direct navigation to a stream URL (the browser's "save" path) is refused. This is access control, not DRM
- Cover art is now cached `private` rather than `public`
- Streams are sent `Content-Disposition: inline`, `X-Content-Type-Options: nosniff` and `Cache-Control: private`
- `/api/room-state` no longer returns the active room to visitors with no session (same resolution as Player)

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
