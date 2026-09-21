"""Dashboard:  streamlit run ui.py"""
import pandas as pd
import plotly.express as px
import streamlit as st

from app import analyze, config, db, verify as verify_mod
from app.graph import run_pipeline

TEAL, SLATE = "#0E7C86", "#B8C7D0"

st.set_page_config(page_title="Fresher Job Market", page_icon="📈", layout="wide")
cfg = config.load_config()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Fresher job market")
    data_mode = st.radio("Data", ["Demo data", "Live data"], help="Demo data is synthetic and lives in its own database.")
    demo = data_mode == "Demo data"
    config.use_db(demo)
    st.caption(f"Country: **{cfg.get('country', '').upper()}**  |  window: **{cfg['window_days']} days**")
    use_llm = st.toggle("Use LLM (needs ANTHROPIC_API_KEY)", value=False)
    use_news = st.toggle("Add market news (needs TAVILY_API_KEY)", value=False)
    if st.button("Run the agent now", type="primary", width="stretch"):
        with st.spinner("Collecting, labelling and verifying postings..."):
            state = run_pipeline(cfg, mock=demo, use_llm=use_llm, use_news=use_news)
        st.session_state["log"] = state["log"]
        st.session_state["report"] = state["report_text"]
        st.success("Run finished.")
    if st.session_state.get("log"):
        with st.expander("Agent steps"):
            st.code("\n".join(st.session_state["log"]), language="text")

# ------------------------------------------------------------------ data
metrics = analyze.compute_metrics(cfg)
if metrics.get("empty"):
    st.title("Fresher job market")
    st.info("No postings stored yet. Use **Run the agent now** in the sidebar. "
            + ("Demo data needs no keys." if demo else "Live data needs ADZUNA_APP_ID and ADZUNA_APP_KEY in .env."))
    st.stop()

runs = db.read_runs()
latest = {}
for _, r in runs.iterrows():  # runs are newest first
    latest.setdefault(r["source"], {"fetched": int(r["jobs_fetched"]), "error": r["error"] or ""})
verdict = verify_mod.verify(metrics, cfg, latest, {}, cfg["verify"]["max_retries"])

st.title("What freshers can apply for right now")
if demo:
    st.warning("Showing synthetic demo data. Switch to Live data in the sidebar once your API keys are set.")

c1, c2, c3, c4 = st.columns(4)
delta = lambda p: None if p is None else f"{p:+.0f}%"
c1.metric(f"Fresher postings ({metrics['window_days']}d)", metrics["fresher_now"], delta(metrics["fresher_change_pct"]))
c2.metric("Companies hiring", metrics["companies_now"], delta(metrics["companies_change_pct"]))
c3.metric("Fresher share of all postings", f"{metrics['fresher_share_pct']}%")
c4.metric("Data confidence", verdict["confidence"])

tab_dom, tab_co, tab_skill, tab_trend, tab_jobs, tab_report, tab_health = st.tabs(
    ["Domains", "Companies and cities", "Skills", "Trend", "Jobs", "Report", "Data health"])

with tab_dom:
    d = pd.DataFrame(metrics["top_domains"])
    if d.empty:
        st.write("No fresher postings in this window.")
    else:
        d = d.sort_values("count")
        colors = [SLATE] * (len(d) - 1) + [TEAL]
        fig = px.bar(d, x="count", y="domain", orientation="h", text="count")
        fig.update_traces(marker_color=colors, textposition="outside")
        fig.update_layout(height=max(320, 34 * len(d)), margin=dict(l=0, r=20, t=10, b=0),
                          xaxis_title="Fresher postings", yaxis_title=None)
        st.plotly_chart(fig, width="stretch")
        show = d.sort_values("count", ascending=False).rename(columns={
            "domain": "Domain", "count": "Postings", "share_pct": "Share %", "prev_count": "Previous period", "change_pct": "Change %"})
        st.dataframe(show, hide_index=True, width="stretch")

with tab_co:
    left, right = st.columns(2)
    with left:
        st.subheader("Companies posting the most")
        st.dataframe(pd.DataFrame(metrics["top_companies"]), hide_index=True, width="stretch")
    with right:
        st.subheader("Cities")
        cdf = pd.DataFrame(metrics["top_cities"])
        if not cdf.empty:
            fig = px.bar(cdf.sort_values("count"), x="count", y="city", orientation="h")
            fig.update_traces(marker_color=TEAL)
            fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig, width="stretch")

with tab_skill:
    sdf = pd.DataFrame(metrics["top_skills"])
    if not sdf.empty:
        fig = px.bar(sdf.sort_values("count"), x="count", y="skill", orientation="h")
        fig.update_traces(marker_color=TEAL)
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Postings mentioning skill", yaxis_title=None)
        st.plotly_chart(fig, width="stretch")

with tab_trend:
    daily = pd.Series(metrics["daily"], name="postings")
    if not daily.empty:
        fig = px.bar(daily.reset_index(), x="index", y="postings")
        fig.update_traces(marker_color=TEAL)
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Posting date", yaxis_title="Fresher postings")
        st.plotly_chart(fig, width="stretch")
    st.caption("Postings are placed by their posted date when the source provides one, otherwise by the day the agent first saw them.")

with tab_jobs:
    jobs = db.read_jobs(True)
    f1, f2, f3 = st.columns(3)
    dom = f1.multiselect("Domain", sorted(jobs["domain"].unique()))
    city = f2.multiselect("City", sorted(x for x in jobs["city"].unique() if x))
    q = f3.text_input("Search title or company")
    if dom:
        jobs = jobs[jobs["domain"].isin(dom)]
    if city:
        jobs = jobs[jobs["city"].isin(city)]
    if q:
        jobs = jobs[jobs["title"].str.contains(q, case=False) | jobs["company"].str.contains(q, case=False)]
    jobs = jobs.sort_values("event_date", ascending=False)
    st.caption(f"{len(jobs)} fresher postings")
    st.dataframe(jobs[["title", "company", "city", "domain", "posted_date", "url"]], hide_index=True,
                 width="stretch", column_config={"url": st.column_config.LinkColumn("Apply", display_text="Open")})

with tab_report:
    files = sorted(config.REPORT_DIR.glob(f"report_*{'_demo' if demo else ''}.md"))
    files = [f for f in files if demo or "_demo" not in f.name]
    if files:
        st.markdown(files[-1].read_text(encoding="utf-8"))
    else:
        st.write("No report yet. Run the agent from the sidebar.")

with tab_health:
    st.subheader("Verification")
    if verdict["issues"]:
        for i in verdict["issues"]:
            st.warning(i)
    else:
        st.success("No issues detected.")
    st.subheader("Recent source runs")
    st.dataframe(runs.drop(columns=["run_id"]), hide_index=True, width="stretch")
    st.caption("Counts describe postings in the configured sources, not the whole job market.")
