"""Step 9: sanity checks. Decides whether to retry a source and how confident the report is."""


def verify(metrics: dict, cfg: dict, source_status: dict, stats: dict, attempt: int) -> dict:
    v = cfg["verify"]
    issues: list[str] = []
    retry_sources: list[str] = []
    score = 3

    for name, st in source_status.items():
        if st.get("error"):
            issues.append(f"Source '{name}' failed: {st['error']}")
            score -= 1
            if st.get("retryable", True) and attempt < v["max_retries"]:
                retry_sources.append(name)
        elif st.get("fetched", 0) == 0:
            issues.append(f"Source '{name}' returned 0 postings - counts may be understated.")
            score -= 1

    if metrics.get("empty"):
        issues.append("No postings stored yet.")
        return {"issues": issues, "retry_sources": retry_sources, "confidence": "Low", "score": 0}

    small_sample = metrics["fresher_now"] < v["min_fresher_jobs"]
    if small_sample:
        issues.append(f"Small sample: only {metrics['fresher_now']} fresher postings this period "
                      f"(minimum {v['min_fresher_jobs']}). Treat percentages as rough.")
        score -= 2
    chg = metrics.get("fresher_change_pct")
    prev_count = metrics.get("fresher_prev", 0)
    if (chg is not None and prev_count > 0 and not small_sample and
            metrics["fresher_now"] >= v["min_fresher_jobs"] and prev_count >= max(5, v["min_fresher_jobs"] // 2)):
        ratio = metrics["fresher_now"] / prev_count
        if ratio >= v["spike_ratio"] or ratio <= 1 / v["spike_ratio"]:
            issues.append(f"Large swing ({chg:+.0f}% week over week) - check for duplicate feeds or a source change "
                          "before reading it as a market shift.")
            score -= 1
    if (metrics["other_domain_share"] > v["max_other_domain_share"] and
            metrics["fresher_now"] >= v["min_fresher_jobs"]):
        issues.append(f"{metrics['other_domain_share']:.0%} of fresher jobs are unclassified ('Other') - "
                      "extend domain keywords in config.yaml.")
        score -= 1
    ambiguous_share = metrics.get("ambiguous_in_db", 0) / max(metrics.get("postings_in_db", 1), 1)
    if metrics.get("ambiguous_in_db", 0) and ambiguous_share > 0.5:
        issues.append(f"{metrics['ambiguous_in_db']} postings had no clear experience signal and are not counted as fresher.")

    confidence = "High" if score >= 3 else "Medium" if score == 2 else "Low"
    return {"issues": issues, "retry_sources": retry_sources, "confidence": confidence, "score": score}
