from __future__ import annotations
import html, re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
import feedparser
from ..models import RawPost

def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()

def unwrap_google(url):
    p = urlparse(url or "")
    if p.netloc.endswith("google.com") and p.path == "/url":
        real = parse_qs(p.query).get("url")
        if real:
            return real[0]
    return url

def parse_feed(feed, platform="rss", query=""):
    for e in feed.entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        yield RawPost(url=unwrap_google(e.get("link", "")), platform=platform,
                      title=clean(e.get("title", "")),
                      text=clean(e.get("summary", "") or e.get("content", [{}])[0].get("value", "")),
                      posted_at=datetime(*t[:6], tzinfo=timezone.utc).isoformat() if t else None,
                      source_query=query, context=clean(feed.feed.get("title", "")),
                      date_source="feed")

def fetch(feed_urls):
    for url in feed_urls:
        yield from parse_feed(feedparser.parse(url), platform="rss", query=url)
