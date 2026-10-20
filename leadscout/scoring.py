from __future__ import annotations

import math
from datetime import datetime

from . import config as C


def recency_score(posted: datetime | None, now: datetime) -> float:
    if posted is None:
        return C.UNKNOWN_DATE_RECENCY
    age = max(0.0, (now - posted).total_seconds() / 86400)
    return math.exp(-math.log(2) * age / C.RECENCY_HALF_LIFE_DAYS)


def location_score(lead, targets) -> float:
    base = 0.4
    if lead.location:
        base = 0.8
        if targets and not any(t.lower() in lead.location.lower() for t in targets):
            base = 0.3
        elif targets:
            base = 1.0
    if lead.online_interest:
        base = min(1.0, base + 0.2)  # location matters less when they want online
    return base


def score_lead(lead, posted: datetime | None, now: datetime, targets=(), max_age_days: int = C.DEFAULT_MAX_AGE_DAYS) -> None:
    """Fills lead.score and lead.tier in place. Only seekers/possible seekers get a tier."""
    W = C.WEIGHTS
    rec = recency_score(posted, now)
    s = (W["interest"] * lead.confidence + W["readiness"] * min(1.0, lead.readiness)
         + W["recency"] * rec + W["location"] * location_score(lead, targets))

    is_teacher = getattr(lead, "is_possible_teacher", False)
    is_content_request = getattr(lead, "is_content_request", False)
    is_offline_only = getattr(lead, "is_offline_only", False)

    apply_bonus = lead.has_strong_cue and lead.label not in ("provider_or_ad", "irrelevant") and not is_teacher
    if apply_bonus:
        s = min(1.0, s + 0.15)
        lead.has_strong_cue = True
    else:
        lead.has_strong_cue = False

    lead.score = round(s, 3)

    is_dated = lead.date_status in ("verified", "unverified", "known")
    within_max_age = (posted is not None and (now - posted).total_seconds() / 86400 <= max_age_days)
    hot_standard = (lead.label == "seeker" and s >= C.HOT_MIN_SCORE and is_dated
                    and lead.readiness >= C.HOT_MIN_READINESS)
    hot_strong = (is_dated and within_max_age and lead.has_strong_cue and lead.confidence >= 0.6)
    
    cap_warm = is_teacher or is_content_request or is_offline_only
    hot = (hot_standard or hot_strong) and not cap_warm

    if hot and is_dated:
        lead.tier = "Hot"
    elif s >= C.WARM_MIN_SCORE or cap_warm:
        lead.tier = "Warm"
    else:
        lead.tier = "Cold"

    if is_teacher and "possible_teacher" not in lead.notes:
        lead.notes = (lead.notes + " " if lead.notes else "") + "possible_teacher"
    if is_content_request and "content_request" not in lead.notes:
        lead.notes = (lead.notes + " " if lead.notes else "") + "content_request"
    if is_offline_only and "offline_only" not in lead.notes:
        lead.notes = (lead.notes + " " if lead.notes else "") + "offline_only"

    if lead.date_status == "unknown":
        if "verify_date_manually" not in lead.notes:
            lead.notes = (lead.notes + " " if lead.notes else "") + "verify_date_manually"
        if "No post date" not in lead.notes:
            lead.notes = (lead.notes + " " if lead.notes else "") + "No post date available: capped at Warm; verify recency manually."
