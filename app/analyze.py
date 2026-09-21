"""Step 7: every number in the report comes from here (pandas/SQL), never from the LLM."""
from collections import Counter

import pandas as pd

from . import db


def _pct(new: int, old: int):
    return None if old == 0 else round((new - old) / old * 100, 1)


def _window(df: pd.DataFrame, end: pd.Timestamp, days: int, offset: int = 0) -> pd.DataFrame:
    hi = end - pd.Timedelta(days=offset * days)
    lo = hi - pd.Timedelta(days=days)
    return df[(df["event_date"] > lo) & (df["event_date"] <= hi)]


def compute_metrics(cfg: dict) -> dict:
    w = cfg.get("window_days", 7)
    fresh, alljobs = db.read_jobs(True), db.read_jobs(False)
    if alljobs.empty:
        return {"empty": True}
    end = pd.Timestamp.today().normalize()
    f_now, f_prev = _window(fresh, end, w, 0), _window(fresh, end, w, 1)
    a_now = _window(alljobs, end, w, 0)

    dom_now, dom_prev = Counter(f_now["domain"]), Counter(f_prev["domain"])
    top_domains = [{"domain": d, "count": c, "share_pct": round(c / max(len(f_now), 1) * 100, 1),
                    "prev_count": dom_prev.get(d, 0), "change_pct": _pct(c, dom_prev.get(d, 0))}
                   for d, c in dom_now.most_common()]

    skills = Counter(s for row in f_now["skills"] for s in row)
    daily = (fresh[fresh["event_date"] > end - pd.Timedelta(days=2 * w)]
             .groupby(fresh["event_date"].dt.date).size())

    return {
        "empty": False,
        "window_days": w,
        "as_of": end.date().isoformat(),
        "postings_in_db": int(len(alljobs)),
        "fresher_in_db": int(len(fresh)),
        "ambiguous_in_db": int(alljobs["is_fresher"].isna().sum()),
        "fresher_now": int(len(f_now)), "fresher_prev": int(len(f_prev)),
        "fresher_change_pct": _pct(len(f_now), len(f_prev)),
        "companies_now": int(f_now["company"].nunique()), "companies_prev": int(f_prev["company"].nunique()),
        "companies_change_pct": _pct(f_now["company"].nunique(), f_prev["company"].nunique()),
        "all_postings_now": int(len(a_now)),
        "fresher_share_pct": round(len(f_now) / max(len(a_now), 1) * 100, 1),
        "other_domain_share": round((f_now["domain"] == "Other").mean(), 3) if len(f_now) else 0.0,
        "top_domains": top_domains,
        "top_companies": [{"company": c, "count": int(n)} for c, n in f_now["company"].value_counts().head(10).items()],
        "top_cities": [{"city": c or "Unknown", "count": int(n)} for c, n in f_now["city"].value_counts().head(8).items()],
        "top_skills": [{"skill": s, "count": n} for s, n in skills.most_common(12)],
        "sources_now": {k: int(v) for k, v in f_now["source"].value_counts().items()},
        "daily": {str(k): int(v) for k, v in daily.items()},
    }
