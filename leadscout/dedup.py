from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlparse

_TRACKING = ("utm_", "fbclid", "gclid", "ref", "share", "context")


def is_reddit_domain(host: str) -> bool:
    h = host.lower()
    return (
        h == "reddit.com"
        or h.endswith(".reddit.com")
        or "birdcat.cafe" in h
        or "libreddit" in h
        or "teddit" in h
        or "redlib" in h
    )


def normalise_url(url: str) -> str:
    url_str = (url or "").strip()
    if not url_str:
        return ""
    p = urlparse(url_str)
    if not p.netloc:
        return url_str
    host = p.netloc.lower()
    scheme = p.scheme or "https"
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(_TRACKING)]
    query_str = f"?{urlencode(q)}" if q else ""
    if is_reddit_domain(host):
        path = p.path.rstrip('/')
        return f"https://www.reddit.com{path}{query_str}"
    path = p.path.rstrip('/')
    return f"{scheme}://{host}{path}{query_str}"


def canonical_url(url: str) -> str:
    p = urlparse((url or "").strip())
    host = p.netloc.lower()
    if is_reddit_domain(host):
        host = "reddit.com"
    else:
        for prefix in ("www.", "old.", "np.", "m."):
            if host.startswith(prefix):
                host = host[len(prefix):]
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(_TRACKING)]
    return f"{host}{p.path.rstrip('/')}" + (f"?{urlencode(q)}" if q else "")


def _words(text: str):
    return re.findall(r"\w+", (text or "").lower())


def shingles(text: str, n: int = 3):
    w = _words(text)
    if len(w) < n:
        return {tuple(w)} if w else set()
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def fingerprint(url: str, text: str) -> str:
    key = canonical_url(url) + "|" + " ".join(_words(text)[:30])
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def is_duplicate(a, b, threshold: float = 0.8) -> bool:
    """Same URL + mostly same text, or near-identical text anywhere (cross-posts, reposts)."""
    sim = jaccard(shingles(a.title + " " + a.snippet), shingles(b.title + " " + b.snippet))
    same_url = canonical_url(a.url) == canonical_url(b.url)
    return (same_url and sim >= 0.6) or sim >= threshold


def dedup(items, against=()):
    """Drop duplicates within `items` and versus already-stored `against`.
    Prefers items with a known date, then longer text. Returns (kept, dropped_count)."""
    ordered = sorted(items, key=lambda l: (l.date_status == "unknown", -len(l.snippet)))
    kept, dropped = [], 0
    pool = list(against)
    for it in ordered:
        if any(is_duplicate(it, k) for k in pool):
            dropped += 1
            continue
        kept.append(it)
        pool.append(it)
    return kept, dropped
