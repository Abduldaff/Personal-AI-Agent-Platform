"""Source registry. Each source is fetched independently so one outage never kills a run."""
from . import adzuna, ats, mock


def available_sources(cfg: dict, mock_mode: bool) -> dict:
    """Return {source_name: callable(cfg, attempt) -> list[Job]}."""
    if mock_mode:
        return {
            "mock_board_a": lambda c, a=0: mock.fetch(c, "mock_board_a", a),
            "mock_board_b": lambda c, a=0: mock.fetch(c, "mock_board_b", a),
        }
    sources = {"adzuna": adzuna.fetch}
    boards = cfg.get("company_boards", {})
    if boards.get("greenhouse"):
        sources["greenhouse"] = ats.fetch_greenhouse
    if boards.get("lever"):
        sources["lever"] = ats.fetch_lever
    if boards.get("ashby"):
        sources["ashby"] = ats.fetch_ashby
    if boards.get("workday"):
        sources["workday"] = ats.fetch_workday
    return sources
