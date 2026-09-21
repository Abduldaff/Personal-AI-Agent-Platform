"""Step 5: assign a domain from a FIXED taxonomy and extract skills (keyword scoring)."""
import re


def _rx(words: list[str]) -> re.Pattern:
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(w) for w in words) + r")(?![\w])", re.I)


def build_matchers(cfg: dict) -> dict:
    return {
        "domains": {d: _rx(kws) for d, kws in cfg["domains"].items()},
        "skills": {s: _rx([s]) for s in cfg["skills"]},
    }


def classify_job(job: dict, matchers: dict) -> dict:
    title, desc = job["title"], (job.get("description") or "")[:1500]
    scores = {}
    for dom, rx in matchers["domains"].items():
        scores[dom] = 3 * len(rx.findall(title)) + len(rx.findall(desc))
    best, top = max(scores.items(), key=lambda kv: kv[1])
    job["domain"] = best if top > 0 else "Other"
    job["skills"] = [s for s, rx in matchers["skills"].items() if rx.search(f"{title} {desc}")]
    return job


def classify_all(jobs: list[dict], cfg: dict) -> list[dict]:
    m = build_matchers(cfg)
    return [classify_job(j, m) for j in jobs]
