"""SQLite persistence (stdlib). Re-runs upsert by fingerprint and purge outdated rows."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Lead

_COLS = [
    "id", "tier", "score", "confidence", "label", "course", "location", "online_interest",
    "readiness", "platform", "posted_at", "date_status", "date_source", "url", "original_url",
    "title", "snippet", "reason", "source_query", "collected_at", "review_status", "review_note",
    "notes", "reject_reason", "has_strong_cue", "is_possible_teacher", "is_offline_only"
]

_BOOL_COLS = {"online_interest", "has_strong_cue", "is_possible_teacher", "is_offline_only"}
_FLOAT_COLS = {"score", "confidence", "readiness"}
_KEEP_ON_UPDATE = {"id", "collected_at", "review_status", "review_note", "notes"}


def migrate(con):
    cursor = con.execute("PRAGMA table_info(leads)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if not existing_cols:
        return
    for col in _COLS:
        if col not in existing_cols:
            col_type = "INTEGER" if col in _BOOL_COLS else ("REAL" if col in _FLOAT_COLS else "TEXT")
            con.execute(f"ALTER TABLE leads ADD COLUMN {col} {col_type}")
    con.commit()


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.execute(f"CREATE TABLE IF NOT EXISTS leads ({', '.join(c + ' ' + ('PRIMARY KEY' if c == 'id' else '') for c in _COLS)})")
    migrate(con)
    return con


def upsert(con, leads):
    migrate(con)
    sets = ", ".join(f"{c}=excluded.{c}" for c in _COLS if c not in _KEEP_ON_UPDATE)
    sql = (f"INSERT INTO leads ({', '.join(_COLS)}) VALUES ({', '.join('?' * len(_COLS))}) "
           f"ON CONFLICT(id) DO UPDATE SET {sets}")
    con.executemany(sql, [tuple(int(getattr(l, c)) if c in _BOOL_COLS else getattr(l, c) for c in _COLS) for l in leads])
    con.commit()


def purge_outdated(con, max_age_days, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=max_age_days)).isoformat()
    cur = con.execute("DELETE FROM leads WHERE posted_at != '' AND posted_at < ?", (cutoff,))
    con.commit()
    return cur.rowcount


def load(con):
    migrate(con)
    rows = con.execute(f"SELECT {', '.join(_COLS)} FROM leads").fetchall()
    out = []
    for r in rows:
        d = dict(zip(_COLS, r))
        for bc in _BOOL_COLS:
            d[bc] = bool(d.get(bc))
        for fc in _FLOAT_COLS:
            d[fc] = float(d.get(fc) or 0.0)
        for sc in _COLS:
            if sc not in _BOOL_COLS and sc not in _FLOAT_COLS:
                d[sc] = str(d.get(sc) if d.get(sc) is not None else "")
        out.append(Lead(**d))
    return out


def update_review(con, lead_id: str, status: str, note: str = "") -> None:
    """Persist a review decision without touching any other field."""
    con.execute(
        "UPDATE leads SET review_status=?, review_note=? WHERE id=?",
        (status, note, lead_id),
    )
    con.commit()


def review_stats(con):
    """Return a dict with review counts and precision, read from the database."""
    from collections import Counter
    leads = load(con)
    total_reviewed = 0
    relevant = 0
    false_positive = 0
    unsure = 0
    pending = 0
    tier_fp: Counter = Counter()
    tier_rel: Counter = Counter()
    false_positives = []
    for lead in leads:
        st = (lead.review_status or "pending").strip().lower()
        tier = lead.tier
        if st == "relevant":
            relevant += 1
            total_reviewed += 1
            tier_rel[tier] += 1
        elif st == "false_positive":
            false_positive += 1
            total_reviewed += 1
            tier_fp[tier] += 1
            false_positives.append((tier, lead.snippet[:80], lead.review_note))
        elif st == "unsure":
            unsure += 1
            total_reviewed += 1
        else:
            pending += 1
    denom = relevant + false_positive
    precision = (relevant / denom) if denom > 0 else 0.0
    tier_precision = {}
    for t in ("Hot", "Warm", "Cold"):
        d = tier_rel.get(t, 0) + tier_fp.get(t, 0)
        tier_precision[t] = (tier_rel.get(t, 0) / d) if d > 0 else None
    return {
        "total_reviewed": total_reviewed,
        "relevant": relevant,
        "false_positive": false_positive,
        "unsure": unsure,
        "pending": pending,
        "precision": precision,
        "tier_precision": tier_precision,
        "false_positives": false_positives,
    }
