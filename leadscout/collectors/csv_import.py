"""Import manually gathered public posts. Columns: url, platform, title, text, posted_at, source_query, context."""
import csv

from ..models import RawPost


def fetch(path):
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            posted = (r.get("posted_at") or "").strip() or None
            ds = (r.get("date_source") or "").strip()
            if not ds:
                ds = "manual" if posted else "unknown"
            if not posted:
                ds = "unknown"
            yield RawPost(url=r.get("url", ""), platform=r.get("platform", "web"),
                          title=r.get("title", ""), text=r.get("text", ""),
                          posted_at=posted, source_query=r.get("source_query", ""),
                          context=r.get("context", ""), date_source=ds)
