from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from . import config as C
from . import store
from .collectors import csv_import, reddit, rss, youtube
from .pipeline import export_csv, process


def _write_review_summary(stats: dict, summary_out: str) -> None:
    """Write the markdown summary file and print to stdout."""
    total_reviewed = stats["total_reviewed"]
    relevant = stats["relevant"]
    false_positive = stats["false_positive"]
    unsure = stats["unsure"]
    pending = stats["pending"]
    precision = stats["precision"]
    tier_precision = stats["tier_precision"]
    false_positives = stats["false_positives"]
    denom = relevant + false_positive

    print(f"Total reviewed: {total_reviewed}")
    print(f"Relevant: {relevant}")
    print(f"False positive: {false_positive}")
    print(f"Unsure: {unsure}")
    print(f"Pending: {pending}")
    print(f"Precision: {precision:.1%}" if denom > 0 else "Precision: 0.0%")
    for t in ("Hot", "Warm", "Cold"):
        p = tier_precision.get(t)
        print(f"  {t} precision: {p:.1%}" if p is not None else f"  {t} precision: n/a")

    out_p = Path(summary_out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    prec_str = f"{precision:.1%}" if denom > 0 else "0.0%"
    md = [
        "# Review Summary",
        "",
        f"- **Total reviewed**: {total_reviewed}",
        f"- **Relevant**: {relevant}",
        f"- **False positive**: {false_positive}",
        f"- **Unsure**: {unsure}",
        f"- **Pending**: {pending}",
        f"- **Precision**: {prec_str}",
    ]
    for t in ("Hot", "Warm", "Cold"):
        p = tier_precision.get(t)
        md.append(f"- **{t} precision**: {p:.1%}" if p is not None else f"- **{t} precision**: n/a")
    md += [
        "",
        "## False Positives",
        "",
        "| Tier | Snippet | Note |",
        "|---|---|---|",
    ]
    for t, snip, note in false_positives:
        clean_snip = snip.replace("|", "/").replace("\n", " ")
        clean_note = note.replace("|", "/")
        md.append(f"| {t} | {clean_snip} | {clean_note} |")
    md.append("")
    with open(out_p, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"Wrote summary to {summary_out}")


def handle_review_stats(csv_path: str | None, summary_out: str, db_path: str | None = None):
    """Compute review stats. If db_path given (and csv_path not provided), reads from DB."""
    if csv_path is None and db_path:
        con = store.connect(db_path)
        stats = store.review_stats(con)
        _write_review_summary(stats, summary_out)
        # Re-export leads.csv and review_sheet.csv from DB so they are never stale
        leads = store.load(con)
        leads.sort(key=lambda l: ({"Hot": 0, "Warm": 1, "Cold": 2}.get(l.tier, 3), -l.score))
        out_dir = Path(summary_out).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        export_csv(leads, str(out_dir / "leads.csv"))
        export_csv(leads, str(out_dir / "review_sheet.csv"))
        return 0

    # Legacy CSV mode
    p = Path(csv_path)
    if not p.exists():
        print(f"Error: {csv_path} does not exist.")
        return 1
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total_reviewed = 0
    relevant = 0
    false_positive = 0
    unsure = 0
    pending = 0
    tier_counts: Counter = Counter()
    tier_rel: Counter = Counter()
    tier_fp: Counter = Counter()
    false_positives = []

    for r in rows:
        st = (r.get("review_status") or "pending").strip().lower()
        tier = r.get("tier", "")
        tier_counts[tier] += 1
        if st == "relevant":
            relevant += 1
            total_reviewed += 1
            tier_rel[tier] += 1
        elif st == "false_positive":
            false_positive += 1
            total_reviewed += 1
            tier_fp[tier] += 1
            false_positives.append((tier, (r.get("snippet") or "")[:80], r.get("review_note") or r.get("notes") or ""))
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

    stats = {
        "total_reviewed": total_reviewed,
        "relevant": relevant,
        "false_positive": false_positive,
        "unsure": unsure,
        "pending": pending,
        "precision": precision,
        "tier_precision": tier_precision,
        "false_positives": false_positives,
    }
    _write_review_summary(stats, summary_out)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="leadscout", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="collect -> classify -> dedup -> score -> store -> export")
    r.add_argument("--csv", nargs="*", default=[], help="CSV files of manually gathered public posts")
    r.add_argument("--reddit", action="store_true", help="query public Reddit search (needs network)")
    r.add_argument("--subreddits", nargs="*", default=C.DEFAULT_SUBREDDITS)
    r.add_argument("--queries", nargs="*", default=C.DEFAULT_QUERIES)
    r.add_argument("--rss", nargs="*", default=[], help="RSS/Atom feed URLs")
    r.add_argument("--youtube", action="store_true", help="YouTube comments (needs YOUTUBE_API_KEY)")
    r.add_argument("--yt-queries", nargs="*", default=C.DEFAULT_YT_QUERIES)
    r.add_argument("--yt-videos", type=int, default=5, help="videos per query")
    r.add_argument("--yt-pages", type=int, default=3, help="comment pages per video (default 3, max 5)")
    r.add_argument("--db", default="data/leads.db")
    r.add_argument("--out", default="output/leads.csv")
    r.add_argument("--max-age-days", type=int, default=C.DEFAULT_MAX_AGE_DAYS)
    r.add_argument("--target-location", nargs="*", default=[], help="e.g. USA 'Pune, India'")
    r.add_argument("--review-sheet", action="store_true", help="write output/review_sheet.csv")

    e = sub.add_parser("export", help="re-export the stored leads to CSV")
    e.add_argument("--db", default="data/leads.db")
    e.add_argument("--out", default="output/leads.csv")
    e.add_argument("--review-sheet", action="store_true", help="write output/review_sheet.csv")

    s = sub.add_parser("review-stats", help="summarise manual review annotations")
    s.add_argument("--csv", default=None, help="path to reviewed leads CSV (omit to read from DB)")
    s.add_argument("--db", default="data/leads.db", help="database path (used when --csv not given)")
    s.add_argument("--out", default="output/review_summary.md", help="summary markdown path")

    er = sub.add_parser("export-reviewed", help="export all leads with review_status/review_note from DB")
    er.add_argument("--db", default="data/leads.db")
    er.add_argument("--out", default="output/reviewed_results.csv")

    a = ap.parse_args(argv)

    if a.cmd == "review-stats":
        return handle_review_stats(a.csv, a.out, db_path=a.db)

    if a.cmd == "export-reviewed":
        con = store.connect(a.db)
        leads = store.load(con)
        leads.sort(key=lambda l: ({"Hot": 0, "Warm": 1, "Cold": 2}.get(l.tier, 3), -l.score))
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        export_csv(leads, a.out)
        print(f"Exported {len(leads)} rows (with review status) to {a.out}")
        return 0

    con = store.connect(a.db)
    if a.cmd == "export":
        leads = store.load(con)
        export_csv(leads, a.out)
        print(f"Exported {len(leads)} rows to {a.out}")
        if a.review_sheet:
            sheet = str(Path(a.out).with_name("review_sheet.csv"))
            export_csv(leads, sheet)
            print(f"Exported review sheet to {sheet}")
        return 0

    raw = []
    for path in a.csv:
        raw += list(csv_import.fetch(path))
    if a.reddit:
        try:
            raw += list(reddit.fetch(a.subreddits, a.queries))
        except Exception as exc:
            print(f"[reddit] {exc}")
            if not (raw or a.rss):
                return 2
    if a.youtube:
        try:
            pages = min(max(1, a.yt_pages), 5)
            raw += list(youtube.fetch(a.yt_queries, a.yt_videos, max_pages=pages))
        except Exception as exc:
            print(f"[youtube] {exc}")
    if a.rss:
        raw += list(rss.fetch(a.rss))
    if not raw:
        print("No posts collected from any source. Nothing to do.")
        return 2

    purged = store.purge_outdated(con, a.max_age_days)
    existing = store.load(con)
    leads, rejected, stats = process(raw, max_age_days=a.max_age_days,
                                     targets=a.target_location, existing=existing)
    store.upsert(con, leads)
    # Reload from DB so review_status/review_note are never stale in exported CSVs
    all_leads = store.load(con)
    all_leads.sort(key=lambda l: ({"Hot": 0, "Warm": 1, "Cold": 2}.get(l.tier, 3), -l.score))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    export_csv(all_leads, a.out)
    audit = str(Path(a.out).with_name("rejected_audit.csv"))
    export_csv(rejected, audit)
    # Always write review_sheet from DB so it stays fresh
    sheet = str(Path(a.out).with_name("review_sheet.csv"))
    export_csv(all_leads, sheet)
    if a.review_sheet:
        print(f"Wrote review sheet to {sheet}")

    print(f"Collected {stats['collected']} | purged outdated from DB: {purged}")
    print(f"Rejected: provider/ad={stats['provider_or_ad']}, irrelevant={stats['irrelevant']}, outdated={stats['outdated']}")
    print(f"Duplicates dropped: {stats['duplicates_dropped']}")
    print(f"New leads: Hot={stats['Hot']} Warm={stats['Warm']} Cold={stats['Cold']}")
    print(f"Wrote {a.out} ({len(all_leads)} rows) and {audit} ({len(rejected)} rows)")
    return 0
