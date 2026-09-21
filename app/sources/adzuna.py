"""Adzuna job search API (free tier: https://developer.adzuna.com)."""
import time
import requests

from ..config import env
from ..models import Job, SourceConfigError

BASE = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def fetch(cfg: dict, attempt: int = 0) -> list[Job]:
    app_id, app_key = env("ADZUNA_APP_ID"), env("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        raise SourceConfigError("ADZUNA_APP_ID / ADZUNA_APP_KEY not set (see .env.example)")
    country = cfg.get("country", "in")
    cities = cfg.get("cities") or [""]
    jobs: list[Job] = []
    for keyword in cfg["search_keywords"]:
        for city in cities:
            for page in (1, 2, 3):
                params = {
                    "app_id": app_id, "app_key": app_key, "results_per_page": 50,
                    "what": keyword, "max_days_old": cfg.get("max_days_old", 14),
                    "sort_by": "date", "content-type": "application/json",
                }
                if city:
                    params["where"] = city
                r = requests.get(BASE.format(country=country, page=page), params=params, timeout=30)
                r.raise_for_status()
                results = r.json().get("results", [])
                for it in results:
                    loc = (it.get("location") or {}).get("area") or []
                    jobs.append(Job(
                        title=it.get("title", ""),
                        company=(it.get("company") or {}).get("display_name", "Unknown"),
                        city=loc[-1] if loc else (it.get("location") or {}).get("display_name", ""),
                        country=country,
                        posted_date=(it.get("created") or "")[:10],
                        source="adzuna", url=it.get("redirect_url", ""),
                        description=it.get("description", ""),
                        salary_text=_salary(it),
                    ))
                if len(results) < 50:
                    break
                time.sleep(0.4)  # be polite to the API
    return jobs


def _salary(it: dict) -> str:
    lo, hi = it.get("salary_min"), it.get("salary_max")
    return f"{int(lo)}-{int(hi)}" if lo and hi else ""
