"""
Robust identity for a job posting so the same role found via LinkedIn, the
company career page, or a search result is treated as ONE job.

Strategy (in order of preference):
1. If we can extract a stable ATS job id (Greenhouse/Lever/Ashby numeric or
   slug id) -> use "{ats}:{id}".
2. Otherwise, normalize the URL (strip query params/tracking, fragments,
   trailing slash, lowercase host) -> use the normalized URL.
3. As a last-resort fallback (some search snippets have unstable URLs),
   also compute a "fuzzy key" of normalized(company) + normalized(title),
   used only to *flag* likely duplicates across sources for the same run,
   not to overwrite storage identity.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "lever-source", "ref", "referer", "referrer", "source",
    "trk", "gclid", "fbclid", "igshid",
}


def normalize_url(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url.strip())
    scheme = "https"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parts.path.rstrip("/") or "/"
    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query_pairs.sort()
    query = urlencode(query_pairs)
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_ats_job_id(url: str, ats: str | None) -> str | None:
    if not url:
        return None
    if ats == "greenhouse" or "greenhouse.io" in url or "boards.greenhouse.io" in url:
        m = re.search(r"/jobs/(\d+)", url)
        if m:
            return f"greenhouse:{m.group(1)}"
    if ats == "lever" or "jobs.lever.co" in url:
        m = re.search(r"jobs\.lever\.co/[^/]+/([a-f0-9-]{20,})", url)
        if m:
            return f"lever:{m.group(1)}"
    if ats == "ashby" or "jobs.ashbyhq.com" in url:
        m = re.search(r"jobs\.ashbyhq\.com/[^/]+/([a-f0-9-]{20,})", url)
        if m:
            return f"ashby:{m.group(1)}"
    return None


def job_key(url: str, ats: str | None = None) -> str:
    """Primary persistent identity for a job posting."""
    ats_id = extract_ats_job_id(url, ats)
    if ats_id:
        return ats_id
    normalized = normalize_url(url)
    return "url:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def fuzzy_key(company: str, title: str) -> str:
    """Secondary key used to catch the same role posted with different URLs
    (e.g. LinkedIn repost of a career-page job). Used for cross-source
    de-duplication within a single run, not as the storage identity."""
    basis = normalize_text(company) + "|" + normalize_text(title)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]
