from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class RawPost:
    """A public post/comment/page as collected. No author or handle is stored, by design."""
    url: str
    platform: str
    title: str = ""
    text: str = ""
    posted_at: str | None = None   # ISO-8601 or None when the source gives no date
    source_query: str = ""
    context: str = ""              # e.g. "r/ClassicalIndiandance"; used only to infer course
    date_source: str = "unknown"   # "api", "feed", "page", "manual", "unknown"
    original_url: str = ""


EXPORT_COLUMNS = [
    "tier", "score", "confidence", "has_strong_cue", "course", "location", "online_interest", "readiness",
    "platform", "posted_at", "date_status", "date_source", "url", "original_url", "title", "snippet", "reason",
    "source_query", "collected_at", "review_status", "review_note", "notes", "id",
]
REJECTED_EXPORT_COLUMNS = ["reject_reason"] + EXPORT_COLUMNS

REVIEW_SHEET_COLUMNS = [
    "tier", "url", "original_url", "posted_at", "date_source", "snippet", "reason", "review_status", "review_note",
]


@dataclass
class Lead:
    id: str = ""
    tier: str = ""               # Hot / Warm / Cold (or Rejected in the audit file)
    score: float = 0.0
    confidence: float = 0.0
    label: str = ""              # seeker / possible_seeker / provider_or_ad / irrelevant
    course: str = ""
    location: str = ""
    online_interest: bool = False
    readiness: float = 0.0
    platform: str = ""
    posted_at: str = ""
    date_status: str = "unknown"  # verified / unverified / unknown
    date_source: str = "unknown"  # api / feed / page / manual / unknown
    url: str = ""
    original_url: str = ""
    title: str = ""
    snippet: str = ""
    reason: str = ""
    source_query: str = ""
    collected_at: str = ""
    review_status: str = "pending"
    review_note: str = ""
    notes: str = ""
    reject_reason: str = ""
    has_strong_cue: bool = False
    is_possible_teacher: bool = False
    is_offline_only: bool = False

    def as_row(self) -> dict:
        return asdict(self)
