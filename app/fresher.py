"""Step 4: decide whether a posting is a fresher role. Rules first, LLM only for the leftovers."""
import re

NUM = r"(\d+(?:\.\d+)?)"
RANGE = re.compile(NUM + r"\s*(?:-|–|—|to)\s*" + NUM + r"\s*\+?\s*(?:years?|yrs?)", re.I)
SINGLE_A = re.compile(NUM + r"\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+\w+){0,2}?\s+experience", re.I)
SINGLE_B = re.compile(r"experience\W{0,4}" + NUM + r"\s*\+?\s*(?:years?|yrs?)", re.I)


def _kw_regex(words: list[str]) -> re.Pattern:
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(w) for w in words) + r")(?![\w])", re.I)


def extract_experience(text: str) -> tuple[float | None, float | None]:
    m = RANGE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = SINGLE_A.search(text) or SINGLE_B.search(text)
    if m:
        v = float(m.group(1))
        return v, v
    return None, None


def label_fresher(job: dict, cfg: dict) -> dict:
    fc = cfg["fresher"]
    inc, exc = _kw_regex(fc["include_keywords"]), _kw_regex(fc["exclude_title_keywords"])
    text = f"{job['title']}. {(job.get('description') or '')[:1500]}"
    lo, hi = extract_experience(text)
    job["exp_min"], job["exp_max"] = lo, hi
    limit = fc["max_years_experience"]

    if exc.search(job["title"]):
        job["is_fresher"] = 0
    elif lo is not None:
        job["is_fresher"] = 1 if (lo == 0 or (hi is not None and hi <= limit)) else 0
    elif inc.search(text):
        job["is_fresher"] = 1
    else:
        job["is_fresher"] = None  # ambiguous -> optional LLM pass
    return job


def label_all(jobs: list[dict], cfg: dict) -> list[dict]:
    return [label_fresher(j, cfg) for j in jobs]
