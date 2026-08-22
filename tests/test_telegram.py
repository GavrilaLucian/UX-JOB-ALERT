import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.telegram import build_messages, format_job_block
from src.models import Job


def make_job(title="Product Designer", company="Acme", score=90):
    j = Job(title=title, company=company, url="https://example.com/j", source="greenhouse",
            location_text="Bucharest", is_watchlist_company=True)
    j.ai_score = score
    j.ai_reasons = "Great fit."
    return j


def test_no_jobs_returns_no_messages():
    assert build_messages([], [], max_per_message=6) == []


def test_single_job_message_contains_key_fields():
    job = make_job()
    messages = build_messages([job], [], max_per_message=6)
    assert len(messages) == 1
    assert "Acme" in messages[0]
    assert "Product Designer" in messages[0]
    assert "90/100" in messages[0]
    assert "Apply" in messages[0]


def test_new_company_section_present():
    watchlist_job = make_job(company="TrackedCo")
    new_job = make_job(company="NewCo")
    new_job.is_watchlist_company = False
    messages = build_messages([watchlist_job], [new_job], max_per_message=6)
    combined = "\n".join(messages)
    assert "NEW COMPANY" in combined
    assert "NewCo" in combined


def test_message_splits_when_exceeding_max_per_message():
    jobs = [make_job(company=f"Co{i}") for i in range(10)]
    messages = build_messages(jobs, [], max_per_message=3)
    assert len(messages) >= 4  # 10 jobs / 3 per message rounds up


def test_format_job_block_has_no_placeholder_text():
    job = make_job()
    block = format_job_block(job, 1)
    assert "{" not in block and "}" not in block
