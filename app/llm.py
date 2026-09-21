"""Optional LLM helpers. The agent works fully without a key (rules + template narrative)."""
import json
import re

from .config import env


def available() -> bool:
    return bool(env("ANTHROPIC_API_KEY"))


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=env("ANTHROPIC_API_KEY"))


def _ask(system: str, user: str, max_tokens: int = 2000) -> str:
    resp = _client().messages.create(
        model=env("LLM_MODEL", "claude-sonnet-5"), max_tokens=max_tokens,
        system=system, messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "text", None))


def _json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def label_ambiguous(jobs: list[dict], domains: list[str], batch: int = 20) -> None:
    """Fill is_fresher for ambiguous jobs and domain for 'Other' jobs, in place."""
    targets = [j for j in jobs if j["is_fresher"] is None or j["domain"] == "Other"]
    system = ("You label job postings. Reply with ONLY a JSON list, one object per input, "
              'in the same order: {"i": <index>, "is_fresher": true|false, "domain": <one of the allowed domains or "Other">}. '
              "is_fresher is true only if the role targets candidates with 0-1 years of experience.")
    for k in range(0, len(targets), batch):
        chunk = targets[k:k + batch]
        payload = [{"i": i, "title": j["title"], "description": (j.get("description") or "")[:500]}
                   for i, j in enumerate(chunk)]
        user = f"Allowed domains: {domains}\n\nJobs:\n{json.dumps(payload)}"
        try:
            for row in _json(_ask(system, user)):
                j = chunk[int(row["i"])]
                if j["is_fresher"] is None:
                    j["is_fresher"] = 1 if row.get("is_fresher") else 0
                if j["domain"] == "Other" and row.get("domain") in domains:
                    j["domain"] = row["domain"]
        except Exception:  # never let the optional LLM step break a run
            continue


def write_narrative(metrics: dict, verdict: dict, news: list[dict]) -> str:
    system = ("You are a careful labour-market analyst writing for students looking for their first job. "
              "Use ONLY the numbers in the provided JSON; never invent or estimate figures. "
              "Write 120-180 words in plain language: overall picture, which domains lead, notable changes, "
              "and one sentence on data limits. If news snippets are given, you may mention them briefly. "
              "Do not use markdown headings.")
    user = json.dumps({"metrics": metrics, "verification": verdict, "news": news[:5]}, default=str)
    return _ask(system, user, max_tokens=600).strip()
