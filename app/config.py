"""Load config.yaml and environment variables."""
from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_LIVE = ROOT / "data" / "jobs.db"
DB_DEMO = ROOT / "data" / "jobs_demo.db"
DB_PATH = DB_LIVE  # switched by use_db()
REPORT_DIR = ROOT / "reports"


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def use_db(demo: bool) -> Path:
    """Demo (synthetic) data lives in its own DB so it never mixes with real postings."""
    global DB_PATH
    DB_PATH = DB_DEMO if demo else DB_LIVE
    return DB_PATH
