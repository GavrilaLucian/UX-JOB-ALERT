"""
Generic RSS/Atom feed reader. Several Romanian job boards (eJobs, BestJobs,
Hipo) have published RSS/search-feed URLs at various points, but these URLs
change over time and I can't verify live feed URLs from this environment
(no internet access to those sites here). Rather than hardcode a URL that
might silently break, this source is config-driven and OFF by default:
add feed URLs you've verified work to `rss_feed_urls` in config/settings.json
and this module will read them. This keeps the approach robust (no fragile
per-site scraping) while being honest about what's verified vs. not.

How to find a working feed URL: search the job board for "UI Designer"
(or similar), then look for an RSS/XML icon or link on the results page,
or try appending a common pattern like `&rss=1` / `/rss` to the search URL.
"""
from __future__ import annotations

import logging
import requests
import feedparser

from ..models import Job

log = logging.getLogger(__name__)


def fetch_feed(feed_url: str, source_name: str = "rss", timeout: int = 15) -> list[Job]:
    jobs: list[Job] = []
    try:
        resp = requests.get(feed_url, timeout=timeout, headers={"User-Agent": "ux-job-alerts-bot/1.0"})
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("RSS fetch failed for %s: %s", feed_url, e)
        return jobs

    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        log.warning("RSS feed could not be parsed: %s", feed_url)
        return jobs

    for entry in parsed.entries:
        title = entry.get("title", "")
        url = entry.get("link", "")
        summary = entry.get("summary", "")
        published = entry.get("published", None)
        if not title or not url:
            continue
        jobs.append(Job(
            title=title,
            company="",  # often not structured in the feed; filled in by filters if parseable from title
            url=url,
            source=source_name,
            description_snippet=summary,
            published_at=published,
        ))
    return jobs


def fetch_feeds(feed_urls: list[str]) -> list[Job]:
    all_jobs: list[Job] = []
    for url in feed_urls:
        all_jobs.extend(fetch_feed(url))
    return all_jobs
