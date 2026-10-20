"""Streamlit search interface:  streamlit run app.py"""
import os

import pandas as pd
import streamlit as st

from leadscout import store

DB = os.getenv("LEADSCOUT_DB", "data/leads.db")
st.set_page_config(page_title="LeadScout", layout="wide")
st.title("LeadScout: public learner-interest discussions")
st.caption("Each row is a public discussion link to review by hand. It is a research opportunity, "
           "not a verified customer. Do not scrape private contact details or send unsolicited messages.")


def _load_leads():
    con = store.connect(DB)
    try:
        return store.load(con)
    finally:
        con.close()


def _do_update_review(lead_id, status, note):
    con = store.connect(DB)
    try:
        store.update_review(con, lead_id, status, note)
    finally:
        con.close()


try:
    df = pd.DataFrame([l.as_row() for l in _load_leads()])
except Exception as exc:  # pragma: no cover
    df = pd.DataFrame()
    st.error(f"Could not read {DB}: {exc}")

if df.empty:
    st.info("No data yet. Run:  python -m leadscout run --csv data/sample_real_sources.csv")
    st.stop()

tab_results, tab_review = st.tabs(["Results", "Review"])

# ── Results tab ──────────────────────────────────────────────────────────────
with tab_results:
    with st.sidebar:
        st.header("Search")
        courses = st.multiselect("Course", sorted(df["course"].unique()))
        location = st.text_input("Location contains", placeholder="e.g. USA, Pune")
        keywords = st.text_input("Keywords (comma-separated, any match)", placeholder="beginner, adult, online")
        tiers = st.multiselect("Tier", ["Hot", "Warm", "Cold"], default=["Hot", "Warm", "Cold"])
        min_conf = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)
        online_only = st.checkbox("Only people who mention online")
        date_filter = st.selectbox("Date", ["All", "Dated only", "Undated only"])
        hide_unknown_date = st.checkbox("Hide posts with unknown date")

    view = df[df["tier"].isin(tiers) & (df["confidence"] >= min_conf)]
    if courses:
        view = view[view["course"].isin(courses)]
    if location:
        view = view[view["location"].str.contains(location, case=False, na=False)]
    if keywords.strip():
        kws = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        hay = (view["title"] + " " + view["snippet"] + " " + view["reason"]).str.lower()
        view = view[hay.apply(lambda h: any(k in h for k in kws))]
    if online_only:
        view = view[view["online_interest"]]
    if date_filter == "Dated only":
        view = view[view["date_status"].isin(["verified", "unverified", "known"])]
    elif date_filter == "Undated only":
        view = view[view["date_status"] == "unknown"]
    elif hide_unknown_date:
        view = view[view["date_status"].isin(["verified", "unverified", "known"])]
    view = view.sort_values("score", ascending=False)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Shown", len(view))
    for col, t in zip((c2, c3, c4), ("Hot", "Warm", "Cold")):
        col.metric(t, int((view["tier"] == t).sum()))

    display_cols = [c for c in [
        "tier", "score", "confidence", "has_strong_cue", "course", "location", "online_interest",
        "posted_at", "date_source", "platform", "title", "reason", "url", "original_url"
    ] if c in view.columns]

    st.dataframe(
        view[display_cols],
        column_config={
            "url": st.column_config.LinkColumn("canonical link"),
            "original_url": st.column_config.LinkColumn("original link"),
        },
        width="stretch", hide_index=True,
    )
    st.download_button("Download filtered CSV", view.to_csv(index=False).encode(), "leads_filtered.csv", "text/csv")

# ── Review tab ───────────────────────────────────────────────────────────────
with tab_review:
    st.subheader("Manual Review")

    TIER_ORDER = {"Hot": 0, "Warm": 1, "Cold": 2}
    all_leads = _load_leads()
    all_leads.sort(key=lambda l: (TIER_ORDER.get(l.tier, 3), -l.score))

    pending_leads = [l for l in all_leads if (l.review_status or "pending") == "pending"
                     and l.tier in ("Hot", "Warm", "Cold")]
    reviewed = [l for l in all_leads if (l.review_status or "pending") != "pending"]

    total = len(pending_leads) + len(reviewed)
    n_reviewed = len(reviewed)

    status_counts = {}
    for l in reviewed:
        s = l.review_status or "pending"
        status_counts[s] = status_counts.get(s, 0) + 1

    prog_col1, prog_col2, prog_col3, prog_col4 = st.columns(4)
    prog_col1.metric("Reviewed", f"{n_reviewed} / {total}")
    prog_col2.metric("Relevant", status_counts.get("relevant", 0))
    prog_col3.metric("False positive", status_counts.get("false_positive", 0))
    prog_col4.metric("Unsure", status_counts.get("unsure", 0))

    if "review_idx" not in st.session_state:
        st.session_state.review_idx = 0
    if "review_history" not in st.session_state:
        st.session_state.review_history = []

    idx = st.session_state.review_idx
    if idx >= len(pending_leads):
        st.success("🎉 All pending leads have been reviewed!")
    else:
        lead = pending_leads[idx]

        st.markdown(f"**Lead {idx + 1} of {len(pending_leads)} pending**")
        info_cols = st.columns([1, 1, 1, 2])
        info_cols[0].metric("Tier", lead.tier)
        info_cols[1].metric("Score", f"{lead.score:.2f}")
        info_cols[2].metric("Confidence", f"{lead.confidence:.2f}")
        info_cols[3].write(f"**Platform**: {lead.platform} | **Posted**: {lead.posted_at or 'unknown'} ({lead.date_source})")

        st.markdown(f"🔗 [{lead.url}]({lead.url})")
        st.markdown(f"**Snippet**: {lead.snippet}")
        st.markdown(f"**Reason**: _{lead.reason}_")
        if lead.notes:
            st.markdown(f"**Notes**: {lead.notes}")

        review_note = st.text_input("Review note (optional)", key=f"note_{lead.id}")

        btn_cols = st.columns(5)
        if btn_cols[0].button("✅ Relevant", key="btn_relevant"):
            _do_update_review(lead.id, "relevant", review_note)
            st.session_state.review_history.append((lead.id, "relevant", review_note))
            st.session_state.review_idx += 1
            st.rerun()
        if btn_cols[1].button("❌ False positive", key="btn_fp"):
            _do_update_review(lead.id, "false_positive", review_note)
            st.session_state.review_history.append((lead.id, "false_positive", review_note))
            st.session_state.review_idx += 1
            st.rerun()
        if btn_cols[2].button("🤔 Unsure", key="btn_unsure"):
            _do_update_review(lead.id, "unsure", review_note)
            st.session_state.review_history.append((lead.id, "unsure", review_note))
            st.session_state.review_idx += 1
            st.rerun()
        if btn_cols[3].button("⏭ Skip", key="btn_skip"):
            st.session_state.review_idx += 1
            st.rerun()
        if btn_cols[4].button("⬅ Back", key="btn_back", disabled=len(st.session_state.review_history) == 0):
            if st.session_state.review_history:
                prev_id, _, _ = st.session_state.review_history.pop()
                _do_update_review(prev_id, "pending", "")
                st.session_state.review_idx = max(0, st.session_state.review_idx - 1)
                st.rerun()


