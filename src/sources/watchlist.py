from __future__ import annotations

import logging

from ..models import Job
from . import ats_greenhouse, ats_lever, ats_ashby, google_search

log = logging.getLogger(__name__)

ATS_DISPATCH = {
    "greenhouse": ats_greenhouse.fetch_jobs,
    "lever": ats_lever.fetch_jobs,
    "ashby": ats_ashby.fetch_jobs,
}


def check_watchlist(
    companies: list[dict],
    google_api_key: str | None,
    google_engine_id: str | None,
    fallback_enabled: bool,
    errors: list[str],
) -> list[Job]:
    jobs: list[Job] = []

    for company in companies:
        name = company.get("name", "")
        ats = company.get("ats")
        slug = company.get("ats_slug")

        if ats and slug and ats in ATS_DISPATCH:
            try:
                company_jobs = ATS_DISPATCH[ats](name, slug)
                jobs.extend(company_jobs)
                continue
            except Exception as e:  # noqa: BLE001 - keep the run alive
                msg = f"ATS check failed for {name} ({ats}:{slug}): {e}"
                log.warning(msg)
                errors.append(msg)
                # fall through to Google fallback below

        if fallback_enabled and google_api_key and google_engine_id:
            query = f'"{name}" (UI OR UX OR "Product Designer") Romania jobs'
            try:
                results = google_search.search(query, google_api_key, google_engine_id, num=5)
                for r in results:
                    r.company = name
                    r.is_watchlist_company = True
                jobs.extend(results)
            except Exception as e:  # noqa: BLE001
                msg = f"Fallback search failed for {name}: {e}"
                log.warning(msg)
                errors.append(msg)

    return jobs
