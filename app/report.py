"""Step 10: turn metrics + verification into a Markdown report."""
from datetime import date

from . import llm
from .config import REPORT_DIR


def _arrow(pct):
    if pct is None:
        return "n/a (no data for previous period)"
    return f"{'▲' if pct >= 0 else '▼'} {abs(pct):.1f}% vs previous period"


def template_narrative(m: dict) -> str:
    top = m["top_domains"][:3]
    names = ", ".join(f"{d['domain']} ({d['count']})" for d in top) or "no clear leader"
    chg = m["fresher_change_pct"]
    trend = "no comparison available yet" if chg is None else f"{'up' if chg >= 0 else 'down'} {abs(chg):.0f}% from the previous period"
    return (f"In the last {m['window_days']} days the tracked sources listed {m['fresher_now']} fresher postings "
            f"from {m['companies_now']} companies, {trend}. Fresher roles are {m['fresher_share_pct']}% of all postings seen. "
            f"The most active domains were {names}. These figures describe postings in the configured sources only, "
            f"not the whole job market.")


def build_report(cfg: dict, metrics: dict, verdict: dict, news: list[dict], stats: dict,
                 mock: bool, use_llm: bool = True) -> tuple[str, str]:
    if metrics.get("empty"):
        why = "\n".join(f"- {i}" for i in verdict["issues"]) or "- No postings were collected."
        text = f"# Fresher Hiring Snapshot\n\nNo data yet.\n\n{why}\n"
    else:
        narrative = None
        if use_llm and llm.available():
            try:
                narrative = llm.write_narrative(metrics, verdict, news)
            except Exception:
                narrative = None
        narrative = narrative or template_narrative(metrics)
        m = metrics
        lines = [f"# Fresher Hiring Snapshot - {m['as_of']}", ""]
        if mock:
            lines += ["> **Demo data.** These postings are synthetic and only show how the agent works.", ""]
        lines += [
            narrative, "",
            "## Headline numbers", "",
            f"- **New fresher postings ({m['window_days']} days):** {m['fresher_now']} - {_arrow(m['fresher_change_pct'])}",
            f"- **Companies hiring freshers:** {m['companies_now']} - {_arrow(m['companies_change_pct'])}",
            f"- **Fresher share of all postings:** {m['fresher_share_pct']}%",
            f"- **Confidence:** {verdict['confidence']}", "",
            "## Domains hiring the most", "",
            "| Domain | Postings | Share | Previous | Change |", "|---|---:|---:|---:|---:|",
        ]
        for d in m["top_domains"]:
            ch = "n/a" if d["change_pct"] is None else f"{d['change_pct']:+.0f}%"
            lines.append(f"| {d['domain']} | {d['count']} | {d['share_pct']}% | {d['prev_count']} | {ch} |")
        lines += ["", "## Top hiring companies", "", "| Company | Fresher postings |", "|---|---:|"]
        lines += [f"| {c['company']} | {c['count']} |" for c in m["top_companies"]]
        lines += ["", "## Top cities", "", "| City | Postings |", "|---|---:|"]
        lines += [f"| {c['city']} | {c['count']} |" for c in m["top_cities"]]
        lines += ["", "## Most requested skills", "",
                  ", ".join(f"{s['skill']} ({s['count']})" for s in m["top_skills"]) or "n/a", ""]
        if news:
            lines += ["## Market context (news)", ""] + [f"- [{n['title']}]({n['url']})" for n in news] + [""]
        lines += ["## Data quality", "",
                  f"- Sources: {', '.join(m['sources_now']) or 'none'}; raw postings this run: {stats.get('raw', 0)}, "
                  f"unique after de-duplication: {stats.get('unique', 0)}"]
        lines += [f"- {i}" for i in verdict["issues"]] or ["- No issues detected."]
        lines += ["- Counts describe postings in the configured sources, not the entire market.", ""]
        text = "\n".join(lines)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"report_{date.today().isoformat()}{'_demo' if mock else ''}.md"
    path.write_text(text, encoding="utf-8")
    return str(path), text
