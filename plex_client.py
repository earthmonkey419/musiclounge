"""
Plex client wrapper for MusicLounge.

Layered search and mood-bucket matching follow RiderMusic's proven
pattern exactly (see RIDERMUSIC-PROJECT-SYNOPSIS.md): literal artist
match first, then literal track-title match, then Plex's fuzzy hub
search as a last resort -- preserving fuzzy matching for genuinely
vague queries (the mood pills) while fixing the "search for one
artist, get a loosely related one instead" problem hub search has on
its own.

NOT YET VERIFIED against a real Plex server -- built from the
documented plexapi API surface, but this environment has no network
path to your NAS/Plex to test against. Run a real search before
trusting this in front of a guest. If field-testing turns up a
mismatch with plexapi's actual behavior, that's expected -- fix here,
not a sign the approach is wrong.
"""
import random
import time
from plexapi.server import PlexServer
import config

_plex = None


def get_plex():
    global _plex
    if _plex is None:
        # Short timeout deliberately -- an unreachable Plex server should
        # fail a guest's search request in a few seconds, not hang for
        # plexapi's ~30s default and make the whole app feel broken.
        _plex = PlexServer(config.PLEX_URL, config.PLEX_TOKEN, timeout=6)
    return _plex


def get_music_section():
    return get_plex().library.section(config.MUSIC_LIB)


MOOD_BUCKETS = {
    "funk": ["funk"],
    "soul": ["soul", "r&b", "rnb"],
    "jazz": ["jazz"],
    "dance": ["dance", "disco", "electronic"],
    "chill": ["chill", "ambient", "downtempo", "lounge"],
    "rock": ["rock"],
}


def _track_to_dict(track):
    duration_sec = int((track.duration or 0) / 1000)
    return {
        "rating_key": track.ratingKey,
        "title": track.title,
        "artist": track.grandparentTitle or track.originalTitle or "Unknown Artist",
        "album": track.parentTitle or "",
        "duration_sec": duration_sec,
    }


def search_tracks(query, limit=20):
    """Layered search: literal artist match, then literal title match,
    then Plex's fuzzy hub search. Returns a list of track dicts,
    deduplicated by rating_key, capped at `limit`.

    Ported to match RiderMusic's exact proven implementation after
    real-world testing found two root-cause bugs in the original
    version here:
    1. Artist match used section.searchArtists(title=query), trusting
       Plex's server-side title filter -- RiderMusic instead fetches
       ALL artists (no title kwarg) and filters client-side by
       substring, which is what actually works reliably.
    2. Title match used section.searchTracks(title=query, ...) --
       plain title= does not do a substring/contains match. The fix
       is the `title__icontains` filter operator, which does. This
       alone explains "the firstborn" returning nothing (partial
       phrase match) while "blind lemon jefferson" (matching a full
       track title) worked."""
    section = get_music_section()
    q_lower = query.lower()
    results = []
    seen = set()

    def add(tracks):
        for t in tracks:
            if t.ratingKey not in seen:
                seen.add(t.ratingKey)
                results.append(_track_to_dict(t))

    try:
        all_artists = section.searchArtists()
        matching_artists = [a for a in all_artists if q_lower in a.title.lower()]
        for artist in matching_artists[:8]:
            add(artist.tracks()[:20])
    except Exception:
        pass

    if len(results) < limit:
        try:
            add(section.searchTracks(title__icontains=query, limit=limit))
        except Exception:
            pass

    if not results:
        try:
            hub_results = get_plex().search(query, mediatype="track")
            add(hub_results[:limit])
        except Exception:
            pass

    return results[:limit]


def tracks_by_mood(mood_key, limit=12):
    """Genre-tag lookup for one mood bucket -- Player's live-Plex
    fallback when MusicMind isn't available (see musicmind_bridge.py
    for the preferred fast path).

    Ported to match RiderMusic's proven approach after the same
    root-cause bug found in search_tracks(): the original version
    here queried section.searchTracks(genre=keyword, limit=limit)
    with our own guessed keyword (e.g. "soul") as an exact match --
    but real Plex genre tags are specific ("Neo-Soul", "Motown"), so
    an exact match against a guessed keyword rarely hits anything.
    The fix: enumerate the library's REAL genre tag vocabulary via
    listFilterChoices(), filter those tag strings by keyword substring
    client-side, then query exactly per real matching tag."""
    keywords = MOOD_BUCKETS.get(mood_key.lower())
    if not keywords:
        return []
    section = get_music_section()
    results = []
    seen = set()
    try:
        all_genres = section.listFilterChoices("genre", libtype="track")
        matching_tags = [
            g.title for g in all_genres
            if any(kw in g.title.lower() for kw in keywords)
        ]
        for tag in matching_tags:
            if len(results) >= limit:
                break
            tracks = section.searchTracks(**{"track.genre": tag}, limit=limit)
            for t in tracks:
                if t.ratingKey not in seen:
                    seen.add(t.ratingKey)
                    results.append(_track_to_dict(t))
                if len(results) >= limit:
                    break
    except Exception:
        pass
    return results[:limit]


def get_track(rating_key):
    """Fetch a single track by rating key. Raises if not found --
    callers should handle (e.g. queue-add against a stale/deleted
    library item)."""
    return get_plex().fetchItem(int(rating_key))


def search_content(content_type, query, limit=8):
    """Content-type-scoped search for Share Mode's predictive selector
    (track/album/playlist/artist), separate from search_tracks()'s
    free-text track search. Returns dicts with content_ref/title/subtitle.

    Every branch explicitly checks item.type before including a
    result -- real-world testing surfaced that a plain
    section.search(libtype=...) call can return a mismatched type
    (an Artist result for an album search), so type is verified
    directly rather than trusted from the query method alone."""
    content_type = content_type.lower()
    results = []
    try:
        if content_type == "track":
            section = get_music_section()
            for item in section.searchTracks(title=query, limit=limit * 2):
                if getattr(item, "type", None) != "track":
                    continue
                results.append({
                    "content_ref": item.ratingKey,
                    "title": item.title,
                    "subtitle": item.grandparentTitle,  # artist
                })
        elif content_type == "album":
            section = get_music_section()
            try:
                items = section.searchAlbums(title=query, limit=limit * 2)
            except AttributeError:
                items = section.search(title=query, libtype="album", limit=limit * 2)
            for item in items:
                if getattr(item, "type", None) != "album":
                    continue
                results.append({
                    "content_ref": item.ratingKey,
                    "title": item.title,
                    "subtitle": item.parentTitle,  # album's parent IS the artist
                })
        elif content_type == "artist":
            section = get_music_section()
            for item in section.searchArtists(title=query, limit=limit * 2):
                if getattr(item, "type", None) != "artist":
                    continue
                results.append({
                    "content_ref": item.ratingKey,
                    "title": item.title,
                    "subtitle": "Artist",
                })
        elif content_type == "playlist":
            q = query.lower()
            for item in get_plex().playlists():
                if getattr(item, "type", None) != "playlist":
                    continue
                if q in item.title.lower():
                    results.append({
                        "content_ref": item.ratingKey,
                        "title": item.title,
                        "subtitle": f"{getattr(item, 'leafCount', '?')} tracks",
                    })
                if len(results) >= limit:
                    break
    except Exception:
        raise
    return results[:limit]


def get_content_tracks(content_type, rating_key, limit=100):
    """Resolves a shared track/album/playlist/artist into (title,
    artist, [track dicts]) for the /linked player. Artist mode caps
    at the first 10 albums to avoid pulling an entire discography."""
    item = get_plex().fetchItem(int(rating_key))
    content_type = content_type.lower()

    if content_type == "track":
        title = item.title
        artist = item.grandparentTitle
        tracks = [item]
    elif content_type == "album":
        title = item.title
        artist = item.parentTitle
        tracks = item.tracks()[:limit]
    elif content_type == "playlist":
        title = item.title
        artist = None
        # Ask Plex for only the first `limit` items. item.items() downloads
        # the ENTIRE playlist (32K+ tracks for smart playlists like
        # "All Music", ~85s) just to slice off the first few.
        tracks = item.fetchItems(
            f"/playlists/{item.ratingKey}/items",
            container_start=0,
            container_size=limit,
            maxresults=limit,
        )
    elif content_type == "artist":
        title = item.title
        artist = item.title
        tracks = []
        for album in item.albums()[:10]:
            tracks.extend(album.tracks())
            if len(tracks) >= limit:
                break
        tracks = tracks[:limit]
    else:
        raise ValueError(f"Unknown content_type: {content_type}")

    return title, artist, [_track_to_dict(t) for t in tracks]


def track_art_path(rating_key):
    """Returns the Plex thumb `key` path (no token) for an item's cover
    art. Works for tracks (prefers the album's cover via parentThumb
    over the track's own, often-absent thumb) and also for whole
    albums/artists/playlists (used for /linked's hero image) -- those
    don't have parentThumb, so getattr-with-default avoids crashing on
    a valid item that's just a different shape."""
    item = get_track(rating_key)
    return getattr(item, "parentThumb", None) or getattr(item, "thumb", None)


def track_stream_part(rating_key):
    """Returns the Plex part `key` path (not a full URL, no token) for
    a track -- used by the streaming proxy, which attaches the real
    token server-side so it's never exposed to any client."""
    track = get_track(rating_key)
    return track.media[0].parts[0].key
