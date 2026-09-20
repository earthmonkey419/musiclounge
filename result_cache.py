"""
Player -- in-process TTL cache for search/mood result pools.

Ported from RiderMusic's proven implementation. Exists because
building a mood-bucket pool from live Plex means one query per
matching genre tag -- RiderMusic measured a broad bucket like "rock"
taking ~25 seconds cold on a real library (60+ sequential Plex
queries). Without caching, every mood-pill tap would pay that cost
again.

NOTE: this is a plain in-process dict, assumes a single gunicorn
worker (mlplayer's ecosystem.config.cjs runs it that way).
"""
import random
import time

_RESULT_CACHE = {}
_CACHE_TTL = 600          # seconds -- search results
_MOOD_CACHE_TTL = 3600    # seconds -- mood pools are expensive to
                          # rebuild and don't depend on who's asking.


def cache_set(key, results, ttl=_CACHE_TTL):
    _RESULT_CACHE[key] = (time.time(), results, ttl)
    _evict_stale()


def cache_get(key):
    entry = _RESULT_CACHE.get(key)
    if not entry:
        return None
    ts, results, ttl = entry
    if time.time() - ts > ttl:
        _RESULT_CACHE.pop(key, None)
        return None
    return results


def _evict_stale():
    now = time.time()
    stale = [k for k, (ts, _, ttl) in list(_RESULT_CACHE.items()) if now - ts > ttl]
    for k in stale:
        _RESULT_CACHE.pop(k, None)


def paged(all_results, offset, limit):
    page = all_results[offset:offset + limit]
    has_more = (offset + limit) < len(all_results)
    return {
        "results": page,
        "has_more": has_more,
        "next_offset": offset + len(page),
    }


def paged_shuffled(all_results, offset, limit, seed=None):
    """Same as paged(), but pages through a shuffled copy of the pool
    instead of its natural order -- powers mood/genre browsing
    returning different tracks on repeat clicks, without the
    underlying (expensive-to-build) pool itself needing to change.

    seed=None means "start a new shuffle": a fresh random seed is
    generated and returned in the response. The caller (frontend)
    threads that same seed back on subsequent "load more" pagination
    calls within the same browse session, so random.Random(seed)
    deterministically reproduces the identical shuffled order each
    time -- pagination stays correct (no duplicate or skipped tracks
    as the user scrolls) even though the order itself is random.
    A fresh pill click / new Explore submission omits the seed again,
    getting a genuinely new shuffle."""
    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    shuffled = list(all_results)
    random.Random(seed).shuffle(shuffled)
    page = shuffled[offset:offset + limit]
    has_more = (offset + limit) < len(shuffled)
    return {
        "results": page,
        "has_more": has_more,
        "next_offset": offset + len(page),
        "seed": seed,
    }


def offset_for_letter(sorted_pool, key_fn, letter):
    """Given a pool already sorted by key_fn (ascending), finds the
    index of the first item whose key starts with a character >= the
    requested letter -- powers the Browse pages' A-Z quickbar jump.
    Binary search rather than a linear scan, since these pools can run
    into the thousands and this runs on every letter tap.

    Deliberately only meaningful when the pool is sorted by the exact
    field being jumped through (title, in every current caller) --
    jumping through a differently-sorted pool (e.g. sorted by year)
    wouldn't produce a meaningful letter-ordered position, so callers
    only expose the quickbar when sort="title" is active.

    "#" as `letter` jumps to the first non-letter-starting entry
    (numbers, symbols) -- everything before 'A' in a naive string
    comparison, which is exactly where those titles already sort to
    under plain alphabetical ordering.
    """
    import bisect
    letter = letter.upper()
    if letter == "#":
        for i, item in enumerate(sorted_pool):
            k = key_fn(item)
            if not k or not k[0].upper().isalpha():
                return i
        return len(sorted_pool)
    keys = [key_fn(item).upper() for item in sorted_pool]
    return bisect.bisect_left(keys, letter)
