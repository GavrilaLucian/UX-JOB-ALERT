"""
Ashby exposes a public job board API used by their own embeddable widget:
https://api.ashbyhq.com/posting-api/job-board/{slug}
No API key required for public boards.
"""
from __future__ import annotations

import logging
import requests

from ..models import Job

log = logging.getLogger(__name__)

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch_jobs(company_name: str, slug: str, timeout: int = 15) -> list[Job]:
    jobs: list[Job] = []
    try:
        resp = requests.get(API_URL.format(slug=slug), timeout=timeout)
        if resp.status_code == 404:
            log.info("Ashby: no board found for slug '%s' (company %s)", slug, company_name)
            return jobs
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        log.warning("Ashby fetch failed for %s (%s): %s", company_name, slug, e)
        return jobs
    except ValueError as e:
        log.warning("Ashby invalid JSON for %s (%s): %s", company_name, slug, e)
        return jobs

    for item in payload.get("jobs", []):
        title = item.get("title", "")
        url = item.get("jobUrl") or item.get("applyUrl", "")
        location = item.get("location", "")
        published_at = item.get("publishedAt")
        if not title or not url:
            continue
        jobs.append(Job(
            title=title,
            company=company_name,
            url=url,
            source="ashby",
            location_text=location,
            published_at=published_at,
            is_watchlist_company=True,
        ))
    return jobs
