"""
Greenhouse exposes a public, unauthenticated JSON API for any company's job
board: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
No API key needed, no ToS issue (it's the same data the public board page
shows), and it's far more robust than scraping HTML.
"""
from __future__ import annotations

import logging
import requests

from ..models import Job

log = logging.getLogger(__name__)

API_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def fetch_jobs(company_name: str, slug: str, timeout: int = 15) -> list[Job]:
    jobs: list[Job] = []
    try:
        resp = requests.get(API_URL.format(slug=slug), params={"content": "true"}, timeout=timeout)
        if resp.status_code == 404:
            log.info("Greenhouse: no board found for slug '%s' (company %s)", slug, company_name)
            return jobs
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        log.warning("Greenhouse fetch failed for %s (%s): %s", company_name, slug, e)
        return jobs
    except ValueError as e:
        log.warning("Greenhouse invalid JSON for %s (%s): %s", company_name, slug, e)
        return jobs

    for item in payload.get("jobs", []):
        title = item.get("title", "")
        url = item.get("absolute_url", "")
        location = (item.get("location") or {}).get("name", "")
        updated_at = item.get("updated_at")
        if not title or not url:
            continue
        jobs.append(Job(
            title=title,
            company=company_name,
            url=url,
            source="greenhouse",
            location_text=location,
            published_at=updated_at,
            is_watchlist_company=True,
        ))
    return jobs
