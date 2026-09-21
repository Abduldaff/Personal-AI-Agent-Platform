"""LangGraph pipeline:

collect -> normalize -> label_fresher -> classify -> store -> analyze -> verify -+-> report
   ^                                                                            |
   +---------------------- retry failed sources (max_retries) -----------------+
"""
from typing import TypedDict

from langgraph.graph import END, StateGraph

from . import analyze, classify, config, db, fresher, llm, news, normalize, report, verify as verify_mod
from .models import SourceConfigError
from .sources import available_sources


class AgentState(TypedDict, total=False):
    cfg: dict
    mock: bool
    use_llm: bool
    use_news: bool
    attempt: int
    pending: list[str]
    raw_jobs: list[dict]
    source_status: dict
    jobs: list[dict]
    stats: dict
    seen_by_source: dict
    metrics: dict
    verdict: dict
    news: list[dict]
    report_path: str
    report_text: str
    log: list[str]


def _log(state: AgentState, msg: str) -> list[str]:
    print(msg)
    return state.get("log", []) + [msg]


# ---------------------------------------------------------------- nodes
def collect(state: AgentState) -> dict:
    sources = available_sources(state["cfg"], state["mock"])
    pending = state.get("pending") or list(sources)
    attempt = state.get("attempt", 0)
    raw = list(state.get("raw_jobs", []))
    status = dict(state.get("source_status", {}))
    log = state.get("log", [])
    for name in pending:
        try:
            jobs = sources[name](state["cfg"], attempt)
            raw += [j.to_dict() for j in jobs]
            status[name] = {"fetched": len(jobs), "error": "", "retryable": True}
            db.log_run(name, len(jobs))
            log = _log({"log": log}, f"[collect] {name}: {len(jobs)} postings")
        except SourceConfigError as e:
            status[name] = {"fetched": 0, "error": str(e), "retryable": False}
            db.log_run(name, 0, str(e))
            log = _log({"log": log}, f"[collect] {name}: SKIPPED ({e})")
        except Exception as e:  # network errors, HTTP errors, ...
            status[name] = {"fetched": 0, "error": f"{type(e).__name__}: {e}", "retryable": True}
            db.log_run(name, 0, str(e))
            log = _log({"log": log}, f"[collect] {name}: FAILED ({type(e).__name__}: {e})")
    return {"raw_jobs": raw, "source_status": status, "log": log}


def normalize_node(state: AgentState) -> dict:
    jobs, stats, seen = normalize.normalize_and_dedupe(state["raw_jobs"])
    return {"jobs": jobs, "stats": stats, "seen_by_source": seen,
            "log": _log(state, f"[normalize] {stats['raw']} raw -> {stats['unique']} unique "
                               f"({stats['duplicates_removed']} duplicates removed)")}


def fresher_node(state: AgentState) -> dict:
    jobs = fresher.label_all(state["jobs"], state["cfg"])
    n1 = sum(1 for j in jobs if j["is_fresher"] == 1)
    n_amb = sum(1 for j in jobs if j["is_fresher"] is None)
    return {"jobs": jobs, "log": _log(state, f"[fresher] {n1} fresher, {n_amb} ambiguous, {len(jobs) - n1 - n_amb} not fresher")}


def classify_node(state: AgentState) -> dict:
    jobs = classify.classify_all(state["jobs"], state["cfg"])
    msg = "[classify] domains assigned by keyword scoring"
    if state.get("use_llm") and llm.available():
        llm.label_ambiguous(jobs, list(state["cfg"]["domains"]))
        msg += " + LLM pass for ambiguous/unclassified"
    return {"jobs": jobs, "log": _log(state, msg)}


def store_node(state: AgentState) -> dict:
    new, upd = db.upsert_jobs(state["jobs"])
    ok_sources = [s for s, st in state["source_status"].items() if not st["error"] and st["fetched"] > 0]
    all_seen = set().union(*state["seen_by_source"].values()) if state["seen_by_source"] else set()
    for s in ok_sources:
        db.mark_inactive(s, all_seen)
    return {"log": _log(state, f"[store] {new} new postings saved, {upd} already known")}


def analyze_node(state: AgentState) -> dict:
    m = analyze.compute_metrics(state["cfg"])
    return {"metrics": m, "log": _log(state, "[analyze] metrics computed with SQL/pandas")}


def verify_node(state: AgentState) -> dict:
    attempt = state.get("attempt", 0)
    verdict = verify_mod.verify(state["metrics"], state["cfg"], state["source_status"], state["stats"], attempt)
    msg = f"[verify] confidence={verdict['confidence']}, issues={len(verdict['issues'])}"
    update = {"verdict": verdict}
    if verdict["retry_sources"]:
        update.update({"pending": verdict["retry_sources"], "attempt": attempt + 1})
        msg += f" -> retrying {verdict['retry_sources']} (attempt {attempt + 1})"
    else:
        update["pending"] = []
    return {**update, "log": _log(state, msg)}


def route_after_verify(state: AgentState) -> str:
    return "collect" if state.get("pending") else "news"


def news_node(state: AgentState) -> dict:
    items = news.fetch_news(state["cfg"]) if state.get("use_news") else []
    return {"news": items, "log": _log(state, f"[news] {len(items)} context articles")}


def report_node(state: AgentState) -> dict:
    path, text = report.build_report(state["cfg"], state["metrics"], state["verdict"], state.get("news", []),
                                     state["stats"], state["mock"], state.get("use_llm", True))
    return {"report_path": path, "report_text": text, "log": _log(state, f"[report] saved {path}")}


# ---------------------------------------------------------------- graph
def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [("collect", collect), ("normalize", normalize_node), ("label_fresher", fresher_node),
                     ("classify", classify_node), ("store", store_node), ("analyze", analyze_node),
                     ("verify", verify_node), ("news", news_node), ("report", report_node)]:
        g.add_node(name, fn)
    g.set_entry_point("collect")
    for a, b in [("collect", "normalize"), ("normalize", "label_fresher"), ("label_fresher", "classify"),
                 ("classify", "store"), ("store", "analyze"), ("analyze", "verify"), ("news", "report")]:
        g.add_edge(a, b)
    g.add_conditional_edges("verify", route_after_verify, {"collect": "collect", "news": "news"})
    g.add_edge("report", END)
    return g.compile()


def run_pipeline(cfg: dict, mock: bool = False, use_llm: bool = True, use_news: bool = True) -> AgentState:
    config.use_db(demo=mock)
    return build_graph().invoke({"cfg": cfg, "mock": mock, "use_llm": use_llm, "use_news": use_news,
                                 "attempt": 0, "pending": [], "raw_jobs": [], "source_status": {}, "log": []})
