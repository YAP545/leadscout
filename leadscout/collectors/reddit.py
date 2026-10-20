from __future__ import annotations
import os, time
from datetime import datetime, timezone
import requests
from ..models import RawPost

UA = "script:leadscout-research:v0.1 (contact: %s)" % os.getenv("LEADSCOUT_CONTACT", "unset")

class RedditAccessError(RuntimeError):
    pass

def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None

def parse_listing(payload, query="", sub=""):
    for c in payload.get("data", {}).get("children", []):
        d = c.get("data", {})
        if d.get("over_18") or not d.get("permalink"):
            continue
        yield RawPost(url="https://www.reddit.com" + d["permalink"], platform="reddit",
                      title=d.get("title", ""), text=d.get("selftext", ""),
                      posted_at=_iso(d.get("created_utc")), source_query=query,
                      context=f"r/{d.get('subreddit', sub)}", date_source="api")

def submission_to_post(s, query="", sub=""):
    if getattr(s, "over_18", False) or not getattr(s, "permalink", ""):
        return None
    return RawPost(url="https://www.reddit.com" + s.permalink, platform="reddit",
                   title=getattr(s, "title", ""), text=getattr(s, "selftext", "") or "",
                   posted_at=_iso(getattr(s, "created_utc", None)), source_query=query,
                   context=f"r/{sub}", date_source="api")

def has_credentials():
    return bool(os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"))

def fetch_oauth(subreddits, queries, limit=50, period="month", delay=1.0):
    import praw
    r = praw.Reddit(client_id=os.environ["REDDIT_CLIENT_ID"],
                    client_secret=os.environ["REDDIT_CLIENT_SECRET"],
                    user_agent=UA, check_for_async=False)
    r.read_only = True
    for sub in subreddits:
        for q in queries:
            for s in r.subreddit(sub).search(q, sort="new", time_filter=period, limit=limit):
                p = submission_to_post(s, q, sub)
                if p:
                    yield p
            time.sleep(delay)

def fetch_anonymous(subreddits, queries, limit=50, delay=2.5, period="month"):
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    for sub in subreddits:
        for q in queries:
            r = sess.get(f"https://www.reddit.com/r/{sub}/search.json",
                         params={"q": q, "restrict_sr": 1, "sort": "new", "t": period, "limit": limit},
                         timeout=20)
            if r.status_code in (401, 403):
                raise RedditAccessError(
                    "Reddit blocked the anonymous request (HTTP %d). Create a free 'script' app at "
                    "https://www.reddit.com/prefs/apps, set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET, "
                    "then re-run." % r.status_code)
            if r.status_code == 429:
                time.sleep(30)
                continue
            r.raise_for_status()
            yield from parse_listing(r.json(), q, sub)
            time.sleep(delay)

def fetch(subreddits, queries, **kw):
    if has_credentials():
        yield from fetch_oauth(subreddits, queries, **{k: v for k, v in kw.items() if k in ("limit", "period")})
    else:
        yield from fetch_anonymous(subreddits, queries, **kw)
