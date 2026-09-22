"""Common job schema shared by every source."""
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional


@dataclass
class Job:
    title: str
    company: str
    city: str = ""
    country: str = ""
    posted_date: str = ""          # ISO date (YYYY-MM-DD)
    source: str = ""
    url: str = ""
    description: str = ""
    salary_text: str = ""
    # filled by the pipeline
    id: str = ""
    is_fresher: Optional[int] = None  # 1 / 0 / None (ambiguous)
    exp_min: Optional[float] = None
    exp_max: Optional[float] = None
    domain: str = ""
    skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def today_iso() -> str:
    return date.today().isoformat()


class SourceConfigError(RuntimeError):
    """Raised when a source cannot run because of missing keys/config (not worth retrying)."""
