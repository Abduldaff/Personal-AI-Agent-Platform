"""Load config.yaml and environment variables."""
from pathlib import Path
import csv
import os

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_LIVE = ROOT / "data" / "jobs.db"
DB_DEMO = ROOT / "data" / "jobs_demo.db"
DB_PATH = DB_LIVE  # switched by use_db()
REPORT_DIR = ROOT / "reports"


def _merge_company_boards(cfg: dict) -> dict:
    companies_path = ROOT / "company_boards.csv"
    if not companies_path.exists():
        return cfg

    board_keys = {"greenhouse", "lever", "ashby", "workday"}
    extra = {k: [] for k in board_keys}

    with open(companies_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row is None:
                continue
            source = (row.get("source") or row.get("platform") or "").strip().lower()
            slug = (row.get("slug") or row.get("company") or "").strip()
            if not source or not slug:
                continue
            if source in board_keys:
                extra[source].append(slug)

    cfg.setdefault("company_boards", {})
    for source, values in extra.items():
        d = cfg["company_boards"].setdefault(source, [])
        for slug in values:
            if slug not in d:
                d.append(slug)
    for source in list(cfg["company_boards"]):
        if source in board_keys:
            cfg["company_boards"][source] = list(dict.fromkeys(cfg["company_boards"][source]))
    return cfg


def get_company_board_summary(cfg: dict) -> dict:
    boards = cfg.get("company_boards", {})
    summary = {source: len(values) for source, values in boards.items() if isinstance(values, list)}
    total = sum(summary.values())
    return {"source_counts": summary, "total_companies": total}


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return _merge_company_boards(cfg)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def use_db(demo: bool) -> Path:
    """Demo (synthetic) data lives in its own DB so it never mixes with real postings."""
    global DB_PATH
    DB_PATH = DB_DEMO if demo else DB_LIVE
    return DB_PATH
