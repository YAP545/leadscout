"""Intent classifier: genuine learner interest vs. teacher ads, notices and passing mentions.

Default backend is a transparent weighted-lexicon model (no downloads, no API, fully explainable:
every decision lists the cues that fired). An optional local-LLM backend (Ollama, free) can
re-check borderline cases; see `ollama_second_opinion`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import config as C


@dataclass
class Classification:
    label: str                 # seeker / possible_seeker / provider_or_ad / irrelevant
    confidence: float
    reason: str
    course: str = ""
    location: str = ""
    readiness: float = 0.0
    online: bool = False
    seeker_hits: list = field(default_factory=list)
    provider_hits: list = field(default_factory=list)
    has_strong_cue: bool = False
    kept_strong_cue: bool = False
    is_possible_teacher: bool = False
    is_content_request: bool = False
    is_offline_only: bool = False
    reject_reason: str = ""


FEES_QUESTION_PATTERN = re.compile(
    r"\b(what('?s| is| are) (the )?fees?|fees? kya hai|fees? kitn[ie]|how much)\b|fees?\?",
    re.IGNORECASE
)

TEACHER_GUARD_PATTERN = re.compile(
    r"\b(my students and parents|my parents and students|my students|"
    r"my class(es)?|my school|my academy|my batch(es)?|our students|our class(es)?|"
    r"i teach|i('?m| am) a (dance )?teacher|as a (dance )?teacher|guru here|"
    r"my channel|subscribe to my)\b",
    re.IGNORECASE
)

CONTENT_REQUEST_PATTERN = re.compile(
    r"\b(make a video on|make a vdo|please make (a )?video|please upload|upload a video|"
    r"make a tutorial|video on how|can you make a video|next video)\b",
    re.IGNORECASE
)

GUARD_ENROLMENT_ASK_PATTERN = re.compile(
    r"\b(enrol+|join|admission|register|registration|do you offer|do you teach|do you take)\b",
    re.IGNORECASE
)

OFFLINE_PATTERN = re.compile(
    r"\b(offline|in[\s-]person|physical class(es)?|near me|at your studio|your cent(?:er|re)|come to class|"
    r"visit\s+(?:you|your|the\s+(?:studio|class|school|cent(?:er|re))))\b",
    re.IGNORECASE
)

ONLINE_PATTERN = re.compile(
    r"\b(online|zoom|virtual|remote|skype|google meet|video call|video class(es)?|from home)\b",
    re.IGNORECASE
)


def has_teacher_guard(text: str) -> bool:
    return bool(TEACHER_GUARD_PATTERN.search(text))


def is_strong_cue(cue: str, text: str) -> bool:
    if cue in ("fees", "fee structure"):
        words = text.split()
        return len(words) <= 15 or bool(FEES_QUESTION_PATTERN.search(text))
    return cue in C.STRONG_CUES


def find_cues(text: str, cues: list[str]) -> list[str]:
    hits = []
    for cue in cues:
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in cue.split()) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            hits.append(cue)
    return hits


def find_strong_cues(text: str) -> list[str]:
    if has_teacher_guard(text):
        return []
    strong = []
    for cue in list(C.STRONG_CUES) + ["fee structure"]:
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in cue.split()) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            if is_strong_cue(cue, text) and cue not in strong:
                strong.append(cue)
    return strong


def has_strong_cue(text: str) -> bool:
    return bool(find_strong_cues(text))


def _clamp(x, lo=0.05, hi=0.95):
    return max(lo, min(hi, x))


def detect_course(text: str, context: str = ""):
    """Returns (course, inferred_from_context_only)."""
    t = text.lower()
    for name, rx in C.COURSES.items():
        if re.search(rx, t):
            return name, False
    if re.search(C.GENERIC_COURSE[1], t):
        return C.GENERIC_COURSE[0], False
    ctx = (context or "").lower()
    for name, rx in C.COURSES.items():
        if re.search(rx, ctx):
            return name, True
    if re.search(C.GENERIC_COURSE[1], ctx):
        return C.GENERIC_COURSE[0], True
    return "", False


def detect_location(text: str) -> str:
    for label, rx in C.LOCATIONS:
        flags = re.IGNORECASE
        if re.search(rx, text, flags):
            return label
    return ""


def _hits(signals, text):
    out, total = [], 0.0
    for rx, w, name in signals:
        if re.search(rx, text, re.IGNORECASE):
            out.append(name)
            total += w
    return out, total


def classify(text: str, context: str = "") -> Classification:
    has_prov = bool(TEACHER_GUARD_PATTERN.search(text))
    has_content_req = bool(CONTENT_REQUEST_PATTERN.search(text))
    has_enrol_ask = bool(GUARD_ENROLMENT_ASK_PATTERN.search(text))

    # Rejection rule: Provider cue OR content-request cue and NO explicit enrolment ask
    if (has_prov or has_content_req) and not has_enrol_ask:
        return Classification(
            label="irrelevant",
            confidence=0.9,
            reason="Provider or content request without enrolment ask",
            reject_reason="provider_or_content_request",
            is_possible_teacher=has_prov,
            is_content_request=has_content_req,
        )

    course, from_ctx = detect_course(text, context)
    is_teacher = has_prov
    strong_hits = find_strong_cues(text)
    has_strong = bool(strong_hits)
    intent_hits = find_cues(text, C.LEARNER_INTENT_CUES)

    if not course and not has_strong:
        return Classification("irrelevant", 0.9, "No Indian classical dance course mentioned",
                              is_possible_teacher=is_teacher,
                              is_content_request=has_content_req)

    if not course and has_strong:
        course = C.GENERIC_COURSE[0]

    s_hits, seeker = _hits(C.SEEKER_SIGNALS, text)
    p_hits, provider = _hits(C.PROVIDER_SIGNALS, text)
    if "?" in text:
        seeker += 0.5
        s_hits.append("asks a question")

    for cue in intent_hits:
        if cue not in s_hits:
            s_hits.append(cue)
            seeker += 2.0 if cue in strong_hits else 1.5

    readiness = min(1.0, sum(w for rx, w in C.READINESS_SIGNALS if re.search(rx, text, re.IGNORECASE)))
    if has_strong and readiness < 0.25:
        readiness = max(readiness, 0.3)

    has_offline = bool(OFFLINE_PATTERN.search(text))
    has_online = bool(ONLINE_PATTERN.search(text))
    is_offline_only = has_offline and not has_online
    online = False if is_offline_only else has_online

    common = dict(course=course, location=detect_location(text), readiness=readiness,
                  online=online, seeker_hits=s_hits, provider_hits=p_hits,
                  has_strong_cue=has_strong, is_possible_teacher=is_teacher,
                  is_content_request=has_content_req, is_offline_only=is_offline_only)
    ctx_note = " (course inferred from community context)" if from_ctx else ""

    if provider >= 2 and provider > seeker:
        return Classification("provider_or_ad", _clamp(0.5 + 0.1 * (provider - seeker)),
                              "Looks like a teacher/provider/institutional post: " + ", ".join(p_hits) + ctx_note, **common)
    if seeker >= 2 and seeker > provider:
        min_conf = 0.6 if has_strong else 0.55
        return Classification("seeker", _clamp(0.5 + 0.08 * (seeker - provider), min_conf, 0.95),
                              "Learner intent cues: " + ", ".join(s_hits) + ctx_note,
                              kept_strong_cue=has_strong, **common)
    if seeker >= 1 and seeker > provider:
        return Classification("possible_seeker", _clamp(0.35 + 0.05 * seeker, 0.35, 0.5),
                              "Weak learner-intent cues: " + ", ".join(s_hits) + ctx_note,
                              kept_strong_cue=has_strong, **common)

    if has_strong:
        return Classification("seeker", 0.65,
                              "Kept due to strong learner intent: " + ", ".join(strong_hits) + ctx_note,
                              kept_strong_cue=True, **common)

    why = "Mentions the topic but no clear learner intent"
    if p_hits:
        why += f"; provider cues present: {', '.join(p_hits)}"
    return Classification("irrelevant", 0.6, why + ctx_note, **common)


def ollama_second_opinion(text: str, model: str = "llama3.2", host: str = "http://localhost:11434"):
    """OPTIONAL, UNTESTED in this repo's CI: ask a local Ollama model for a yes/no on borderline posts.
    Returns True/False, or None if Ollama is not running."""
    import requests
    prompt = ("Does the author of this post want to find/enrol in an online Indian classical dance class "
              "(as a learner, or for a family member)? Answer with JSON {\"seeker\": true|false}.\n\n" + text[:1500])
    try:
        r = requests.post(f"{host}/api/generate", json={"model": model, "prompt": prompt,
                          "stream": False, "format": "json"}, timeout=60)
        return bool(json.loads(r.json()["response"]).get("seeker"))
    except Exception:
        return None
