from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Job:
    title: str
    company: str
    url: str
    source: str                      # e.g. "greenhouse", "lever", "ashby", "google_cse", "career_page"
    location_text: str = ""
    description_snippet: str = ""
    published_at: Optional[str] = None   # ISO string if known
    canonical_url: Optional[str] = None
    is_watchlist_company: bool = False
    job_id: Optional[str] = None     # id from job_key (see dedup.py), set later

    # filled in during filtering
    prefilter_score: int = 0
    prefilter_reasons: list[str] = field(default_factory=list)
    ai_score: Optional[int] = None
    ai_reasons: str = ""
    level_guess: str = ""

    def final_score(self) -> int:
        return self.ai_score if self.ai_score is not None else self.prefilter_score

    def best_url(self) -> str:
        return self.canonical_url or self.url

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
