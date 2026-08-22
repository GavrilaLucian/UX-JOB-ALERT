"""
Persistent storage of seen jobs, backed by a JSON file committed to the
repo by the GitHub Actions workflow after each run (see
.github/workflows/check-jobs.yml). This is the simplest reliable option for
this workload: GitHub Actions runners are ephemeral, so state must live
somewhere durable between runs, and auto-committing a small JSON file back
to the repo is free, requires no extra service, and is easy to inspect.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .models import Job
from .dedup import job_key


@dataclass
class SeenStore:
    path: Path
    _data: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> "SeenStore":
        path = Path(path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = {}
        else:
            data = {}
        return cls(path=path, _data=data)

    def has(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str) -> dict[str, Any] | None:
        return self._data.get(key)

    def mark_seen(self, job: Job, notification_sent: bool) -> None:
        now = datetime.now(timezone.utc).isoformat()
        key = job.job_id or job_key(job.url)
        existing = self._data.get(key)
        entry = {
            "url": job.url,
            "canonical_url": job.canonical_url,
            "company": job.company,
            "title": job.title,
            "source": job.source,
            "published_at": job.published_at,
            "first_seen_at": existing["first_seen_at"] if existing else now,
            "last_seen_at": now,
            "relevance_score": job.final_score(),
            "notification_sent": notification_sent or (existing.get("notification_sent") if existing else False),
        }
        self._data[key] = entry

    def touch_last_seen(self, key: str) -> None:
        if key in self._data:
            self._data[key]["last_seen_at"] = datetime.now(timezone.utc).isoformat()

    def prune(self, max_age_days: int) -> int:
        """Remove entries not seen in max_age_days. Returns count removed."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        to_remove = []
        for key, entry in self._data.items():
            last_seen = entry.get("last_seen_at") or entry.get("first_seen_at")
            try:
                dt = datetime.fromisoformat(last_seen)
            except (TypeError, ValueError):
                continue
            if dt < cutoff:
                to_remove.append(key)
        for key in to_remove:
            del self._data[key]
        return len(to_remove)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False, sort_keys=True)

    def __len__(self) -> int:
        return len(self._data)
