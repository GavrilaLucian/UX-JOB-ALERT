"""
Lever exposes a public JSON API: https://api.lever.co/v0/postings/{slug}?mode=json
No API key required.
"""
from __future__ import annotations

import logging
import requests

from ..models import Job

log = logging.getLogger(__name__)

API_URL = "https://api.lever.co/v0/postings/{slug}"


def fetch_jobs(company_name: str, slug: str, timeout: int = 15) -> list[Job]:
    jobs: list[Job] = []
    try:
        resp = requests.get(API_URL.format(slug=slug), params={"mode": "json"}, timeout=timeout)
        if resp.status_code == 404:
            log.info("Lever: no board found for slug '%s' (company %s)", slug, company_name)
            return jobs
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        log.warning("Lever fetch failed for %s (%s): %s", company_name, slug, e)
        return jobs
    except ValueError as e:
        log.warning("Lever invalid JSON for %s (%s): %s", company_name, slug, e)
        return jobs

    if not isinstance(payload, list):
        return jobs

    for item in payload:
        title = item.get("text", "")
        url = item.get("hostedUrl", "")
        categories = item.get("categories", {}) or {}
        location = categories.get("location", "")
        created_at_ms = item.get("createdAt")
        published_at = None
        if created_at_ms:
            from datetime import datetime, timezone
            try:
                published_at = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OSError):
                published_at = None
        if not title or not url:
            continue
        jobs.append(Job(
            title=title,
            company=company_name,
            url=url,
            source="lever",
            location_text=location,
            published_at=published_at,
            is_watchlist_company=True,
        ))
    return jobs
