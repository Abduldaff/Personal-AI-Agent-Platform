"""Public company job-board endpoints (Greenhouse, Lever). No API key needed."""
import re
from datetime import datetime, timezone

import requests

from ..models import Job


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def fetch_greenhouse(cfg: dict, attempt: int = 0) -> list[Job]:
    jobs: list[Job] = []
    for token in cfg["company_boards"].get("greenhouse", []):
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                         params={"content": "true"}, timeout=30)
        r.raise_for_status()
        for it in r.json().get("jobs", []):
            jobs.append(Job(
                title=it.get("title", ""), company=token, city=(it.get("location") or {}).get("name", ""),
                country=cfg.get("country", ""), posted_date=(it.get("updated_at") or "")[:10],
                source="greenhouse", url=it.get("absolute_url", ""), description=_strip(it.get("content", "")),
            ))
    return jobs


def fetch_lever(cfg: dict, attempt: int = 0) -> list[Job]:
    jobs: list[Job] = []
    for token in cfg["company_boards"].get("lever", []):
        r = requests.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"}, timeout=30)
        r.raise_for_status()
        for it in r.json():
            ts = it.get("createdAt")
            posted = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat() if ts else ""
            cats = it.get("categories") or {}
            jobs.append(Job(
                title=it.get("text", ""), company=token, city=cats.get("location", ""),
                country=cfg.get("country", ""), posted_date=posted, source="lever",
                url=it.get("hostedUrl", ""), description=it.get("descriptionPlain", ""),
            ))
    return jobs
