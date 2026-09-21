"""SQLite storage. jobs accumulate across runs; runs table logs source health."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import date

import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT, company TEXT, city TEXT, country TEXT,
    posted_date TEXT, first_seen TEXT, last_seen TEXT,
    source TEXT, url TEXT, description TEXT, salary_text TEXT,
    is_fresher INTEGER, exp_min REAL, exp_max REAL,
    domain TEXT, skills TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT, source TEXT, jobs_fetched INTEGER, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_date);
"""


@contextmanager
def connect(path=None):
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_jobs(jobs: list[dict]) -> tuple[int, int]:
    """Insert new jobs / refresh last_seen. Returns (new, updated)."""
    today = date.today().isoformat()
    new = upd = 0
    with connect() as conn:
        for j in jobs:
            exists = conn.execute("SELECT 1 FROM jobs WHERE id=?", (j["id"],)).fetchone()
            if exists:
                conn.execute("UPDATE jobs SET last_seen=?, active=1 WHERE id=?", (today, j["id"]))
                upd += 1
            else:
                conn.execute(
                    """INSERT INTO jobs (id,title,company,city,country,posted_date,first_seen,last_seen,
                       source,url,description,salary_text,is_fresher,exp_min,exp_max,domain,skills,active)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                    (j["id"], j["title"], j["company"], j["city"], j["country"], j["posted_date"],
                     today, today, j["source"], j["url"], (j["description"] or "")[:4000],
                     j["salary_text"], j["is_fresher"], j["exp_min"], j["exp_max"], j["domain"],
                     json.dumps(j["skills"])),
                )
                new += 1
    return new, upd


def mark_inactive(source: str, seen_ids: set[str]) -> None:
    """Jobs from a source that vanished from its latest feed are marked inactive."""
    with connect() as conn:
        rows = conn.execute("SELECT id FROM jobs WHERE source=? AND active=1", (source,)).fetchall()
        gone = [r["id"] for r in rows if r["id"] not in seen_ids]
        conn.executemany("UPDATE jobs SET active=0 WHERE id=?", [(i,) for i in gone])


def log_run(source: str, fetched: int, error: str = "") -> None:
    with connect() as conn:
        conn.execute("INSERT INTO runs (run_date, source, jobs_fetched, error) VALUES (?,?,?,?)",
                     (date.today().isoformat(), source, fetched, error))


def read_jobs(only_fresher: bool = True) -> pd.DataFrame:
    with connect() as conn:
        q = "SELECT * FROM jobs" + (" WHERE is_fresher=1" if only_fresher else "")
        df = pd.read_sql_query(q, conn)
    if not df.empty:
        df["event_date"] = pd.to_datetime(df["posted_date"].replace("", None).fillna(df["first_seen"]),
                                          errors="coerce")
        df["skills"] = df["skills"].apply(lambda s: json.loads(s) if s else [])
    return df


def read_runs(limit: int = 50) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM runs ORDER BY run_id DESC LIMIT ?", conn, params=(limit,))


def reset_db() -> None:
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
