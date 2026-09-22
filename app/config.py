"""Load config.yaml and environment variables."""
from pathlib import Path
import csv
import os
import re
from typing import Optional, Union

import yaml
from dotenv import load_dotenv

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_LIVE = ROOT / "data" / "jobs.db"
DB_DEMO = ROOT / "data" / "jobs_demo.db"
DB_PATH = DB_LIVE  # switched by use_db()
REPORT_DIR = ROOT / "reports"
BOARD_KEYS = {"greenhouse", "lever", "ashby", "workday"}


def _slugify_company_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = text.replace("/", " ")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-").lower()
    return text


def _dedupe(items):
    seen = set()
    ordered = []
    for item in items:
        val = (item or "").strip()
        if not val:
            continue
        if val not in seen:
            seen.add(val)
            ordered.append(val)
    return ordered


def _merge_company_boards(cfg: dict) -> dict:
    cfg.setdefault("company_boards", {})

    companies_path = ROOT / "company_boards.csv"
    if companies_path.exists():
        extra = {k: [] for k in BOARD_KEYS}
        with open(companies_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row is None:
                    continue
                source = (row.get("source") or row.get("platform") or "").strip().lower()
                slug = (row.get("slug") or row.get("company") or "").strip()
                if not source or not slug:
                    continue
                if source in BOARD_KEYS:
                    extra[source].append(slug)
        for source, values in extra.items():
            d = cfg["company_boards"].setdefault(source, [])
            for slug in values:
                if slug not in d:
                    d.append(slug)

    pdf_path = _detect_company_pdf_path()
    if pdf_path and pdf_path.exists():
        refresh_company_boards_from_pdf(pdf_path, cfg)

    for source in list(cfg["company_boards"]):
        if source in BOARD_KEYS:
            cfg["company_boards"][source] = _dedupe(cfg["company_boards"][source])
    return cfg


def extract_company_names_from_pdf(pdf_path: Union[Path, str]) -> list[str]:
    path = Path(pdf_path)
    if not path.exists() or PdfReader is None:
        return []

    try:
        reader = PdfReader(str(path))
    except Exception:
        return []

    raw_text = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            raw_text.append(text)
    if not raw_text:
        return []

    text = "\n".join(raw_text)
    cleaned = text.replace("\xa0", " ")
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    companies = []
    for line in lines:
        lowered = line.lower()
        if not line or lowered in {"serial no.", "company name", "official career site link", "official linkedin account", "official hr / career mail"}:
            continue
        if "http" in lowered or "linkedin.com" in lowered or "career" in lowered and "site" in lowered:
            continue
        if lowered.startswith("not publicly") or lowered.startswith("not provided"):
            continue
        if re.fullmatch(r"\d+", line):
            continue
        if any(token in lowered for token in ["serial no", "company name", "official", "career site", "linkedin", "hr / career mail"]):
            continue
        if len(line) < 3:
            continue
        if re.fullmatch(r"[A-Za-z0-9& .'-]+", line):
            companies.append(line)
    return _dedupe(companies)


def _detect_company_pdf_path() -> Optional[Path]:
    env_paths = [
        os.getenv("COMPANY_PDF_PATH"),
        os.getenv("COMPANY_BOARDS_PDF_PATH"),
    ]
    for value in env_paths:
        if value:
            candidate = Path(value).expanduser()
            if candidate.exists():
                return candidate

    candidates = [
        ROOT / "company_boards.pdf",
        ROOT / "companies.pdf",
        ROOT / "data" / "company_boards.pdf",
        Path.home() / "Downloads",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            for file in sorted(candidate.glob("*.pdf")):
                if "company" in file.name.lower() or "career" in file.name.lower():
                    return file
        elif candidate.exists() and candidate.suffix.lower() == ".pdf":
            return candidate

    if (Path.home() / "Downloads").exists():
        for file in sorted((Path.home() / "Downloads").glob("*.pdf")):
            if "company" in file.name.lower() or "career" in file.name.lower():
                return file
    return None


def refresh_company_boards_from_pdf(pdf_path: Optional[Union[Path, str]] = None, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or {}
    cfg.setdefault("company_boards", {})
    resolved = Path(pdf_path) if pdf_path is not None else _detect_company_pdf_path()
    if resolved is None:
        return cfg
    names = extract_company_names_from_pdf(resolved)
    if not names:
        return cfg

    for company_name in names:
        slug = _slugify_company_name(company_name)
        if not slug:
            continue
        for source in BOARD_KEYS:
            values = cfg["company_boards"].setdefault(source, [])
            if slug not in values:
                values.append(slug)
    return cfg


def get_company_board_summary(cfg: dict) -> dict:
    boards = cfg.get("company_boards", {})
    summary = {source: len(values) for source, values in boards.items() if isinstance(values, list)}
    total = sum(summary.values())
    return {"source_counts": summary, "total_companies": total}


def load_config(path: Optional[Path] = None) -> dict:
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
