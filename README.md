# Fresher Job Market Intelligence Agent

An agent that answers three questions about entry-level hiring:

1. How is the fresher job market moving right now (this week vs last week)?
2. How many companies are posting new fresher jobs?
3. Which domains are hiring the most?

**Design rule:** every number comes from pandas/SQL. The LLM (optional) only labels ambiguous postings and
writes the narrative from numbers it is given.

## Quick start (no API keys)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py --mock --reset --no-llm --no-news        # demo run, prints a report
streamlit run ui.py                                    # dashboard (choose "Demo data")
python -m unittest discover tests                      # tests
```

Demo data is **synthetic** and stored in `data/jobs_demo.db`, separate from live data.

## Going live

1. Get free keys at https://developer.adzuna.com and copy `.env.example` to `.env`:
   `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`.
2. Edit `config.yaml`: `country` (Adzuna code, e.g. `in`), `cities`, `search_keywords`.
3. (Recommended) add company career pages to `company_boards` (Greenhouse / Lever slugs).
   Open `https://boards.greenhouse.io/<slug>` or `https://jobs.lever.co/<slug>` to confirm a slug exists.
4. `python run.py` then `streamlit run ui.py` and choose **Live data**.
5. Optional: `ANTHROPIC_API_KEY` (better labelling + narrative), `TAVILY_API_KEY` (market news).
6. Schedule: `python scheduler.py --hour 7` runs the full pipeline daily.

## Pipeline (LangGraph, `app/graph.py`)

```
collect -> normalize -> label_fresher -> classify -> store -> analyze -> verify -+-> news -> report
   ^                                                                             |
   +------------------ retry failed sources (max_retries) -----------------------+
```

| Step | File | What it does |
|---|---|---|
| collect | `app/sources/` | Adzuna, Greenhouse, Lever (one source failing never kills the run) |
| normalize | `app/normalize.py` | one schema, city aliases, cross-source de-duplication |
| label_fresher | `app/fresher.py` | experience regex + keyword rules; unclear cases stay "ambiguous" |
| classify | `app/classify.py` | fixed domain taxonomy + skill extraction (`config.yaml`) |
| store | `app/db.py` | SQLite; `first_seen`, `last_seen`, `active` per posting |
| analyze | `app/analyze.py` | week-over-week counts, companies, domains, skills, cities |
| verify | `app/verify.py` | source health, small sample, spikes, unclassified share -> confidence |
| report | `app/report.py` | Markdown report in `reports/` |

## Limits to keep in mind

- Numbers describe postings **in your configured sources**, not the whole market. The report says so.
- LinkedIn, Naukri and Indeed forbid scraping and are deliberately not used.
- "Fresher" is a rule in `config.yaml` (default: 0-1 years). Change it there.
- "Inactive" means a posting dropped out of the latest feed window (e.g. older than `max_days_old`).

## Tested vs not tested

Tested: the full pipeline on demo data, the outage-retry loop (`MOCK_FAIL_ONCE=1 python run.py --mock --reset`),
the dashboard (Streamlit AppTest), and 11 unit tests. Parsers for Adzuna, Greenhouse and Lever are tested against
mocked responses. **Not tested here:** real calls to Adzuna/Greenhouse/Lever, the Anthropic LLM step and the Tavily
news step (they need your keys and internet). Run once with your keys and check the first report.

## Ideas for next steps

- Add more sources (JSearch, Jooble) as new files in `app/sources/` and register them in `app/sources/__init__.py`.
- Email or Telegram the weekly report; deploy the dashboard with Docker or Streamlit Community Cloud.
- Track a hand-labelled sample of 100 postings to measure classifier accuracy.
