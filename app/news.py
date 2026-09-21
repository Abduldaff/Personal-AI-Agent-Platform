"""Step 8 (optional): market-news context via Tavily. Returns [] if no key or on any error."""
from datetime import date

import requests

from .config import env


def fetch_news(cfg: dict, max_results: int = 5) -> list[dict]:
    key = env("TAVILY_API_KEY")
    if not key:
        return []
    query = f"fresher hiring trends {cfg.get('country', '')} IT jobs {date.today().year}"
    try:
        r = requests.post("https://api.tavily.com/search", timeout=30,
                          headers={"Authorization": f"Bearer {key}"},
                          json={"query": query, "topic": "news", "max_results": max_results})
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": (x.get("content") or "")[:300]}
                for x in r.json().get("results", [])]
    except Exception:
        return []
