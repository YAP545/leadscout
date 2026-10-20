# LeadScout

[Repository](https://github.com/YAP545/leadscout)

Finds **public discussions** where people appear to be looking for online Indian classical dance classes
(Bharatanatyam, Kathak, Kuchipudi, Odissi and more), filters genuine learner interest from teacher ads and
passing mentions, ranks them Hot / Warm / Cold, and exports a clean CSV with a small search UI.

> **Every row is a research opportunity, not a verified customer.** The tool stores a public link, date,
> platform and a reason, never usernames. Emails, phone numbers and handles are redacted before saving.
> It never contacts anyone. Review each link by hand and follow each platform's rules for how you engage.

Python 3.10+, open-source libraries only, no paid APIs.

## Setup

```bash
git clone https://github.com/YAP545/leadscout.git && cd leadscout
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

## Use

```bash
# 1) From manually gathered public posts (CSV: url,platform,title,text,posted_at,source_query,context)
python -m leadscout run --csv data/sample_real_sources.csv

# 2) Live public Reddit search (polite: 2.5s delay, identified User-Agent, no author data)
export LEADSCOUT_CONTACT="you@example.com"
python -m leadscout run --reddit --subreddits ClassicalIndiandance --target-location USA "Pune, India"

# 3) RSS/Atom feeds (forums, blog comment feeds, your own Google Alerts feeds)
python -m leadscout run --rss https://example.org/feed.xml

# 4) YouTube comment search (requires YouTube Data API v3 key)
# Windows (cmd):
set YOUTUBE_API_KEY=YOUR_KEY_HERE
# Windows (PowerShell):
# $env:YOUTUBE_API_KEY="YOUR_KEY_HERE"
# Linux/macOS:
# export YOUTUBE_API_KEY="YOUR_KEY_HERE"

python -m leadscout run --youtube --max-age-days 30

# Search interface
streamlit run app.py
```

Outputs: `output/leads.csv` (Hot/Warm/Cold), `output/rejected_audit.csv` (what was filtered out and why),
`output/review_sheet.csv` (manual review sheet), `data/leads.db` (SQLite; re-runs upsert, dedupe against stored rows, and purge posts older than `--max-age-days`, default 90).

CSV columns: `tier, score, confidence, has_strong_cue, course, location, online_interest, readiness, platform, posted_at,
date_status, date_source, url, original_url, title, snippet, reason, source_query, collected_at, review_status, review_note, notes, id`.

## How classification works

LeadScout uses a transparent, rule-based classifier (no paid API, no black box):
- Learner-intent cues (e.g. "want to learn", "enroll", "how to join", "what are the fees")
- Strong cues raise the score; a recent post date is required for Hot
- Provider/teacher guard: comments from teachers ("my students", "my class") are capped at Warm
- Content-request filter: generic requests for videos or tutorials without an enrollment ask are filtered out
- Every lead stores the cues that triggered it in the `reason` column, so each decision can be audited

Why rules and not a language model: results are explainable and repeatable, it runs offline
and free, and a person reviews every lead by hand. A local open-source model could be added
later as a second opinion (see "Future work").

## Scoring and Tiers

1. **Score** (`scoring.py`): `0.40 interest + 0.25 readiness + 0.20 recency + 0.15 location`
   (weights in `config.py`). Readiness = budget/fees/timings/demo/enrol cues. Recency decays with a 21-day half-life.
   Strong cues add a +0.15 bonus when not blocked by provider cues.
2. **Tiers**: Hot needs a *known* post date within max-age-days (and readiness or a strong cue with confidence ≥ 0.6). Warm ≥ 0.40. Else Cold.
   Posts with **no date are capped at Warm** and flagged for manual verification.
3. **Dedup**: canonical URLs (tracking params, `www/old/np/m` stripped) plus 3-word-shingle Jaccard text similarity,
   so reposts and cross-posts collapse while different posts on one listing page stay separate.

## Review and accuracy

Leads should be verified by hand before outreach. The review status column in `output/leads.csv` can be edited with `relevant`, `false_positive`, `unsure`, or `pending`.

To generate a manual review sheet:
```bash
python -m leadscout export --review-sheet
```

To compute review metrics and output false positives summary:
```bash
python -m leadscout review-stats --csv output/leads.csv
```

### Accuracy benchmark results
*(To be populated after running manual reviews on sample batches)*
- Total reviewed: [placeholder]
- Precision: [placeholder]

## Limitations
- Reddit search needs an API login, so it is not used by default
- Posts without a date (some blog comments) are capped at Warm
- Mostly-English cues; Hindi support is partial ("fees kya hai" works)
- Leads are research opportunities, not verified customers

## Layout

```
leadscout/      config, classifier, scoring, dedup, privacy, pipeline, store, cli, collectors/
app.py          Streamlit UI (course / location / keywords / tier / confidence filters, CSV download)
tests/          pytest suite (synthetic fixtures, clearly labelled)
data/           sample_real_sources.csv
```

## Publish to GitHub

```bash
git init && git add . && git commit -m "LeadScout prototype"
gh repo create leadscout --public --source=. --push     # or create it on github.com and `git remote add origin ...; git push -u origin main`
```
