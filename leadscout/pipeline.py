from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import config as C
from .classifier import classify
from .dedup import dedup, fingerprint, normalise_url
from .models import EXPORT_COLUMNS, REJECTED_EXPORT_COLUMNS, REVIEW_SHEET_COLUMNS, Lead
from .privacy import redact
from .scoring import score_lead

TIER_ORDER = {"Hot": 0, "Warm": 1, "Cold": 2, "Rejected": 3}


def parse_dt(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def process(raw_posts, now=None, max_age_days=C.DEFAULT_MAX_AGE_DAYS, targets=(), existing=()):
    """collect -> redact -> classify -> drop non-seekers/outdated -> dedup -> score.
    Returns (leads, rejected, stats)."""
    now = now or datetime.now(timezone.utc)
    stats, accepted, rejected = Counter(), [], []
    posted_by_id = {}
    for p in raw_posts:
        stats["collected"] += 1
        title, text = redact(p.title), redact(p.text)
        body = f"{title}. {text}" if text else title
        c = classify(body, p.context)
        posted = parse_dt(p.posted_at)
        if posted and posted > now + timedelta(days=1):
            posted = None  # implausible future date: treat as unknown

        raw_ds = getattr(p, "date_source", "unknown")
        if posted:
            date_source = raw_ds if raw_ds != "unknown" else "manual"
            date_status = "verified" if date_source in ("api", "feed") else "unverified"
        else:
            date_source = "unknown"
            date_status = "unknown"

        orig_url = getattr(p, "original_url", "") or p.url
        norm_url = normalise_url(p.url)

        notes_parts = []
        if c.is_possible_teacher:
            notes_parts.append("possible_teacher")
        if c.is_content_request:
            notes_parts.append("content_request")
        if c.is_offline_only:
            notes_parts.append("offline_only")
        if c.has_strong_cue and c.label not in ("provider_or_ad", "irrelevant") and not c.is_possible_teacher:
            notes_parts.append("kept_strong_cue")
        notes = " ".join(notes_parts)

        lead = Lead(
            id=fingerprint(p.url, body), label=c.label, confidence=round(c.confidence, 2),
            course=c.course, location=c.location, online_interest=c.online,
            readiness=round(c.readiness, 2), platform=p.platform,
            posted_at=posted.isoformat() if posted else "",
            date_status=date_status, date_source=date_source,
            url=norm_url, original_url=orig_url, title=title,
            snippet=body[:400], reason=c.reason, source_query=p.source_query,
            collected_at=now.isoformat(timespec="seconds"),
            review_status="pending", review_note="",
            notes=notes,
            reject_reason=c.reject_reason,
            has_strong_cue=c.has_strong_cue,
            is_possible_teacher=c.is_possible_teacher,
            is_offline_only=c.is_offline_only,
        )
        posted_by_id[lead.id] = posted
        if c.label in ("provider_or_ad", "irrelevant"):
            lead.tier = "Rejected"
            lead.reject_reason = c.reject_reason or c.label
            stats[lead.reject_reason] += 1
            rejected.append(lead)
        elif posted and (now - posted).days > max_age_days:
            lead.tier, lead.reason = "Rejected", f"Outdated (> {max_age_days} days). " + lead.reason
            lead.reject_reason = "outdated"
            stats["outdated"] += 1
            rejected.append(lead)
        else:
            accepted.append(lead)

    kept, dropped = dedup(accepted, against=existing)
    stats["duplicates_dropped"] = dropped
    for lead in kept:
        score_lead(lead, posted_by_id[lead.id], now, targets, max_age_days=max_age_days)
        stats[lead.tier] += 1
    kept.sort(key=lambda l: (TIER_ORDER.get(l.tier, 4), -l.score))
    return kept, rejected, stats


def export_csv(leads, path, fieldnames=None):
    if fieldnames is None:
        if str(path).endswith("rejected_audit.csv"):
            fieldnames = REJECTED_EXPORT_COLUMNS
        elif str(path).endswith("review_sheet.csv"):
            fieldnames = REVIEW_SHEET_COLUMNS
        else:
            fieldnames = EXPORT_COLUMNS
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for l in leads:
            w.writerow(l.as_row())
