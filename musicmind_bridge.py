"""
Player -- optional read-only bridge into MusicMind's plex_music_brain.db.

Fully optional: if config.MUSICMIND_DB_PATH isn't set or the file
isn't reachable, every function here falls back to Player's own
live-Plex search/mood-bucket code with no degraded functionality.

POOL_SIZE governs how many results get built and cached per query --
a page is then sliced from this pool via result_cache.paged(), rather
than each page triggering its own rebuild.
"""
import os
import bisect
import sqlite3
import random

import config
import plex_client
import result_cache

POOL_SIZE = 200


def is_available():
    path = getattr(config, "MUSICMIND_DB_PATH", "")
    return bool(path) and os.path.exists(path)


def _connect():
    return sqlite3.connect(f"file:{config.MUSICMIND_DB_PATH}?mode=ro", uri=True)


def _row_to_track_dict(row):
    try:
        rating_key = int(row["rating_key"])
    except (TypeError, ValueError):
        return None
    duration_ms = row["duration_ms"] if row["duration_ms"] is not None else 0
    return {
        "rating_key": rating_key,
        "title": row["title"],
        "artist": row["artist"],
        "album": row["album"],
        "duration_sec": int(duration_ms / 1000),
    }


def _musicmind_search(query, limit=POOL_SIZE):
    q_like = f"%{query.lower()}%"
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        artist_rows = conn.execute(
            "SELECT rating_key, title, artist, album, duration_ms "
            "FROM tracks WHERE LOWER(artist) LIKE ? LIMIT ?",
            (q_like, limit),
        ).fetchall()
        title_rows = conn.execute(
            "SELECT rating_key, title, artist, album, duration_ms "
            "FROM tracks WHERE LOWER(title) LIKE ? LIMIT ?",
            (q_like, limit),
        ).fetchall()
    finally:
        conn.close()

    results = []
    seen = set()
    for row in list(artist_rows) + list(title_rows):
        d = _row_to_track_dict(row)
        if d and d["rating_key"] not in seen:
            seen.add(d["rating_key"])
            results.append(d)
    return results[:limit]


def _build_search_pool(query):
    if is_available():
        try:
            results = _musicmind_search(query, limit=POOL_SIZE)
            if results:
                return results
        except Exception:
            pass
    return plex_client.search_tracks(query, limit=POOL_SIZE)


def search_tracks_page(query, offset=0, limit=20):
    cache_key = ("search", query.lower())
    pool = result_cache.cache_get(cache_key)
    if pool is None:
        pool = _build_search_pool(query)
        result_cache.cache_set(cache_key, pool)
    return result_cache.paged(pool, offset, limit)


def _mood_pool_from_musicmind(mood_key, pool_size=POOL_SIZE):
    keywords = plex_client.MOOD_BUCKETS.get(mood_key.lower(), [mood_key.lower()])

    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        like_clauses = " OR ".join(["LOWER(tag) LIKE ?"] * len(keywords))
        params = [f"%{kw.lower()}%" for kw in keywords]
        tag_rows = conn.execute(
            f"SELECT DISTINCT rating_key FROM track_tags WHERE {like_clauses}",
            params,
        ).fetchall()

        matched_keys = [row["rating_key"] for row in tag_rows]
        if not matched_keys:
            return []

        placeholders = ",".join("?" * len(matched_keys))
        track_rows = conn.execute(
            "SELECT rating_key, title, artist, album, duration_ms "
            f"FROM tracks WHERE rating_key IN ({placeholders})",
            matched_keys,
        ).fetchall()
    finally:
        conn.close()

    pool = [d for d in (_row_to_track_dict(r) for r in track_rows) if d]
    random.shuffle(pool)
    return pool[:pool_size]


def _build_mood_pool(mood_key, instrumental_only):
    pool = []
    if is_available():
        try:
            pool = _mood_pool_from_musicmind(mood_key, pool_size=POOL_SIZE)
        except Exception:
            pool = []

    if not pool:
        pool = plex_client.tracks_by_mood(mood_key, limit=POOL_SIZE)

    if instrumental_only and is_available() and pool:
        pool = _filter_instrumental(pool)

    return pool


def tracks_by_mood_page(mood_key, offset=0, limit=20, instrumental_only=False, shuffle_seed=None):
    """Cached, paginated mood-bucket lookup. The cached pool is the
    same every time, but paged_shuffled() pages through a shuffled
    copy of it, so repeat clicks surface different tracks while
    "load more" within one click still pages correctly with no
    duplicates (see its own docstring)."""
    cache_key = ("mood", mood_key.lower(), instrumental_only)
    pool = result_cache.cache_get(cache_key)
    if pool is None:
        pool = _build_mood_pool(mood_key, instrumental_only)
        result_cache.cache_set(cache_key, pool, ttl=result_cache._MOOD_CACHE_TTL)
    return result_cache.paged_shuffled(pool, offset, limit, seed=shuffle_seed)


def available_tags(min_count=21):
    """The library's most common, reliable tags from MusicMind's
    track_tags table -- far more granular than tracks.genre's 17
    broad categories (confirmed directly against real data: track_tags
    has entries like "new wave" (4,364 tracks), "synth-pop",
    "post-punk", "psychedelic rock" -- exactly the kind of specific
    genre the broad genre field collapses into "Pop/Rock"). Mood/
    energy descriptors ("upbeat", "nostalgic", "melodic") live in this
    same table with no distinguishing column -- confirmed directly,
    both kinds show up mixed in the top results. Returning both
    together, not trying to separate them, is a deliberate scoping
    decision (discussed and confirmed), not an oversight.

    min_count filters the long tail: confirmed directly that
    track_tags has thousands of distinct tags total, but the vast
    majority are noisy, one-off AI-tagging quirks (occurring only a
    handful of times) rather than reliable descriptors -- around 600
    tags clear a 21-occurrence bar. Cached like every other
    library-wide pool here.

    Returns None if MusicMind isn't available."""
    if not is_available():
        return None
    cache_key = ("available_tags", min_count)
    cached = result_cache.cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        conn = _connect()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT tag, COUNT(*) AS cnt FROM track_tags "
                "GROUP BY tag HAVING cnt >= ? ORDER BY cnt DESC",
                (min_count,),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return None
    result = [{"tag": r["tag"], "count": r["cnt"]} for r in rows]
    result_cache.cache_set(cache_key, result, ttl=result_cache._MOOD_CACHE_TTL)
    return result


def tracks_by_tag_page(tag, offset=0, limit=20, shuffle_seed=None):
    """Paginated, cached track list for an exact tag match against
    MusicMind's own track_tags table (joined back to tracks for the
    actual track data). track_tags has a UNIQUE(rating_key, tag)
    constraint, so this join can't produce duplicate rows for a single
    tag query. Pages through a shuffled copy of the cached pool (see
    result_cache.paged_shuffled()'s own docstring) so repeat Explore
    submissions for the same tag surface different tracks.

    Returns None if MusicMind isn't available."""
    if not is_available():
        return None
    cache_key = ("tag_pool", tag.lower())
    pool = result_cache.cache_get(cache_key)
    if pool is None:
        try:
            conn = _connect()
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT t.rating_key, t.title, t.artist, t.album, t.duration_ms "
                    "FROM tracks t JOIN track_tags tt ON tt.rating_key = t.rating_key "
                    "WHERE LOWER(tt.tag) = ?",
                    (tag.lower(),),
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            return None
        pool = [t for t in (_row_to_track_dict(r) for r in rows) if t]
        if pool:  # never cache an empty result -- it would stick for an hour
            result_cache.cache_set(cache_key, pool, ttl=result_cache._MOOD_CACHE_TTL)
    return result_cache.paged_shuffled(pool, offset, limit, seed=shuffle_seed)


def _filter_instrumental(tracks):
    rating_keys = [str(t["rating_key"]) for t in tracks]
    try:
        conn = _connect()
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in rating_keys)
        rows = conn.execute(
            f"SELECT rating_key FROM tracks "
            f"WHERE rating_key IN ({placeholders}) AND is_instrumental = 1",
            rating_keys,
        ).fetchall()
        conn.close()
        instrumental_keys = {str(row["rating_key"]) for row in rows}
    except Exception:
        return tracks
    return [t for t in tracks if str(t["rating_key"]) in instrumental_keys]


# --- Track browsing --------------------------------------------------------

def _all_tracks_from_musicmind():
    """Fast path: every track directly from MusicMind's own table, no
    filter. Only selects columns already proven to exist elsewhere in
    this file (rating_key/title/artist/album/duration_ms) -- no
    assumption about an added_at-style column that's never actually
    been queried anywhere in this codebase."""
    conn = _connect()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT rating_key, title, artist, album, duration_ms FROM tracks"
        ).fetchall()
    finally:
        conn.close()
    return [d for d in (_row_to_track_dict(r) for r in rows) if d]


def _build_track_browse_pool():
    """Prefer MusicMind (a local SQLite table scan, fast even for a
    large library), fall back to live Plex on any failure or if
    MusicMind isn't configured."""
    if is_available():
        try:
            pool = _all_tracks_from_musicmind()
            if pool:
                return pool
        except Exception:
            pass
    return plex_client.list_all_tracks()


_TRACK_SORTS = {
    "title": lambda t: t["title"].lower(),
    "artist": lambda t: (t["artist"].lower(), t["title"].lower()),
    "album": lambda t: (t["album"].lower(), t["title"].lower()),
}


_SORT_MEMO = {"pool": None, "sorted": {}, "letters": None}


def _sorted_track_pool(pool, sort):
    """Sorted view of the cached track pool, computed once per pool
    per sort order instead of on every page/letter request. Tied to
    the pool object's identity, so it resets automatically whenever
    the underlying pool is rebuilt after its TTL."""
    if _SORT_MEMO["pool"] is not pool:
        _SORT_MEMO["pool"] = pool
        _SORT_MEMO["sorted"] = {}
        _SORT_MEMO["letters"] = None
    key = sort if sort in _TRACK_SORTS else "title"
    cached = _SORT_MEMO["sorted"].get(key)
    if cached is None:
        cached = sorted(pool, key=_TRACK_SORTS[key])
        _SORT_MEMO["sorted"][key] = cached
    return cached


def _title_letter_offset(sorted_pool, letter):
    """A-Z quickbar lookup against a title-sorted pool; the key list
    is built once per sorted pool, then each tap is a binary search."""
    idx = _SORT_MEMO["letters"]
    if idx is None or idx[0] is not sorted_pool:
        keys = [(t["title"] or "").lower() for t in sorted_pool]
        first_non_alpha = next(
            (i for i, k in enumerate(keys) if not k or not k[0].isalpha()),
            len(keys),
        )
        idx = (sorted_pool, keys, first_non_alpha)
        _SORT_MEMO["letters"] = idx
    _, keys, first_non_alpha = idx
    letter = letter.lower()
    if letter == "#":
        return first_non_alpha
    return bisect.bisect_left(keys, letter)


def browse_tracks_page(offset=0, limit=48, sort="title"):
    """Cached, paginated, sorted track browse. One cached pool serves
    every sort order (sorting an already-fetched in-memory list is
    cheap), same pattern as library_browse.py's artist/album pools."""
    cache_key = ("browse_tracks",)
    pool = result_cache.cache_get(cache_key)
    if pool is None:
        pool = _build_track_browse_pool()
        result_cache.cache_set(cache_key, pool, ttl=result_cache._MOOD_CACHE_TTL)
    sorted_pool = _sorted_track_pool(pool, sort)
    return result_cache.paged(sorted_pool, offset, limit)


def track_letter_offset(letter):
    """Powers the A-Z quickbar for Browse Tracks. Only meaningful for
    the default title sort -- see result_cache.offset_for_letter()'s
    own docstring for why."""
    cache_key = ("browse_tracks",)
    pool = result_cache.cache_get(cache_key)
    if pool is None:
        pool = _build_track_browse_pool()
        result_cache.cache_set(cache_key, pool, ttl=result_cache._MOOD_CACHE_TTL)
    sorted_pool = _sorted_track_pool(pool, "title")
    return _title_letter_offset(sorted_pool, letter)


# --- Album search ------------------------------------------------------

_PARENT_KEY_MEMO = {}


def _album_key_for_track(plex, rating_key):
    """A track's album key rarely changes, so remember it instead of
    paying a Plex round trip every time the same album matches a
    (prefix) search again."""
    rk = int(rating_key)
    if rk not in _PARENT_KEY_MEMO:
        _PARENT_KEY_MEMO[rk] = plex.fetchItem(rk).parentRatingKey
    return _PARENT_KEY_MEMO[rk]


def search_albums(query, limit=8):
    """Fast album search: match against MusicMind's own track-level
    album/artist columns (grouped so one representative track stands
    in per album), then resolve each MATCHED album's real Plex rating
    key via a single targeted fetchItem() call per match -- NOT a full
    library-wide album walk. At most `limit` such targeted calls, not
    thousands.

    Returns None (caller falls back to the live-Plex full walk) if
    MusicMind isn't available or anything here fails -- this is a
    pure speed optimization, never a hard dependency."""
    if not is_available():
        return None

    q_like = f"%{query.lower()}%"
    try:
        conn = _connect()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT album, artist, MIN(rating_key) AS sample_rating_key "
                "FROM tracks WHERE LOWER(album) LIKE ? "
                "GROUP BY album, artist LIMIT ?",
                (q_like, limit),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return None

    results = []
    try:
        plex = plex_client.get_plex()
    except Exception:
        return None

    for row in rows:
        try:
            album_key = _album_key_for_track(plex, row["sample_rating_key"])
            results.append({
                "content_ref": album_key,
                "title": row["album"],
                "subtitle": row["artist"],
            })
        except Exception:
            # This one album's sample track is gone/stale in MusicMind's
            # snapshot -- skip just this result, not the whole search.
            continue
    return results


def search_tracks_for_share(query, limit=8):
    """Fast track search for Share Mode -- reuses the same proven
    _musicmind_search() Player's own search already relies on, just
    reshaped to the {content_ref, title, subtitle} shape Share's
    picker expects instead of the fuller track-dict shape.

    Genuinely fixes a correctness bug, not just speed: Plex's own
    title__icontains filter (used by the live-Plex fallback in
    search_content()) was confirmed NOT matching real, existing
    multi-word titles -- "Les Fleurs" by Minnie Riperton, verified
    directly to exist in MusicMind's own database, never appeared in
    live-Plex search results for that exact query. MusicMind's literal
    SQL LIKE match doesn't share whatever tokenization quirk Plex's API
    has for multi-word phrases.

    Returns None (caller falls back to the live-Plex path) if
    MusicMind isn't available -- this is a speed AND correctness
    improvement, never a hard dependency."""
    if not is_available():
        return None
    try:
        tracks = _musicmind_search(query, limit=limit)
    except Exception:
        return None
    return [
        {
            "content_ref": t["rating_key"],
            "title": t["title"],
            "subtitle": t["artist"],
        }
        for t in tracks
    ]


def search_albums_for_player(query, limit=5):
    """Fast album search for Player's own main search box -- same
    approach as search_albums() (match locally against MusicMind's
    track-level album/artist columns, grouped, then resolve each
    match's real Plex rating key via a targeted fetchItem() call), but
    returns the {rating_key, title, artist, year} shape Browse's own
    albumTile() renderer expects, rather than Share's
    {content_ref, title, subtitle} shape. Kept as a separate function
    rather than generalizing search_albums() itself -- that one is
    proven and tested for Share; safer not to touch it for this.

    Deliberately small limit (5, not search_albums()'s 8) -- this is a
    "top album matches" section above the main track results, not a
    paginated list of its own.

    Returns None (caller falls back to no albums shown -- the main
    live-Plex-backed track search still works either way) if MusicMind
    isn't available or anything here fails."""
    if not is_available():
        return None

    q_like = f"%{query.lower()}%"
    try:
        conn = _connect()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT album, artist, year, MIN(rating_key) AS sample_rating_key "
                "FROM tracks WHERE LOWER(album) LIKE ? "
                "GROUP BY album, artist LIMIT ?",
                (q_like, limit),
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return None

    results = []
    try:
        plex = plex_client.get_plex()
    except Exception:
        return None

    for row in rows:
        try:
            album_key = _album_key_for_track(plex, row["sample_rating_key"])
            results.append({
                "rating_key": album_key,
                "title": row["album"],
                "artist": row["artist"],
                "year": row["year"],
            })
        except Exception:
            continue
    return results
