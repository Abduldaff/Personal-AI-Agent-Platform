"""Dashboard: streamlit run ui.py"""
import pandas as pd
import streamlit as st

from app import analyze, config, db, verify as verify_mod
from app.graph import run_pipeline

st.set_page_config(page_title="Fresher job market", page_icon="📈", layout="wide")


@st.cache_data(ttl=30, max_entries=4)
def get_dashboard_data(window_days: int, db_path: str, db_mtime_ns: int):
    cfg = config.load_config()
    return analyze.compute_metrics(cfg), db.read_runs(), cfg, db.read_jobs(only_fresher=False)


cfg = config.load_config()
board_summary = config.get_company_board_summary(cfg)

with st.sidebar:
    st.title("Job market")
    st.caption("Entry-level hiring intelligence")
    data_mode = st.radio(
        "Data set",
        ["Demo data", "Live data"],
        index=0,
        horizontal=True,
        help="Demo data is synthetic and stored separately from live postings.",
    )
    demo = data_mode == "Demo data"
    config.use_db(demo)
    st.caption(f"Country: **{cfg.get('country', '').upper()}** · Analysis window: **{cfg['window_days']} days**")

    st.subheader("Tracked sources")
    st.metric("Company boards", board_summary["total_companies"])
    for source, count in board_summary["source_counts"].items():
        st.caption(f"{source.title()} · {count} boards")
    st.caption(f"Adzuna · {len(cfg.get('search_keywords', []))} search terms")

    st.subheader("Run options")
    use_llm = st.toggle("AI labeling and narrative", value=False,
                        help="Uses ANTHROPIC_API_KEY when configured.")
    use_news = st.toggle("Market news context", value=False,
                         help="Uses TAVILY_API_KEY when configured.")
    run_clicked = st.button("Run data analysis", type="primary", width="stretch",
                             icon=":material/play_arrow:")

if run_clicked:
    with st.status("Collecting and analyzing postings...", expanded=True) as status_box:
        try:
            run_state = run_pipeline(config.load_config(), mock=demo, use_llm=use_llm, use_news=use_news)
        except Exception as exc:
            status_box.update(label="The analysis run failed", state="error", expanded=True)
            st.exception(exc)
        else:
            st.session_state["log"] = run_state["log"]
            st.session_state["report"] = run_state["report_text"]
            status_box.update(label="Analysis complete", state="complete", expanded=False)
            st.rerun()

db_mtime_ns = config.DB_PATH.stat().st_mtime_ns if config.DB_PATH.exists() else 0
metrics, runs, cfg, all_jobs = get_dashboard_data(
    cfg["window_days"], str(config.DB_PATH), db_mtime_ns
)

st.title("Fresher job market")
st.caption(
    f"{'Synthetic demo' if demo else 'Live sources'} · {cfg.get('country', '').upper()} · "
    f"As of {metrics.get('as_of', pd.Timestamp.now().date().isoformat())}"
)
if demo:
    st.info("Demo mode uses synthetic postings. Switch to Live data for real provider data.",
            icon=":material/science:")

if metrics.get("empty"):
    st.info(
        "No postings are available for this period. Run the analysis from the sidebar. "
        + ("Demo data needs no API keys." if demo else "Live collection needs valid provider credentials."),
        title="Waiting for data",
    )
    st.stop()

latest_runs = {}
for _, run in runs.iterrows():
    latest_runs.setdefault(run["source"], {
        "fetched": int(run["jobs_fetched"]),
        "error": run["error"] or "",
        "run_date": run["run_date"],
    })
verdict = verify_mod.verify(metrics, cfg, latest_runs, {}, cfg["verify"]["max_retries"])

total_stored = len(all_jobs)
kpi_cols = st.columns(4)
kpi_cols[0].metric(
    f"Fresher jobs ({metrics['window_days']}d)",
    f"{metrics['fresher_now']:,}",
    None if metrics["fresher_change_pct"] is None else f"{metrics['fresher_change_pct']:+.1f}% vs previous",
    border=True,
)
kpi_cols[1].metric("All stored postings", f"{total_stored:,}", border=True)
kpi_cols[2].metric("Companies hiring", f"{metrics['companies_now']:,}",
                   None if metrics["companies_change_pct"] is None else f"{metrics['companies_change_pct']:+.1f}% vs previous",
                   border=True)
kpi_cols[3].metric("Data confidence", verdict["confidence"], border=True)

detail_cols = st.columns(3)
detail_cols[0].metric("All postings in current window", f"{metrics['all_postings_now']:,}")
detail_cols[1].metric("Fresher share", f"{metrics['fresher_share_pct']}%")
detail_cols[2].metric("Fresher postings previous period", f"{metrics['fresher_prev']:,}")

if verdict["issues"]:
    with st.container(border=True):
        st.subheader("Data quality notes")
        for issue in verdict["issues"]:
            st.warning(issue)

st.divider()
st.header("Hiring analysis")

domains = pd.DataFrame(metrics["top_domains"])
top_domains = domains[domains["domain"] != "Other"] if not domains.empty else domains
top_domain = top_domains.iloc[0] if not top_domains.empty else None
top_skill = metrics["top_skills"][0] if metrics["top_skills"] else None
insight_cols = st.columns(3)
insight_cols[0].metric(
    "Leading hiring domain",
    top_domain["domain"] if top_domain is not None else "Not enough data",
    f"{int(top_domain['count'])} fresher postings" if top_domain is not None else None,
    border=True,
)
insight_cols[1].metric(
    "Most mentioned skill",
    top_skill["skill"].title() if top_skill else "Not enough data",
    f"In {top_skill['count']} postings" if top_skill else None,
    border=True,
)
insight_cols[2].metric(
    "Unclassified fresher postings",
    f"{metrics['other_domain_share']:.1%}",
    help="Share labeled as Other; a high value means the domain keywords may need tuning.",
    border=True,
)

chart_left, chart_right = st.columns(2)
with chart_left:
    st.subheader("Postings by domain")
    if domains.empty:
        st.caption("No fresher postings to chart in this period.")
    else:
        st.bar_chart(domains.set_index("domain")[["count"]], horizontal=True,
                     x_label="Fresher postings", y_label="Domain", height=380)
        display_domains = domains.rename(columns={
            "domain": "Domain", "count": "Postings", "share_pct": "Share of fresher jobs",
            "prev_count": "Previous period", "change_pct": "Change (%)",
        })
        st.dataframe(display_domains, hide_index=True, width="stretch")

with chart_right:
    st.subheader("Daily fresher postings")
    daily = pd.DataFrame(
        [(pd.Timestamp(day), count) for day, count in metrics["daily"].items()],
        columns=["Date", "Postings"],
    ).sort_values("Date")
    if daily.empty:
        st.caption("No dated postings to chart.")
    else:
        st.bar_chart(daily.set_index("Date"), y="Postings", x_label="Date",
                     y_label="Fresher postings", height=300)
    st.caption("Uses the posting date when available; otherwise the date the job was first seen.")

st.divider()
st.header("Companies, locations, and skills")
company_col, city_col = st.columns(2)
with company_col:
    st.subheader("Companies with most fresher postings")
    st.dataframe(pd.DataFrame(metrics["top_companies"]), hide_index=True, width="stretch")
with city_col:
    st.subheader("Top hiring locations")
    cities = pd.DataFrame(metrics["top_cities"])
    if cities.empty:
        st.caption("No location data for this period.")
    else:
        st.bar_chart(cities.set_index("city")[["count"]], horizontal=True,
                     x_label="Fresher postings", y_label="Location", height=300)

st.subheader("Most requested skills")
skills = pd.DataFrame(metrics["top_skills"])
if skills.empty:
    st.caption("No skill data available.")
else:
    st.bar_chart(skills.set_index("skill")[["count"]], horizontal=True,
                 x_label="Postings mentioning skill", y_label="Skill", height=360)

st.divider()
st.header("Source coverage and run history")
configured_sources = []
for source in ("adzuna", "greenhouse", "lever", "ashby", "workday"):
    if source == "adzuna":
        configured_items = len(cfg.get("search_keywords", [])) * max(len(cfg.get("cities") or [""]), 1)
        unit = "searches"
    else:
        configured_items = len(cfg.get("company_boards", {}).get(source, []))
        unit = "boards"
    latest = latest_runs.get(source, {})
    configured_sources.append({
        "Source": source.title(),
        "Configured": f"{configured_items} {unit}",
        "Fresher postings in window": metrics.get("sources_now", {}).get(source, 0),
        "Latest fetch": latest.get("fetched", "Not run"),
        "Last run": latest.get("run_date", "Not run"),
        "Status": latest.get("error") or ("OK" if latest else "Not run"),
    })
st.dataframe(pd.DataFrame(configured_sources), hide_index=True, width="stretch")

with st.expander("Recent source runs and agent steps"):
    if runs.empty:
        st.caption("No source runs recorded yet.")
    else:
        st.dataframe(runs.drop(columns=["run_id"]), hide_index=True, width="stretch")
    if st.session_state.get("log"):
        st.code("\n".join(st.session_state["log"]), language="text")

st.divider()
st.header("All stored job postings")
if all_jobs.empty:
    st.caption("There are no stored postings.")
else:
    jobs = all_jobs.copy()
    jobs["Experience fit"] = jobs["is_fresher"].map({1: "Fresher", 0: "Not fresher"}).fillna("Unclear")
    with st.container(border=True):
        filter_cols = st.columns(4)
        domains_filter = filter_cols[0].multiselect("Domain", sorted(jobs["domain"].dropna().unique()))
        cities_filter = filter_cols[1].multiselect("Location", sorted(c for c in jobs["city"].dropna().unique() if c))
        sources_filter = filter_cols[2].multiselect("Source", sorted(jobs["source"].dropna().unique()))
        fit_filter = filter_cols[3].multiselect(
            "Experience fit", ["Fresher", "Not fresher", "Unclear"], default=["Fresher"]
        )
        query = st.text_input("Search jobs", placeholder="Search title, company, location, or description")

    if domains_filter:
        jobs = jobs[jobs["domain"].isin(domains_filter)]
    if cities_filter:
        jobs = jobs[jobs["city"].isin(cities_filter)]
    if sources_filter:
        jobs = jobs[jobs["source"].isin(sources_filter)]
    if fit_filter:
        jobs = jobs[jobs["Experience fit"].isin(fit_filter)]
    if query:
        search_fields = jobs[["title", "company", "city", "description"]].fillna("").astype(str)
        matches = search_fields.apply(
            lambda column: column.str.contains(query, case=False, regex=False)
        ).any(axis=1)
        jobs = jobs[matches]

    st.caption(f"Showing {len(jobs):,} matching postings from {total_stored:,} stored.")
    visible_columns = ["title", "company", "city", "country", "domain", "Experience fit",
                       "posted_date", "source", "salary_text", "url"]
    st.dataframe(
        jobs[visible_columns].rename(columns={
            "title": "Title", "company": "Company", "city": "Location", "country": "Country",
            "domain": "Domain", "posted_date": "Posted", "source": "Source", "salary_text": "Salary",
            "url": "Apply",
        }),
        hide_index=True,
        width="stretch",
        height=520,
        column_config={"Apply": st.column_config.LinkColumn("Apply", display_text="Open")},
    )
    st.download_button(
        "Download matching postings",
        jobs[visible_columns].to_csv(index=False),
        file_name="job_postings.csv",
        mime="text/csv",
        icon=":material/download:",
    )

st.divider()
st.header("Latest report")
if st.session_state.get("report"):
    st.markdown(st.session_state["report"])
else:
    report_files = sorted(config.REPORT_DIR.glob(f"report_*{'_demo' if demo else ''}.md"))
    report_files = [path for path in report_files if demo or "_demo" not in path.name]
    if report_files:
        st.markdown(report_files[-1].read_text(encoding="utf-8"))
    else:
        st.caption("No report generated yet. Run the analysis to create one.")

st.caption("Counts cover configured sources only; they do not represent the entire job market.")
