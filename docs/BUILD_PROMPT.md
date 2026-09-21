# Master prompt: Fresher Job Market Intelligence Agent

Paste this into Claude Code (or any coding assistant) to rebuild or extend the project from scratch.

---

You are a senior Python engineer. Build a **Fresher Job Market Intelligence Agent** that answers:
(1) how the current job market is moving for freshers, (2) how many companies are posting new fresher jobs,
(3) which domains are hiring the most.

## Hard rules
- All counts, trends and rankings are computed with pandas/SQL. The LLM must never produce numbers.
  It may only (a) label ambiguous postings and (b) write a narrative from a metrics JSON it is given.
- The agent must run end-to-end with NO API keys using a synthetic "mock" source, and must keep demo data in a
  separate database from live data.
- Do not scrape LinkedIn, Naukri or Indeed. Use official APIs (Adzuna) and public ATS endpoints (Greenhouse, Lever).
- One failing source must never crash a run. Config problems (missing key) must not be retried.

## Stack
Python 3.11, LangGraph, pandas, SQLite, requests, PyYAML, Streamlit + Plotly, APScheduler, optional Anthropic SDK
and Tavily. Keep configuration in `config.yaml` (country, cities, fresher rule, domain taxonomy, skills, companies).

## Pipeline (LangGraph nodes)
1. collect - fetch each source independently; log every source run (fetched count, error) to a `runs` table.
2. normalize - one Job schema; clean city aliases; dedupe across sources by hash(company|title|city).
3. label_fresher - rules first (experience ranges like "0-2 years", exclusion words like senior/lead, inclusion words
   like graduate/trainee/intern, word-boundary matching); leave unclear jobs as ambiguous (NULL). Optional LLM pass.
4. classify - fixed domain taxonomy from config (title matches weigh 3x description); extract skills by keyword.
5. store - upsert into `jobs` (id, title, company, city, posted_date, first_seen, last_seen, source, url, domain,
   is_fresher, exp_min, exp_max, skills, active); mark postings missing from the latest feed as inactive.
6. analyze - this window vs previous window: fresher postings, unique companies, fresher share, domains with
   week-over-week change, top companies, cities, skills, daily counts.
7. verify - flag failed/empty sources, small samples, week-over-week spikes, high "Other" share; output a confidence
   level. If retryable sources failed and retries remain, route back to collect for those sources only.
8. news (optional) - Tavily market-news context.
9. report - Markdown report with narrative, headline numbers, domain table, companies, cities, skills, and a
   "Data quality" section that states counts cover configured sources only.

## Deliverables
- Project layout: `app/` (config, models, db, sources/, normalize, fresher, classify, llm, analyze, verify, news,
  report, graph), `run.py` (CLI with --mock/--reset/--no-llm/--no-news), `scheduler.py`, `ui.py` (Streamlit dashboard
  with tabs: Domains, Companies and cities, Skills, Trend, Jobs, Report, Data health), `tests/`, README.
- Unit tests for: fresher rules (incl. "internal" must not match "intern"), dedupe across sources, classifier,
  API parsers with mocked HTTP, verify logic. A simulated-outage flag (MOCK_FAIL_ONCE=1) that exercises the retry loop.
- Be explicit in the README about what was tested and what needs real API keys.

## Definition of done
`python run.py --mock --reset` prints a complete report, `streamlit run ui.py` shows the dashboard, and
`python -m unittest discover tests` passes.
