"""Unit tests. Texts below are SYNTHETIC fixtures written for testing; they are not sample results."""
import csv
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from leadscout import store
from leadscout.classifier import classify
from leadscout.cli import handle_review_stats
from leadscout.collectors import csv_import
from leadscout.collectors.reddit import parse_listing
from leadscout.dedup import canonical_url, normalise_url
from leadscout.models import Lead, RawPost
from leadscout.pipeline import export_csv, process
from leadscout.privacy import redact

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


def post(title, text="", days_ago=2, url="https://example.org/a", ctx="", date_source="api"):
    return RawPost(url=url, platform="test", title=title, text=text,
                   posted_at=iso(days_ago) if days_ago is not None else None, context=ctx,
                   date_source=date_source if days_ago is not None else "unknown")


def test_seeker_detected():
    c = classify("Can anyone suggest an online Bharatanatyam class for adults in Pune? Budget is flexible.")
    assert c.label == "seeker" and c.course == "Bharatanatyam" and c.location == "Pune, India" and c.online


def test_teacher_ad_rejected():
    c = classify("We offer online Bharatanatyam classes. Book a free demo class. 10 years of teaching experience.")
    assert c.label in ("provider_or_ad", "irrelevant")


def test_teacher_pitch_not_a_seeker():
    c = classify("If anyone is looking for a personal Kathak teacher online, please message me.")
    assert c.label == "provider_or_ad"


def test_irrelevant_mention():
    assert classify("Watched a Bharatanatyam arangetram yesterday, wonderful costumes").label == "irrelevant"


def test_no_course_is_irrelevant():
    assert classify("Looking for a good yoga class online?").label == "irrelevant"


def test_course_from_context_only():
    c = classify("Are there any online teachers you recommend?", ctx := "r/ClassicalIndiandance Indian classical dance")
    assert c.label == "seeker" and "context" in c.reason


def test_kathak_not_confused_with_kathakali():
    assert classify("want to learn kathakali online?").course == "Kathakali"


def test_us_location_case_sensitive():
    assert classify("looking for kathak classes in US, online?").location == "USA"
    assert classify("let us find kathak classes, looking for online?").location != "USA"


def test_redaction():
    t = redact("mail me at a.b@x.com or +91 98765 43210, thanks u/someone_1")
    assert "@x.com" not in t and "98765" not in t and "someone_1" not in t


def test_hot_requires_known_date_and_readiness():
    txt = "Looking for an online Bharatanatyam teacher, can anyone suggest? Need weekend timings, fees reasonable, want to join soon."
    leads, _, _ = process([post("Need teacher", txt, days_ago=1)], now=NOW)
    assert leads[0].tier == "Hot"
    leads, _, _ = process([post("Need teacher", txt, days_ago=None)], now=NOW)
    assert leads[0].tier != "Hot" and "No post date" in leads[0].notes


def test_outdated_dropped():
    txt = "Looking for an online Kathak teacher, can anyone suggest?"
    leads, rejected, stats = process([post("t", txt, days_ago=200)], now=NOW, max_age_days=90)
    assert not leads and stats["outdated"] == 1 and "Outdated" in rejected[0].reason


def test_dedup_same_post_two_urls_and_tracking_params():
    txt = "Looking for an online Kathak teacher for my daughter, can anyone suggest good classes in Dubai?"
    a = post("Kathak teacher", txt, url="https://www.reddit.com/r/x/comments/1/abc/?utm_source=share")
    b = post("Kathak teacher", txt, url="https://old.reddit.com/r/x/comments/1/abc")
    c = post("Kathak teacher", txt, url="https://other.site/crosspost")
    leads, _, stats = process([a, b, c], now=NOW)
    assert len(leads) == 1 and stats["duplicates_dropped"] == 2


def test_different_posts_same_listing_url_not_merged():
    u = "https://example.org/listing"
    a = post("Kathak in US", "Can anyone suggest online kathak classes in US time zone?", url=u)
    b = post("Odissi Pune", "Where can I learn odissi in Pune? Any teacher recommendations?", url=u)
    leads, _, _ = process([a, b], now=NOW)
    assert len(leads) == 2


def test_canonical_url():
    assert canonical_url("https://WWW.Reddit.com/r/a/b/?utm_x=1#c") == "reddit.com/r/a/b"


def test_reddit_parser_fixture():
    payload = {"data": {"children": [
        {"data": {"permalink": "/r/x/comments/1/t/", "title": "Online kathak?", "selftext": "pls suggest",
                  "created_utc": 1760000000, "subreddit": "x", "author": "someone"}},
        {"data": {"permalink": "/r/x/comments/2/t/", "title": "nsfw", "over_18": True}}]}}
    posts = list(parse_listing(payload, "q"))
    assert len(posts) == 1 and posts[0].url.endswith("/r/x/comments/1/t/") and posts[0].posted_at
    assert "someone" not in json.dumps(posts[0].__dict__)  # author never stored


def test_store_roundtrip_and_purge(tmp_path):
    txt = "Looking for an online Kathak teacher, can anyone suggest?"
    leads, _, _ = process([post("a", txt, days_ago=5, url="https://e.org/1")], now=NOW)
    con = store.connect(tmp_path / "t.db")
    store.upsert(con, leads)
    store.upsert(con, leads)  # idempotent
    assert len(store.load(con)) == 1
    assert store.purge_outdated(con, 3, now=NOW) == 1 and not store.load(con)


def test_export_columns(tmp_path):
    txt = "Looking for an online Kathak teacher, can anyone suggest?"
    leads, _, _ = process([post("a", txt)], now=NOW)
    out = tmp_path / "o.csv"
    export_csv(leads, out)
    row = next(csv.DictReader(open(out)))
    for col in ("tier", "url", "posted_at", "platform", "reason", "confidence", "has_strong_cue", "date_source", "original_url"):
        assert row[col] != "" or col == "posted_at"


def test_strong_cue_dated_is_hot():
    txt = "Mam I would like to enroll in your dance class mam"
    leads, _, _ = process([post("Enroll inquiry", txt, days_ago=5)], now=NOW)
    assert len(leads) == 1
    assert leads[0].tier == "Hot"
    assert leads[0].has_strong_cue is True


def test_strong_cue_undated_is_warm():
    txt = "Mam I would like to enroll in your dance class mam"
    leads, _, _ = process([post("Enroll inquiry", txt, days_ago=None)], now=NOW)
    assert len(leads) == 1
    assert leads[0].tier == "Warm"


def test_beautiful_dance_still_rejected():
    leads, rejected, _ = process([post("Compliment", "beautiful dance", days_ago=2)], now=NOW)
    assert len(leads) == 0
    assert len(rejected) == 1
    assert rejected[0].tier == "Rejected"


def test_do_you_offer_classes_not_rejected():
    leads, rejected, _ = process([post("Question", "Do you offer classes?", days_ago=2)], now=NOW)
    assert len(leads) == 1
    assert len(rejected) == 0


def test_rejected_audit_has_reject_reason(tmp_path):
    leads, rejected, _ = process([post("Compliment", "beautiful dance", days_ago=2)], now=NOW)
    audit = tmp_path / "rejected_audit.csv"
    export_csv(rejected, audit)
    row = next(csv.DictReader(open(audit)))
    assert "reject_reason" in row
    assert row["reject_reason"] == "irrelevant"


def test_fees_short_question_is_hot():
    txt = "Mam what are the fees"
    leads, _, _ = process([post("Fees inquiry", txt, days_ago=5)], now=NOW)
    assert len(leads) == 1
    assert leads[0].tier == "Hot"
    assert leads[0].has_strong_cue is True


def test_fees_hindi_question_is_hot():
    txt = "Mam apni fees kya hai"
    leads, _, _ = process([post("Fees inquiry", txt, days_ago=3)], now=NOW)
    assert len(leads) == 1
    assert leads[0].tier == "Hot"
    assert leads[0].has_strong_cue is True


def test_teacher_guard_long_comment_rejected():
    txt = (
        "Mam plzz make a vdo on ..coming to class in proper time, proper uniform, bindi on forehead , "
        "and timely fees payment and importance of uniform and dupatta... These are my problems im facing "
        "with my parents and students. .so plzz do needful mam ..this vdo also I shared to students"
    )
    leads, rejected, _ = process([post("YouTube comment", txt, days_ago=15, ctx="learn bharatanatyam online")], now=NOW)
    assert len(leads) == 0
    assert len(rejected) == 1
    assert rejected[0].reject_reason == "provider_or_content_request"


def test_offline_only_request():
    txt = "Mam how to join offline"
    leads, _, _ = process([post("Question", txt, days_ago=2, ctx="ClassicalIndiandance")], now=NOW)
    assert len(leads) == 1
    assert leads[0].tier != "Hot"
    assert leads[0].tier == "Warm"
    assert "offline_only" in leads[0].notes


def test_online_with_strong_cue_is_hot():
    txt = "Is there an online class? I would like to enroll."
    leads, _, _ = process([post("Enroll inquiry", txt, days_ago=2, ctx="ClassicalIndiandance")], now=NOW)
    assert len(leads) == 1
    assert leads[0].tier == "Hot"
    assert leads[0].has_strong_cue is True


def test_content_request_with_teacher_and_fees():
    txt = "Mam please make a video on uniform and fees for my students"
    leads, rejected, _ = process([post("Video request", txt, days_ago=2, ctx="ClassicalIndiandance")], now=NOW)
    if leads:
        assert leads[0].tier != "Hot"
        assert leads[0].tier == "Warm"
    else:
        assert len(rejected) == 1
        assert rejected[0].tier == "Rejected"


def test_persistence_roundtrip_all_fields(tmp_path):
    db_file = tmp_path / "test_roundtrip.db"
    con = store.connect(db_file)
    lead = Lead(
        id="roundtrip123", tier="Hot", score=0.85, confidence=0.9, label="seeker",
        course="Bharatanatyam", location="Pune, India", online_interest=True,
        readiness=0.75, platform="youtube", posted_at="2026-10-18T12:00:00+00:00",
        date_status="verified", date_source="api", url="https://www.reddit.com/r/a/b",
        original_url="https://reddit.birdcat.cafe/r/a/b", title="Title", snippet="Snippet text",
        reason="Reason text", source_query="query", collected_at="2026-10-20T12:00:00+00:00",
        review_status="relevant", review_note="Verified lead", notes="kept_strong_cue",
        reject_reason="", has_strong_cue=True, is_possible_teacher=False, is_offline_only=False
    )
    store.upsert(con, [lead])
    loaded = store.load(con)
    assert len(loaded) == 1
    l2 = loaded[0]
    for f, v in lead.as_row().items():
        assert getattr(l2, f) == v, f"Field {f} mismatch: {getattr(l2, f)} != {v}"

    out_csv = tmp_path / "leads.csv"
    export_csv(loaded, out_csv)
    row = next(csv.DictReader(open(out_csv, encoding="utf-8")))
    for col in ("tier", "score", "confidence", "has_strong_cue", "date_status", "date_source", "url", "original_url"):
        assert row[col] != "", f"Column {col} is blank"


def test_old_schema_migration(tmp_path):
    db_file = tmp_path / "old.db"
    con = sqlite3.connect(db_file)
    con.execute("CREATE TABLE leads (id TEXT PRIMARY KEY, tier TEXT, score REAL, title TEXT, snippet TEXT)")
    con.execute("INSERT INTO leads (id, tier, score, title, snippet) VALUES ('old1', 'Warm', 0.5, 'Old title', 'Old snippet')")
    con.commit()
    con.close()

    con2 = store.connect(db_file)
    loaded = store.load(con2)
    assert len(loaded) == 1
    assert loaded[0].id == "old1"
    assert loaded[0].tier == "Warm"
    assert loaded[0].score == 0.5
    assert loaded[0].title == "Old title"


def test_mirror_url_normalisation():
    url = "https://reddit.birdcat.cafe/r/ClassicalIndiandance/comments/abc123/classes/?utm_source=share"
    norm = normalise_url(url)
    assert norm == "https://www.reddit.com/r/ClassicalIndiandance/comments/abc123/classes"


def test_date_source_and_status():
    p_api = RawPost(url="https://example.org/1", platform="youtube", title="t", text="Mam I want to learn Bharatanatyam",
                    posted_at=iso(2), date_source="api")
    leads_api, _, _ = process([p_api], now=NOW)
    assert leads_api[0].date_source == "api"
    assert leads_api[0].date_status == "verified"

    p_man = RawPost(url="https://example.org/2", platform="csv", title="t", text="Mam I want to learn Bharatanatyam",
                    posted_at=iso(2), date_source="manual")
    leads_man, _, _ = process([p_man], now=NOW)
    assert leads_man[0].date_source == "manual"
    assert leads_man[0].date_status == "unverified"

    p_undated = RawPost(url="https://example.org/3", platform="csv", title="t", text="Mam I want to learn Bharatanatyam",
                        posted_at=None, date_source="unknown")
    leads_und, _, _ = process([p_undated], now=NOW)
    assert leads_und[0].date_source == "unknown"
    assert leads_und[0].date_status == "unknown"
    assert "verify_date_manually" in leads_und[0].notes


def test_review_stats(tmp_path):
    csv_path = tmp_path / "leads.csv"
    out_md = tmp_path / "summary.md"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tier", "review_status", "snippet", "notes"])
        w.writeheader()
        w.writerow({"tier": "Hot", "review_status": "relevant", "snippet": "Genuine learner looking for class", "notes": ""})
        w.writerow({"tier": "Hot", "review_status": "false_positive", "snippet": "Teacher selling classes", "notes": "possible_teacher"})
        w.writerow({"tier": "Warm", "review_status": "unsure", "snippet": "Vague question about dance", "notes": ""})
        w.writerow({"tier": "Cold", "review_status": "pending", "snippet": "Unreviewed post", "notes": ""})

    rc = handle_review_stats(str(csv_path), str(out_md))
    assert rc == 0
    assert out_md.exists()
    md_content = open(out_md, encoding="utf-8").read()
    assert "- **Total reviewed**: 3" in md_content
    assert "- **Relevant**: 1" in md_content
    assert "- **False positive**: 1" in md_content
    assert "- **Unsure**: 1" in md_content
    assert "- **Precision**: 50.0%" in md_content
    assert "Teacher selling classes" in md_content


def test_looking_for_dance_teacher_is_seeker():
    assert classify("Looking for a dance teacher for Bharatanatyam online, can anyone suggest?").label == "seeker"


def test_csv_import_date_source(tmp_path):
    p = tmp_path / "test_dates.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "posted_at", "date_source"])
        w.writeheader()
        w.writerow({"url": "u1", "posted_at": "2026-10-01", "date_source": ""})
        w.writerow({"url": "u2", "posted_at": "", "date_source": ""})
        w.writerow({"url": "u3", "posted_at": "2026-10-01", "date_source": "page"})
    posts = list(csv_import.fetch(str(p)))
    assert posts[0].date_source == "manual"
    assert posts[1].date_source == "unknown"
    assert posts[2].date_source == "page"


def test_guard_content_request_and_fees_alone_rejected():
    txt = "Mam plzz make a vdo on coming to class in proper time and timely fees payment for my students, Bharatanatyam"
    c = classify(txt)
    assert c.label == "irrelevant"
    assert c.reject_reason == "provider_or_content_request"
    leads, rejected, _ = process([post("YouTube comment", txt, days_ago=5)], now=NOW)
    assert len(leads) == 0
    assert len(rejected) == 1
    assert rejected[0].reject_reason == "provider_or_content_request"


def test_fees_with_bharatanatyam_context_stays_lead():
    txt = "Mam what are the fees"
    c = classify(txt, context="Bharatanatyam")
    assert c.label == "seeker"
    leads, rejected, _ = process([post("YouTube comment", txt, days_ago=5, ctx="Bharatanatyam")], now=NOW)
    assert len(leads) == 1
    assert len(rejected) == 0
    assert leads[0].tier in ("Hot", "Warm")


def test_is_there_any_online_classes_available_kathak():
    txt = "Is there any online classes available"
    c = classify(txt, context="Kathak")
    assert c.label == "seeker"
    assert "asks if classes exist" in c.seeker_hits
    leads, rejected, _ = process([post("YouTube comment", txt, days_ago=5, ctx="Kathak")], now=NOW)
    assert len(leads) == 1
    assert leads[0].tier in ("Warm", "Hot")


def test_widened_learner_cues():
    positives = [
        "How I can join the online bharatnatyam course",
        "Hi Im 25years I wanted to learn Bharatnatyam Is it possible to learn and perform",
        "Mam what's fee for online classes? I'm an absolute beginner.",
        "Online class available na mam",
        "Mam can I learn bharatanatyam",
        "I need to learn",
        "How can connect with you to join class",
        "Fees",
    ]
    for text in positives:
        c = classify(text, context="Bharatanatyam")
        assert c.label in ("seeker", "possible_seeker"), f"Expected seeker/possible_seeker for {text!r}, got {c.label}"

    negatives = [
        "I learn steps in my school only no need to join",
        "Beautiful performance, thank you so much",
        "Mam please make a video on adavu for my students",
    ]
    for text in negatives:
        c = classify(text, context="Bharatanatyam")
        assert c.label == "irrelevant", f"Expected irrelevant for {text!r}, got {c.label}"


def test_youtube_pagination(monkeypatch):
    from leadscout.collectors import youtube

    calls = []
    def fake_get(path, params):
        calls.append((path, params.copy()))
        if path == "search":
            return {"items": [{"id": {"videoId": "vid1"}, "snippet": {"title": "Dance video"}}]}
        if path == "commentThreads":
            pt = params.get("pageToken")
            if not pt:
                return {
                    "nextPageToken": "token2",
                    "items": [{"id": "c1", "snippet": {"topLevelComment": {"id": "c1", "snippet": {"textDisplay": "Comment 1", "publishedAt": "2026-10-01T00:00:00Z"}}}}]
                }
            elif pt == "token2":
                return {
                    "nextPageToken": "token3",
                    "items": [{"id": "c2", "snippet": {"topLevelComment": {"id": "c2", "snippet": {"textDisplay": "Comment 2", "publishedAt": "2026-10-02T00:00:00Z"}}}}]
                }
            elif pt == "token3":
                return {
                    "items": [{"id": "c3", "snippet": {"topLevelComment": {"id": "c3", "snippet": {"textDisplay": "Comment 3", "publishedAt": "2026-10-03T00:00:00Z"}}}}]
                }
        return {}

    monkeypatch.setattr(youtube, "_get", fake_get)
    comments = list(youtube.fetch(["query"], videos_per_query=1, delay=0, max_pages=2))
    assert len(comments) == 2
    assert [c.text for c in comments] == ["Comment 1", "Comment 2"]

    calls.clear()
    comments3 = list(youtube.fetch(["query"], videos_per_query=1, delay=0))
    assert len(comments3) == 3
    assert [c.text for c in comments3] == ["Comment 1", "Comment 2", "Comment 3"]


def _make_lead(lead_id, tier="Warm", score=0.5, review_status="pending", review_note="") -> Lead:
    return Lead(
        id=lead_id, tier=tier, score=score, confidence=0.6, label="seeker",
        course="Bharatanatyam", location="", online_interest=True, readiness=0.3,
        platform="youtube", posted_at="2026-10-10T12:00:00+00:00",
        date_status="verified", date_source="api",
        url=f"https://example.org/{lead_id}", original_url="", title="Test",
        snippet="Test snippet", reason="learner intent", source_query="q",
        collected_at="2026-10-20T12:00:00+00:00",
        review_status=review_status, review_note=review_note,
        notes="", reject_reason="", has_strong_cue=False,
        is_possible_teacher=False, is_offline_only=False,
    )


def test_update_review_saves_and_reloads(tmp_path):
    con = store.connect(tmp_path / "test.db")
    lead = _make_lead("rev001")
    store.upsert(con, [lead])
    # Initially pending
    assert store.load(con)[0].review_status == "pending"
    # Update review
    store.update_review(con, "rev001", "relevant", "Genuine learner")
    loaded = store.load(con)
    assert loaded[0].review_status == "relevant"
    assert loaded[0].review_note == "Genuine learner"


def test_upsert_preserves_review_status(tmp_path):
    """A pipeline re-run (upsert) must not reset existing review_status or review_note."""
    con = store.connect(tmp_path / "test.db")
    lead = _make_lead("rev002")
    store.upsert(con, [lead])
    store.update_review(con, "rev002", "false_positive", "Teacher ad")
    # Simulate a re-run: upsert the same lead again (score changed)
    lead2 = _make_lead("rev002", score=0.75)
    store.upsert(con, [lead2])
    loaded = store.load(con)
    assert loaded[0].review_status == "false_positive", "Re-run must not reset review_status"
    assert loaded[0].review_note == "Teacher ad", "Re-run must not reset review_note"
    assert loaded[0].score == 0.75, "Score should be updated"


def test_review_stats_from_db(tmp_path):
    con = store.connect(tmp_path / "test.db")
    store.upsert(con, [
        _make_lead("rs001", tier="Hot", score=0.9, review_status="relevant"),
        _make_lead("rs002", tier="Hot", score=0.8, review_status="false_positive", review_note="ad"),
        _make_lead("rs003", tier="Warm", score=0.5, review_status="unsure"),
        _make_lead("rs004", tier="Warm", score=0.4, review_status="pending"),
    ])
    stats = store.review_stats(con)
    assert stats["total_reviewed"] == 3
    assert stats["relevant"] == 1
    assert stats["false_positive"] == 1
    assert stats["unsure"] == 1
    assert stats["pending"] == 1
    assert stats["precision"] == 0.5
    assert stats["tier_precision"]["Hot"] == 0.5
    assert stats["tier_precision"]["Warm"] is None  # no fp or rel for Warm
    assert len(stats["false_positives"]) == 1
    assert stats["false_positives"][0][2] == "ad"


def test_review_stats_cli_db_mode(tmp_path):
    """review-stats without --csv reads from the DB and writes markdown."""
    from leadscout.cli import main
    db = tmp_path / "leads.db"
    con = store.connect(db)
    store.upsert(con, [
        _make_lead("cli001", tier="Hot", score=0.9, review_status="relevant"),
        _make_lead("cli002", tier="Hot", score=0.8, review_status="false_positive"),
    ])
    out_md = tmp_path / "summary.md"
    rc = main(["review-stats", "--db", str(db), "--out", str(out_md)])
    assert rc == 0
    md = out_md.read_text(encoding="utf-8")
    assert "**Relevant**: 1" in md
    assert "**False positive**: 1" in md
    assert "50.0%" in md


def test_export_reviewed_command(tmp_path):
    """export-reviewed writes a CSV with review_status and review_note from the DB."""
    from leadscout.cli import main
    db = tmp_path / "leads.db"
    con = store.connect(db)
    store.upsert(con, [
        _make_lead("er001", tier="Hot", score=0.9, review_status="relevant", review_note="Genuine"),
        _make_lead("er002", tier="Warm", score=0.5, review_status="false_positive", review_note="Ad"),
        _make_lead("er003", tier="Cold", score=0.3, review_status="pending"),
    ])
    out_csv = tmp_path / "reviewed.csv"
    rc = main(["export-reviewed", "--db", str(db), "--out", str(out_csv)])
    assert rc == 0
    assert out_csv.exists()
    rows = list(csv.DictReader(open(out_csv, encoding="utf-8")))
    assert len(rows) == 3
    # Sorted Hot -> Warm -> Cold
    assert rows[0]["id"] == "er001"
    assert rows[0]["review_status"] == "relevant"
    assert rows[0]["review_note"] == "Genuine"
    assert rows[1]["review_status"] == "false_positive"
    assert rows[1]["review_note"] == "Ad"
    assert rows[2]["review_status"] == "pending"



def test_store_cross_thread(tmp_path):
    """update_review and review_stats called from a different thread must not raise."""
    import threading
    db = tmp_path / "thread_test.db"
    # Create and populate DB in main thread
    con_main = store.connect(db)
    store.upsert(con_main, [_make_lead("th001", tier="Hot", score=0.9)])
    con_main.close()

    errors = []

    def worker():
        try:
            con = store.connect(db)
            try:
                store.update_review(con, "th001", "relevant", "from thread")
                stats = store.review_stats(con)
                assert stats["relevant"] == 1
            finally:
                con.close()
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert errors == [], f"Thread raised: {errors[0]}"





