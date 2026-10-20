from __future__ import annotations
import os, time
import requests
from ..models import RawPost

API = "https://www.googleapis.com/youtube/v3"

class YouTubeError(RuntimeError):
    pass

def _get(path, params):
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        raise YouTubeError("Set YOUTUBE_API_KEY (free key from Google Cloud Console, YouTube Data API v3).")
    r = requests.get(f"{API}/{path}", params={**params, "key": key}, timeout=20)
    if r.status_code == 403 and "commentsDisabled" in r.text:
        return None
    if r.status_code in (400, 403):
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = r.text[:200]
        raise YouTubeError(f"YouTube API error {r.status_code}: {msg}")
    r.raise_for_status()
    return r.json()

def parse_comments(payload, video_id, video_title, query=""):
    for item in payload.get("items", []):
        top = item.get("snippet", {}).get("topLevelComment", {})
        sn = top.get("snippet", {})
        text = sn.get("textOriginal") or sn.get("textDisplay") or ""
        if not text or not top.get("id"):
            continue
        yield RawPost(url=f"https://www.youtube.com/watch?v={video_id}&lc={top['id']}",
                      platform="youtube", title="YouTube comment", text=text,
                      posted_at=sn.get("publishedAt"),
                      source_query=f"{query} | video: {video_title}", context=video_title,
                      date_source="api")

def fetch(queries, videos_per_query=5, delay=0.5, max_pages=3):
    max_pages = min(max(1, int(max_pages)), 5)
    seen = set()
    for q in queries:
        found = _get("search", {"part": "snippet", "q": q, "type": "video",
                                "maxResults": videos_per_query, "order": "relevance"})
        if not found:
            continue
        for item in found.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            video_title = item.get("snippet", {}).get("title", "")
            page_token = None
            for _ in range(max_pages):
                params = {"part": "snippet", "videoId": vid, "maxResults": 100,
                          "order": "time", "textFormat": "plainText"}
                if page_token:
                    params["pageToken"] = page_token
                payload = _get("commentThreads", params)
                if not payload:
                    break
                yield from parse_comments(payload, vid, video_title, q)
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
                time.sleep(delay)
            time.sleep(delay)
