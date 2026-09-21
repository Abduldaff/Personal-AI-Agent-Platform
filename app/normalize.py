"""Step 2-3: clean fields into one schema and drop duplicate postings."""
import hashlib
import re

CITY_ALIASES = {
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru", "bangalore urban": "Bengaluru",
    "gurgaon": "Delhi NCR", "gurugram": "Delhi NCR", "noida": "Delhi NCR", "new delhi": "Delhi NCR",
    "delhi": "Delhi NCR", "delhi ncr": "Delhi NCR", "ghaziabad": "Delhi NCR", "faridabad": "Delhi NCR",
    "bombay": "Mumbai", "navi mumbai": "Mumbai", "thane": "Mumbai",
    "madras": "Chennai", "calcutta": "Kolkata", "hyderabad": "Hyderabad", "secunderabad": "Hyderabad",
    "pune": "Pune", "mumbai": "Mumbai", "chennai": "Chennai", "kolkata": "Kolkata", "ahmedabad": "Ahmedabad",
}
COMPANY_SUFFIX = re.compile(r"\b(pvt\.?|private|ltd\.?|limited|inc\.?|llc|llp|corp\.?|corporation|technologies|technology)\b",
                            re.I)


def clean_city(city: str) -> str:
    c = (city or "").split(",")[0].strip()
    return CITY_ALIASES.get(c.lower(), c.title() if c else "")


def norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def company_key(name: str) -> str:
    return norm_key(COMPANY_SUFFIX.sub("", name or ""))


def job_id(company: str, title: str, city: str) -> str:
    raw = f"{company_key(company)}|{norm_key(title)}|{norm_key(city)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def normalize_and_dedupe(raw_jobs: list[dict]) -> tuple[list[dict], dict, dict]:
    """Returns (unique_jobs, stats, seen_ids_by_source)."""
    unique: dict[str, dict] = {}
    seen_by_source: dict[str, set] = {}
    dropped_invalid = 0
    for j in raw_jobs:
        title = re.sub(r"\s+", " ", (j.get("title") or "")).strip()
        company = re.sub(r"\s+", " ", (j.get("company") or "")).strip()
        if not title or not company:
            dropped_invalid += 1
            continue
        j = {**j, "title": title, "company": company, "city": clean_city(j.get("city", ""))}
        j["id"] = job_id(company, title, j["city"])
        seen_by_source.setdefault(j["source"], set()).add(j["id"])
        prev = unique.get(j["id"])
        if prev is None:
            unique[j["id"]] = j
        else:  # keep the richer copy and the earliest posting date
            keep = j if len(j.get("description", "")) > len(prev.get("description", "")) else prev
            dates = [d for d in (prev.get("posted_date"), j.get("posted_date")) if d]
            keep["posted_date"] = min(dates) if dates else ""
            unique[j["id"]] = keep
    stats = {"raw": len(raw_jobs), "unique": len(unique),
             "duplicates_removed": len(raw_jobs) - dropped_invalid - len(unique),
             "invalid_dropped": dropped_invalid}
    return list(unique.values()), stats, seen_by_source
