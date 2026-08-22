"""
Pipeline tests for new/unseen detection, cross-source dedup, and the
contract that empty seen-store => all unique jobs are NEW.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import Job
from src.storage import SeenStore
from src.dedup import job_key, fuzzy_key
from src.main import dedupe_within_run, split_new_vs_seen


def make_job(title="Product Designer", company="EveryMatrix", url="https://example.com/jobs/1",
             source="greenhouse", location="Bucharest"):
    return Job(
        title=title,
        company=company,
        url=url,
        source=source,
        location_text=location,
        is_watchlist_company=True,
    )


def test_empty_seen_store_all_jobs_are_new():
    """seen_jobs = {} ; raw_jobs = [job1, job2, job3] => new_jobs = all three."""
    with tempfile.TemporaryDirectory() as d:
        store = SeenStore.load(Path(d) / "seen.json")
        assert len(store) == 0

        jobs = [
            make_job(url="https://example.com/jobs/1"),
            make_job(title="UI Designer", company="UiPath", url="https://example.com/jobs/2"),
            make_job(title="UX Designer", company="eMAG", url="https://example.com/jobs/3"),
        ]
        new_jobs, previously_seen = split_new_vs_seen(jobs, store)

        assert len(previously_seen) == 0
        assert len(new_jobs) == 3
        assert {j.url for j in new_jobs} == {j.url for j in jobs}


def test_partial_seen_store_returns_only_unseen():
    """seen_jobs = {job1} ; raw_jobs = [job1, job2, job3] => new_jobs = [job2, job3]."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "seen.json"
        store = SeenStore.load(path)

        job1 = make_job(url="https://example.com/jobs/1")
        job1.job_id = job_key(job1.url)
        store.mark_seen(job1, notification_sent=True)
        store.save()

        store2 = SeenStore.load(path)
        assert store2.has(job1.job_id)

        jobs = [
            make_job(url="https://example.com/jobs/1"),
            make_job(title="UI Designer", company="UiPath", url="https://example.com/jobs/2"),
            make_job(title="UX Designer", company="eMAG", url="https://example.com/jobs/3"),
        ]
        new_jobs, previously_seen = split_new_vs_seen(jobs, store2)

        assert len(previously_seen) == 1
        assert previously_seen[0].url == "https://example.com/jobs/1"
        assert len(new_jobs) == 2
        assert {j.url for j in new_jobs} == {
            "https://example.com/jobs/2",
            "https://example.com/jobs/3",
        }


def test_same_job_from_two_sources_is_deduped_but_still_new():
    """Same role via Greenhouse + Google must collapse to 1 job, and that job
    is NEW if the store is empty (not marked seen merely because it appeared twice)."""
    with tempfile.TemporaryDirectory() as d:
        store = SeenStore.load(Path(d) / "seen.json")

        from_greenhouse = make_job(
            title="Product Designer",
            company="EveryMatrix",
            url="https://boards.greenhouse.io/everymatrix/jobs/12345",
            source="greenhouse",
        )
        from_google = make_job(
            title="Product Designer",
            company="EveryMatrix",
            url="https://www.linkedin.com/jobs/view/999",
            source="google_cse",
        )

        # Same company+title => same fuzzy key
        assert fuzzy_key(from_greenhouse.company, from_greenhouse.title) == fuzzy_key(
            from_google.company, from_google.title
        )

        unique = dedupe_within_run([from_greenhouse, from_google])
        assert len(unique) == 1
        # Prefer official ATS source
        assert unique[0].source == "greenhouse"

        new_jobs, previously_seen = split_new_vs_seen(unique, store)
        assert len(previously_seen) == 0
        assert len(new_jobs) == 1
        assert new_jobs[0].source == "greenhouse"


def test_tracking_param_variants_share_persistent_id():
    """URL with different tracking params must share the same job_key."""
    a = make_job(url="https://example.com/careers/pd?utm_source=linkedin")
    b = make_job(url="https://example.com/careers/pd?ref=indeed")
    assert job_key(a.url) == job_key(b.url)

    with tempfile.TemporaryDirectory() as d:
        store = SeenStore.load(Path(d) / "seen.json")
        a.job_id = job_key(a.url)
        store.mark_seen(a, notification_sent=True)

        new_jobs, previously_seen = split_new_vs_seen([b], store)
        assert len(new_jobs) == 0
        assert len(previously_seen) == 1
