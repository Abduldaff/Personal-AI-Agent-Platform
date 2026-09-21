"""Public company job-board endpoints (Greenhouse, Lever, Ashby, Workday). No API key needed."""
import re
from datetime import datetime, timezone

import requests

from ..models import Job


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def _pick(data: dict, *keys: str):
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    for key in keys:
        if "." in key:
            parent, child = key.split(".", 1)
            if parent in data and isinstance(data[parent], dict):
                val = data[parent].get(child)
                if val not in (None, ""):
                    return val
    return ""


def _normalize_date(value):
    if not value:
        return ""
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    if isinstance(value, str):
        val = value.strip()
        if val.endswith("Z"):
            val = val[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(val).date().isoformat()
        except ValueError:
            return val[:10]
    return ""


def fetch_greenhouse(cfg: dict, attempt: int = 0) -> list[Job]:
    jobs: list[Job] = []
    for token in cfg["company_boards"].get("greenhouse", []):
        try:
            r = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                params={"content": "true"},
                timeout=30,
            )
            r.raise_for_status()
            payload = r.json()
        except requests.RequestException:
            continue
        for it in payload.get("jobs", []):
            jobs.append(Job(
                title=it.get("title", ""), company=token, city=(it.get("location") or {}).get("name", ""),
                country=cfg.get("country", ""), posted_date=(it.get("updated_at") or "")[:10],
                source="greenhouse", url=it.get("absolute_url", ""), description=_strip(it.get("content", "")),
            ))
    return jobs


def fetch_lever(cfg: dict, attempt: int = 0) -> list[Job]:
    jobs: list[Job] = []
    for token in cfg["company_boards"].get("lever", []):
        try:
            r = requests.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"}, timeout=30)
            r.raise_for_status()
            payload = r.json()
        except requests.RequestException:
            continue
        for it in payload:
            ts = it.get("createdAt")
            posted = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat() if ts else ""
            cats = it.get("categories") or {}
            jobs.append(Job(
                title=it.get("text", ""), company=token, city=cats.get("location", ""),
                country=cfg.get("country", ""), posted_date=posted, source="lever",
                url=it.get("hostedUrl", ""), description=it.get("descriptionPlain", ""),
            ))
    return jobs


def fetch_ashby(cfg: dict, attempt: int = 0) -> list[Job]:
    jobs: list[Job] = []
    for token in cfg["company_boards"].get("ashby", []):
        try:
            page = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{token}", timeout=30)
            page.raise_for_status()
            data = page.json()
        except requests.RequestException:
            continue
        items = data.get("jobs") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not items:
            continue
        for it in items:
            title = _pick(it, "title", "jobTitle", "name")
            loc = _pick(it, "location", "locationName", "officeLocation", "workLocation")
            city = loc.get("city") if isinstance(loc, dict) else str(loc)
            url = _pick(it, "jobUrl", "url", "applicationUrl", "canonicalUrl", "publicUrl")
            if not url and _pick(it, "slug"):
                url = f"https://jobs.ashbyhq.com/{token}/{_pick(it, 'slug')}"
            jobs.append(Job(
                title=str(title or "Ashby role"), company=token, city=str(city or ""),
                country=cfg.get("country", ""), posted_date=_normalize_date(_pick(it, "createdAt", "publishedAt", "date")),
                source="ashby", url=str(url or ""), description=str(_pick(it, "description", "descriptionPlain", "content") or ""),
            ))
    return jobs


def fetch_workday(cfg: dict, attempt: int = 0) -> list[Job]:
    jobs: list[Job] = []
    for token in cfg["company_boards"].get("workday", []):
        domain = token if "." in token else f"{token}.workdayjobs.com"
        base = f"https://{domain}" if not domain.startswith("http") else domain.rstrip("/")
        try:
            page = requests.get(f"{base}/wday/cxs/{token}/jobs", timeout=30)
            page.raise_for_status()
            html = page.text
        except requests.RequestException:
            continue
        for m in re.finditer(r"href=[\"']((?:https?://[^\"']+?/job/[^\"']+|/wday/cxs/[^\"']+?/job/[^\"']+))[\'\"]", html, re.I):
            href = m.group(1)
            if not href.startswith("http"):
                href = f"{base}{href if href.startswith('/') else '/' + href}"
            title_match = re.search(r">([^<>]{1,120})</a>", html[m.start():m.start() + 400], re.S)
            title = title_match.group(1).strip() if title_match else "Workday role"
            jobs.append(Job(
                title=_strip(title), company=token, city="",
                country=cfg.get("country", ""), posted_date="",
                source="workday", url=href, description="",
            ))
    return jobs
