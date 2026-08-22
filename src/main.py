from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Allow running as `python src/main.py` as well as `python -m src.main`
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.config import load_config, ROOT_DIR  # type: ignore
    from src.models import Job  # type: ignore
    from src.dedup import job_key, fuzzy_key  # type: ignore
    from src.storage import SeenStore  # type: ignore
    from src.filters import apply_prefilter  # type: ignore
    from src.ai_filter import apply_ai_filter  # type: ignore
    from src import telegram  # type: ignore
    from src.sources import google_search, watchlist, rss_source  # type: ignore
else:
    from .config import load_config, ROOT_DIR
    from .models import Job
    from .dedup import job_key, fuzzy_key
    from .storage import SeenStore
    from .filters import apply_prefilter
    from .ai_filter import apply_ai_filter
    from . import telegram
    from .sources import google_search, watchlist, rss_source


class SecretRedactingFilter(logging.Filter):
    """Never let a secret value leak into logs."""

    def __init__(self, secrets: list[str]):
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self.secrets:
            if s and s in msg:
                record.msg = record.getMessage().replace(s, "***REDACTED***")
                record.args = ()
        return True


def setup_logging(secrets: list[str]) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    root = logging.getLogger()
    root.addFilter(SecretRedactingFilter(secrets))


def write_github_summary(summary_lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "\n".join(summary_lines)
    print("\n" + text)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def dedupe_within_run(jobs: list[Job]) -> list[Job]:
    """Collapse duplicates within this run by URL identity first, then by
    company+title. Prefer official ATS sources over Google/search results.

    This only collapses duplicates within the current run. It does NOT mark
    jobs as previously-seen. A job that appears twice in the same run is
    still NEW if it was never in the persistent store.
    """
    SOURCE_PRIORITY = {
        "greenhouse": 0, "lever": 0, "ashby": 0,
        "career_page": 1,
        "rss": 2,
        "google_cse": 3,
    }

    def prefer(existing: Job, new: Job) -> Job:
        ep = SOURCE_PRIORITY.get(existing.source, 9)
        np = SOURCE_PRIORITY.get(new.source, 9)
        if np < ep:
            new.canonical_url = new.canonical_url or new.url
            return new
        existing.canonical_url = existing.canonical_url or existing.url
        return existing

    # Pass 1: same URL / ATS id = same job (prevents 4x same Canonical link)
    by_url: dict[str, Job] = {}
    for job in jobs:
        key = job_key(job.best_url())
        job.job_id = key
        if key in by_url:
            by_url[key] = prefer(by_url[key], job)
        else:
            by_url[key] = job

    # Pass 2: same company + title (LinkedIn vs career page with different URLs)
    by_fuzzy: dict[str, Job] = {}
    for job in by_url.values():
        fkey = fuzzy_key(job.company, job.title)
        if fkey in by_fuzzy:
            by_fuzzy[fkey] = prefer(by_fuzzy[fkey], job)
        else:
            by_fuzzy[fkey] = job

    return list(by_fuzzy.values())


def split_new_vs_seen(jobs: list[Job], store: SeenStore) -> tuple[list[Job], list[Job]]:
    """Compare unique jobs against the persistent seen store.

    Returns (new_jobs, previously_seen_jobs).
    A job is NEW only if its identity was not in the store before this run.
    """
    new_jobs: list[Job] = []
    previously_seen: list[Job] = []
    for job in jobs:
        key = job.job_id or job_key(job.best_url())
        job.job_id = key
        if store.has(key):
            store.touch_last_seen(key)
            previously_seen.append(job)
        else:
            new_jobs.append(job)
    return new_jobs, previously_seen


def run() -> int:
    cfg = load_config()
    secrets_to_redact = [
        cfg.secrets.telegram_bot_token,
        cfg.secrets.telegram_chat_id,
        cfg.secrets.google_cse_api_key,
        cfg.secrets.anthropic_api_key,
    ]
    setup_logging([s for s in secrets_to_redact if s])
    log = logging.getLogger("main")

    errors: list[str] = []
    sources_checked = 0

    # 1. Watchlist companies
    log.info("Checking %d watchlist companies...", len(cfg.companies))
    watchlist_jobs = watchlist.check_watchlist(
        companies=cfg.companies,
        google_api_key=cfg.secrets.google_cse_api_key,
        google_engine_id=cfg.secrets.google_cse_engine_id,
        fallback_enabled=cfg.search_cfg.get("per_company_fallback_queries_enabled", True),
        errors=errors,
    )
    sources_checked += len(cfg.companies)
    log.info("Watchlist check returned %d raw job listings.", len(watchlist_jobs))

    # 2. Discovery mode
    discovery_jobs: list[Job] = []
    try:
        queries = cfg.search_cfg.get("google_cse_queries", [])
        num = cfg.search_cfg.get("google_cse_results_per_query", 10)
        discovery_jobs = google_search.search_many(
            queries, cfg.secrets.google_cse_api_key, cfg.secrets.google_cse_engine_id, num=num
        )
        sources_checked += len(queries)
        log.info("Discovery search returned %d raw results.", len(discovery_jobs))
    except Exception as e:  # noqa: BLE001
        msg = f"Discovery search step failed: {e}"
        log.warning(msg)
        errors.append(msg)

    # 3. Optional RSS feeds
    rss_jobs: list[Job] = []
    feed_urls = cfg.settings.get("rss_feed_urls", [])
    if feed_urls:
        try:
            rss_jobs = rss_source.fetch_feeds(feed_urls)
            sources_checked += len(feed_urls)
            log.info("RSS feeds returned %d raw results.", len(rss_jobs))
        except Exception as e:  # noqa: BLE001
            msg = f"RSS fetch step failed: {e}"
            log.warning(msg)
            errors.append(msg)

    watchlist_company_names = {c["name"].lower() for c in cfg.companies}
    for job in discovery_jobs + rss_jobs:
        if job.company and job.company.lower() in watchlist_company_names:
            job.is_watchlist_company = True

    all_jobs = watchlist_jobs + discovery_jobs + rss_jobs
    jobs_found_total = len(all_jobs)

    # 4. Cross-source de-duplication within this run
    unique_jobs = dedupe_within_run(all_jobs)
    duplicates_removed = jobs_found_total - len(unique_jobs)
    log.info(
        "%d unique jobs after cross-source de-duplication (%d duplicates removed).",
        len(unique_jobs),
        duplicates_removed,
    )

    # 5. Load persistent seen store early
    store_path = ROOT_DIR / cfg.storage_cfg.get("seen_jobs_path", "data/seen_jobs.json")
    store = SeenStore.load(store_path)
    seen_before_run = len(store)
    log.info("Persistent seen-jobs store size before run: %d", seen_before_run)

    new_unique_jobs, previously_seen_jobs = split_new_vs_seen(unique_jobs, store)
    log.info(
        "Of %d unique jobs: %d new/unseen, %d previously seen.",
        len(unique_jobs),
        len(new_unique_jobs),
        len(previously_seen_jobs),
    )

    # 6. Keyword prefilter
    scored_jobs = apply_prefilter(unique_jobs, cfg.settings)
    prefilter_min = cfg.ai_filter_cfg.get("only_score_if_prefilter_score_at_least", 40)
    candidates = [j for j in scored_jobs if j.prefilter_score >= prefilter_min]
    log.info("%d jobs passed the keyword prefilter (>= %d).", len(candidates), prefilter_min)

    # 7. AI relevance filter
    if cfg.ai_filter_cfg.get("enabled", True):
        candidates = apply_ai_filter(
            candidates,
            api_key=cfg.secrets.anthropic_api_key,
            model=cfg.ai_filter_cfg.get("model", "claude-haiku-4-5-20251001"),
            min_prefilter_score=prefilter_min,
            max_candidates=cfg.ai_filter_cfg.get("max_candidates_per_run", 40),
        )

    relevant_jobs = [j for j in candidates if j.final_score() >= cfg.relevance_threshold]
    relevant_jobs.sort(key=lambda j: j.final_score(), reverse=True)
    rejected_by_relevance = len(candidates) - len(relevant_jobs)
    log.info(
        "%d jobs are relevant (score >= %d); %d rejected by relevance filter.",
        len(relevant_jobs),
        cfg.relevance_threshold,
        rejected_by_relevance,
    )

    # 8. Among relevant jobs, keep only NEW ones (and never queue same URL twice)
    new_job_id_set = {j.job_id for j in new_unique_jobs if j.job_id}
    new_watchlist_jobs: list[Job] = []
    new_new_company_jobs: list[Job] = []
    notified_keys: set[str] = set()

    for job in relevant_jobs:
        if not job.job_id or job.job_id not in new_job_id_set:
            continue
        if job.job_id in notified_keys:
            continue
        notified_keys.add(job.job_id)
        if job.is_watchlist_company:
            new_watchlist_jobs.append(job)
        else:
            new_new_company_jobs.append(job)

    new_relevant_count = len(new_watchlist_jobs) + len(new_new_company_jobs)
    log.info("%d NEW relevant jobs to notify (not previously seen).", new_relevant_count)

    # 9. Telegram notification
    notifications_sent = 0
    if new_relevant_count > 0:
        notifications_sent = telegram.notify(
            cfg.secrets.telegram_bot_token,
            cfg.secrets.telegram_chat_id,
            new_watchlist_jobs,
            new_new_company_jobs,
            max_per_message=cfg.max_jobs_per_message,
        )
        if notifications_sent == 0:
            errors.append("Had new relevant jobs but Telegram notification failed or is not configured.")
    else:
        log.info("No new relevant jobs today - not sending any Telegram message.")

    # 10. Persist state
    notified_ids = {id(j) for j in new_watchlist_jobs} | {id(j) for j in new_new_company_jobs}
    for job in relevant_jobs:
        was_notified = id(job) in notified_ids
        store.mark_seen(job, notification_sent=was_notified and notifications_sent > 0)

    pruned = store.prune(cfg.storage_cfg.get("max_age_days_to_keep", 120))
    store.save()
    saved_to_store = len(relevant_jobs)

    # 11. GitHub Actions summary
    write_github_summary([
        "## UX Job Alerts - run summary",
        f"- **Persistent seen jobs before run:** {seen_before_run}",
        f"- **Raw jobs found:** {jobs_found_total}",
        f"- **Duplicate jobs removed (same run):** {duplicates_removed}",
        f"- **Unique jobs:** {len(unique_jobs)}",
        f"- **Previously seen (in store):** {len(previously_seen_jobs)}",
        f"- **New/unseen (not in store):** {len(new_unique_jobs)}",
        f"- **Passed keyword prefilter (>= {prefilter_min}):** {len(candidates)}",
        f"- **Passed relevance filter (score >= {cfg.relevance_threshold}):** {len(relevant_jobs)}",
        f"- **Rejected by relevance filter:** {rejected_by_relevance}",
        f"- **New relevant jobs (to notify):** {new_relevant_count}",
        f"- **Telegram notifications sent:** {notifications_sent}",
        f"- **Saved to seen store this run:** {saved_to_store}",
        f"- **Seen-jobs store size after run:** {len(store)} (pruned {pruned} stale entries)",
        f"- **Sources checked:** {sources_checked}",
        f"- **Errors:** {len(errors)}",
        *(f"  - {e}" for e in errors),
    ])

    return 0


if __name__ == "__main__":
    sys.exit(run())