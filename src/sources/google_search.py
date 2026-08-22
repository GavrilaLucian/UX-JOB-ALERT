"""
Google Programmable Search Engine (Custom Search JSON API).

Free tier: 100 queries/day, then $5 per 1000 queries beyond that
(see https://developers.google.com/custom-search/v1/overview). This project
is designed to stay comfortably inside the free 100/day tier (see README for
the query budget breakdown).

Why this instead of scraping Google directly: scraping Google's result pages
violates their Terms of Service and breaks unpredictably. The official API
is the robust, ToS-compliant way to run programmatic searches.

Setup: create a Programmable Search Engine at
https://programmablesearchengine.google.com/ (set it to "search the entire
web"), then create an API key at https://console.cloud.google.com/apis/credentials
with the "Custom Search API" enabled. Put the API key in SEARCH_API_KEY and
the search engine ID ("cx") in SEARCH_ENGINE_ID.
"""
from __future__ import annotations

import logging
import re
import requests

from ..models import Job

log = logging.getLogger(__name__)

API_URL = "https://www.googleapis.com/customsearch/v1"

# Patterns used to lift a rough location string out of a search snippet/title
# when the API does not provide a dedicated location field.
_LOCATION_RE = re.compile(
    r"(?i)\b("
    r"Bucharest|București|Bucuresti|"
    r"Cluj(?:-Napoca)?|Ia[sș]i|Iasi|"
    r"Timi[sș]oara|Timisoara|Bra[sș]ov|Brasov|"
    r"Remote\s*(?:Romania|România|EU|Europe|EMEA)?|"
    r"Romania|România"
    r")\b"
)


def _guess_location(title: str, snippet: str) -> str:
    for text in (title, snippet):
        m = _LOCATION_RE.search(text or "")
        if m:
            return m.group(0)
    return ""


def search(query: str, api_key: str, engine_id: str, num: int = 10, timeout: int = 15) -> list[Job]:
    jobs: list[Job] = []
    if not api_key or not engine_id:
        log.info("Google CSE not configured (missing SEARCH_API_KEY / SEARCH_ENGINE_ID); skipping query: %s", query)
        return jobs

    params = {
        "key": api_key,
        "cx": engine_id,
        "q": query,
        "num": min(num, 10),
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as e:
        log.warning("Google CSE query failed (%s): %s", query, e)
        return jobs
    except ValueError as e:
        log.warning("Google CSE invalid JSON (%s): %s", query, e)
        return jobs

    for item in payload.get("items", []):
        title = item.get("title", "")
        url = item.get("link", "")
        snippet = item.get("snippet", "")
        display_link = item.get("displayLink", "")
        if not title or not url:
            continue
        # Best-effort company guess from the domain; refined later by filters/AI.
        company_guess = display_link.replace("www.", "").split(".")[0].title()
        location_guess = _guess_location(title, snippet)
        jobs.append(Job(
            title=title,
            company=company_guess,
            url=url,
            source="google_cse",
            description_snippet=snippet,
            location_text=location_guess,
        ))
    return jobs


def search_many(queries: list[str], api_key: str, engine_id: str, num: int = 10) -> list[Job]:
    all_jobs: list[Job] = []
    for q in queries:
        all_jobs.extend(search(q, api_key, engine_id, num=num))
    return all_jobs
